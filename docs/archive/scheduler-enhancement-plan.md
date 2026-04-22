# Context

当前 `backend/app/scheduler/` 的 scheduler 是 **run 级别** 调度，不是 step 级别调度。核心准入逻辑在 `backend/app/scheduler/scheduler.py` 的 `_wait_for_resources()`：它会在启动 run 前，通过 `backend/app/scheduler/resources.py` 的 `ResourceEstimator.estimate()` 给整条 run 估一个资源包，再通过 `ResourceChecker.shortage_reasons()` 判断是否能启动。

这套机制的关键问题是：资源估算基本是“整条流程最粗粒度模板”。例如 `sarek` 会被匹配成 `xlarge`，即使它当前只跑到 FASTQC / MultiQC 这类轻步骤，也仍被当成整条大资源 run 对待。于是轻步骤阶段也会阻塞其他 run，造成明显资源浪费。

同时，当前架构里 Nextflow 与 MiniWDL 都是以 **整条 workflow 黑盒执行器** 的方式接入：
- Nextflow：`backend/app/engine/adapters/nextflow.py` 通过 `nextflow run ... -with-trace -with-dag` 启动整个 pipeline；
- WDL：`backend/app/engine/adapters/wdl.py` 通过 `miniwdl run ... --dir ...` 启动整个 workflow。

因此，bpiper 目前真正能控制的是“什么时候启动一个 run”，而不是“在一个已启动的 Nextflow/WDL run 内，逐 step 决定先跑谁”。

# Findings

## 当前 scheduler 是如何实现的

- 队列模型：`backend/app/scheduler/models.py`
  - `ScheduledTask` 以 run 为单位入队，状态是 `QUEUED / DISPATCHED / COMPLETED / FAILED / CANCELLED`。
- 队列策略：`backend/app/scheduler/queue.py`
  - `TaskQueue._dequeue_in_session()` 只按 `priority + FIFO` 取下一个 task。
  - 当前不考虑 project fairness、quota、真实资源占用。
- 调度执行：`backend/app/scheduler/scheduler.py`
  - worker 从队列 claim 一个 run task。
  - `_wait_for_resources()` 在启动前判断资源是否足够；不够则 `re_enqueue()` 并延迟 30 秒。
- 资源监控：`backend/app/scheduler/monitor.py`
  - 已能采集主机级 CPU / memory / disk / GPU。
  - 但还不是 run 级跟踪。
- 资源估算：`backend/app/scheduler/resources.py`
  - 先看显式 `run.config.resources`；
  - 再按 workflow 名匹配模板（如 `sarek -> xlarge`, `rnaseq -> large`）；
  - 否则回退到 `medium`。
- 运行时事件：`backend/app/runtime/jobs.py`
  - 已处理 `PROCESS_INFO`，把 `pid` 写进 `run.config.runtime.pid`；
  - 已处理 `TASK_UPDATE`，更新 `run.current_task` 与 DAG 状态。
- 历史数据：`backend/app/services/trace_parser.py`
  - 已能解析 Nextflow trace 的 `process_name`、`cpu_percent`、`peak_rss`、`duration`。

## 关于 step-level dynamic scheduling 的判断

### Nextflow

当前架构下，bpiper **不适合直接接管 Nextflow 的 step/task 调度**。原因是：
- Nextflow 自己已经是 task scheduler；
- bpiper 现在只是在外层启动 `nextflow run`；
- `TASK_UPDATE` 和 trace 只能给 bpiper 提供观测信息，不能把内部 task queue 控制权交还给 bpiper。

所以对 Nextflow，现实路线应该是：
- 做更聪明的 **run admission**；
- 用运行中真实资源占用做纠偏；
- 用 trace 做历史学习；
- 必要时通过 config override 给 pipeline 增加 executor guardrail（例如限制过度并发），但不把 bpiper改造成 Nextflow 内核调度器。

### WDL / MiniWDL

WDL 的 step-level 调度在长期上更有可能做，因为 WDL 的 task/runtime 结构更适合作为 DAG/step 执行基础。

但在当前 `miniwdl run` 黑盒模式下，bpiper 仍然没有真正的 step 调度权。若未来一定要做真正的 step scheduler，建议把它作为 **WDL 专项执行路径** 单独设计，而不是在当前 scheduler 上小修小补。

# Recommended approach

## 1. 第一优先级：基于真实运行中占用的 run admission

目标：不要再把一个 run 从头到尾都按固定大资源包占着。

做法：
- 扩展 `backend/app/scheduler/monitor.py`，在主机级监控之外，基于 `run.config.runtime.pid` 做 **per-run process tree** CPU / memory 使用跟踪；
- 扩展 `backend/app/scheduler/scheduler.py:_wait_for_resources()`，把“活跃 runs 的真实占用”纳入 admission 决策，而不是只依赖模板；
- 保留 `ResourceEstimator` 作为启动前初始估算，但启动后尽快由真实 usage 接管。

这能在不改引擎执行模型的前提下，逼近你想要的“步骤维度动态效果”。

复杂度：M

DB schema：首版可不改。

## 2. 第二优先级：基于 trace 的历史资源画像

目标：把静态模板升级为经验化预测。

做法：
- 在 `backend/app/scheduler/hooks.py:RunCompletionHooks.on_run_terminal()` 中接入 trace 聚合；
- 复用 `backend/app/services/trace_parser.py` 的 `process_name / cpu_percent / peak_rss / duration`；
- 扩展 `backend/app/scheduler/resources.py:ResourceEstimator`，估算顺序变成：
  1. 显式 resources
  2. 历史 profile
  3. pipeline template
  4. medium fallback

这对生信特别重要，因为同样是 `rnaseq`，样本数、参考基因组、流程阶段都会显著改变资源画像。

复杂度：M

DB schema：建议新增 profile 表。

## 3. 第三优先级：resume-aware scheduling

目标：`-resume` 命中缓存时，不要仍按完整流程估算。

做法：
- 复用 `backend/app/engine/adapters/nextflow.py` 已有的 `resume` / `resume_from`；
- 在 `ResourceEstimator` 中加入 resume-aware 分支；
- 如果预测不准，仍由“真实运行中占用跟踪”纠偏。

复杂度：S

DB schema：否。

## 4. 第四优先级：暴露“为什么排队”

目标：让用户明确看到 run 是因为 CPU、memory、disk、quota、fairness 还是 retry delay 被挡住，而不是只看到 `QUEUED`。

做法：
- 扩展 `backend/app/scheduler/scheduler.py` 记录最近一次 resource decision / shortage reasons / delay_until；
- 扩展 `backend/app/api/v1/scheduler.py` 和 run 详情 API 把这些 blocker 暴露出来。

复杂度：S

DB schema：可选。

## 5. 第五优先级：公平调度与项目配额

目标：适应共享生信平台场景，避免某个项目长期吃满资源。

做法：
- 扩展 `backend/app/scheduler/queue.py`，在 priority 之下引入 fair-share / project-aware ordering；
- 在 admission 阶段增加 project quota（并发 run 数、CPU、memory、GPU）。

复杂度：M

DB schema：建议有。

## 6. 第六优先级：OOM 风险预测与自适应降并发

目标：减少组装、比对、变异检测等高风险步骤反复 OOM 后再 retry 的浪费。

做法：
- 复用 `backend/app/scheduler/retry.py` 里的 OOM pattern；
- 把历史 trace / OOM 历史反馈给 `ResourceEstimator` 或 risk evaluator；
- 对高风险 workflow/process 提前提高 memory multiplier 或降低 admission 并发。

复杂度：M

DB schema：可选。

## 7. 长期方向：如果真要“真正的 step scheduler”，优先单独走 WDL 路线

结论：
- **Nextflow**：建议继续保持黑盒 executor，bpiper 做外层 admission / fairness / observability / learning。
- **WDL**：若未来战略上需要真正 step-level scheduling，建议新建 WDL DAG/step 执行路径，而不是继续依赖 `miniwdl run` 黑盒。

复杂度：XL

DB schema：需要较大改动。

# Other bioinformatics-specific findings

1. 当前模板过粗，无法表达 phase 差异、样本数差异、参考基因组差异。
2. 当前 queue 只按 priority + FIFO，不适合多项目共享平台。
3. 已有主机级资源监控与 PID 落点，说明“真实占用感知”不是从零开始。
4. trace 已足够支持第一版历史学习，不必先大改引擎层。
5. timeout / retry 已有，但还没和资源画像形成反馈闭环。
6. 目前 scheduler API 可观测性偏弱，用户看不到 run 被阻塞的具体原因。

# Critical files

- `backend/app/scheduler/scheduler.py`
- `backend/app/scheduler/resources.py`
- `backend/app/scheduler/monitor.py`
- `backend/app/runtime/jobs.py`
- `backend/app/services/trace_parser.py`
- `backend/app/scheduler/hooks.py`
- `backend/app/scheduler/queue.py`
- `backend/app/api/v1/scheduler.py`

# Existing functions/utilities to reuse

- `RunScheduler._wait_for_resources()` — `backend/app/scheduler/scheduler.py`
- `ResourceEstimator.estimate()` — `backend/app/scheduler/resources.py`
- `ResourceChecker.shortage_reasons()` — `backend/app/scheduler/resources.py`
- `ResourceMonitor.current()` — `backend/app/scheduler/monitor.py`
- `RunCompletionHooks.on_run_terminal()` — `backend/app/scheduler/hooks.py`
- `TraceParser.parse_trace_file()` / `iter_tasks()` — `backend/app/services/trace_parser.py`
- `_handle_run_event()` 对 `PROCESS_INFO` / `TASK_UPDATE` 的处理 — `backend/app/runtime/jobs.py`
- `TaskQueue._dequeue_in_session()` — `backend/app/scheduler/queue.py`

# Verification

## Code-level
- 为 `ResourceEstimator` 增加显式 resources / 历史 profile / template / fallback 优先级测试
- 为 per-run usage accounting 增加 admission 测试
- 为 blocker visibility 增加 API 测试
- 若纳入 fairness / quota，则增加调度顺序测试

## End-to-end
- 用一个同时含轻/重步骤的 Nextflow workflow 做多 run 并发验证
- 用 `-resume` 验证 resume-aware admission
- 在资源紧张场景下验证 blocker 原因可解释
- 对比修改前后的利用率、排队时间、吞吐量、OOM 重试率

## Commands to run later during implementation
- `git branch --show-current`
- `git worktree list`
- `cd backend && uv run pytest tests/test_scheduler -v`
- `cd backend && uv run pytest`
- 启动后调用 `/api/v1/scheduler/status` 与 `/api/v1/scheduler/resources`

# Recommended first implementation slice

已确认的方向分成两条线并行推进：

## Track A：当前轮实现（Admission 增强 + fair-share / quota）

第一轮建议实现：
1. per-run 真实资源占用跟踪
2. scheduler blocker / shortage 可观测性
3. trace 驱动的历史资源画像
4. resume-aware admission
5. fair-share 调度
6. project quota

其中前四项解决“资源被粗粒度 run 模板浪费”的核心问题，后两项解决“共享生信平台治理”的问题。

建议实现顺序：
- Phase A1：真实占用跟踪 + blocker 可观测性
- Phase A2：历史画像 + resume-aware admission
- Phase A3：fair-share + project quota

这样拆分的原因是：
- fair-share / quota 依赖更可信的 usage accounting，避免只基于粗模板做不公平治理；
- 能更清楚地区分“机器资源不足”与“租户策略限制”两类阻塞原因。

## Track B：长期方案设计（WDL step-level scheduler exploration）

这一轨建议先做设计与验证，不与当前轮 admission 改造混在同一实现批次：
1. 明确 WDL step 实例模型、状态机、依赖图和 queue 设计
2. 评估是否需要新的 `run_steps` / `scheduled_steps` 表
3. 明确与现有 `Run` / `ScheduledTask` / DAG UI 的关系
4. 设计如何让 WDL 走 step-level execution，而 Nextflow 仍保持黑盒 executor

这能保留真正 step-level scheduling 的长期路线，但不会把当前 Nextflow/WDL 黑盒执行路径和短期高收益优化耦死。

这是当前架构下收益最高、边界最清晰、且和你刚确认的范围最一致的一组推进方式。
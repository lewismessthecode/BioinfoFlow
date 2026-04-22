# 04 — 分阶段实施计划

本计划的目标是把重构拆成多个可合并阶段，避免一次性大改。

## 总体顺序

```text
Phase 0 -> Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6
```

```text
Phase 0: Baseline and seams
Phase 1: Engine abstraction
Phase 2: Persistent run scheduler
Phase 3: Retry / timeout / cleanup / audit baseline
Phase 4: DAG and schema improvements
Phase 5: Resource-aware scheduling
Phase 6: Batch submission and notifications
```

## Phase 0 — Baseline and seams

### 目标

在不改变外部行为的前提下，补齐后续重构需要的“接口缝”和回归保护。

### 主要工作

1. 为 run lifecycle 增加 characterization tests
2. 为 SSE run events 增加回归测试
3. 为 `Run.config` 引入 helper 或 accessor
4. 将“run dispatch”从 `RunService` 中抽成一个可替换接口
5. 区分 run scheduler 和 generic background tasks 的用途

### 关键产出

- 可以替换 `task_runner.submit(execute_run, run_id)` 而不直接动 API
- 可以在不重写所有逻辑的情况下切换到新 scheduler

### 退出条件

1. 现有 run API 行为不变
2. 已有 run 测试通过
3. 新增的 characterization tests 固化当前行为

## Phase 1 — Engine abstraction

### 目标

建立 `EngineAdapter` + `ExecutionBackend`，消除引擎 if/elif 分支。

### 主要工作

1. 创建 `app/engine/`
2. 迁移 Nextflow 命令构建、事件解析、取消逻辑到 `NextflowAdapter`
3. 迁移 MiniWDL 逻辑到 `WDLAdapter`
4. 抽出 `LocalBackend`
5. 将 `execute_run()` 中的引擎分支替换为统一 backend + adapter 调用

### 关键修订

Nextflow 的 Docker 检测和 config 注入应一并迁移到 adapter 或 adapter 前置处理，而不是继续保留在 `jobs.py`。

### 退出条件

1. `RunService.cancel_run()` 不再写引擎分支
2. `jobs.py` 不再写引擎分支
3. Nextflow/WDL 的 stdout/stderr 都转为统一 `EngineEvent`

## Phase 2 — Persistent run scheduler

### 目标

将 runs 从内存 FIFO 队列迁移到 DB-backed scheduler。

### 主要工作

1. 创建 `scheduled_tasks` 表
2. 引入 `RunScheduler`
3. 支持可配置并发
4. 支持优先级和背压
5. 支持启动恢复
6. 增加 `/scheduler/status`

### 关键修订

只迁移 run 执行链路。
image pull 继续使用 generic background runner，不强行纳入 run scheduler。

### 退出条件

1. run create/resume/retry 走 scheduler.enqueue()
2. 服务重启后 queued task 可恢复
3. 可以查询队列深度和 worker 状态

## Phase 3 — Retry / timeout / cleanup / audit baseline

### 目标

先交付一组“真正降低风险”的平台能力。

### 主要工作

1. 引入 `RetryPolicy`
2. 在 scheduler 中实现平台级重试
3. 引入 timeout watcher
4. 引入 work-dir cleanup
5. 引入 audit log
6. 扩展 `RunCreate` 支持 `retry_policy` 和 `timeout_seconds`

### 对 resume 的处理

- Nextflow native resume 在本阶段一起稳定
- WDL resume 先不承诺完整能力
- 如果要开始做 WDL resume，只允许先交 best-effort 版本并明确限制

### 退出条件

1. 超时 run 能自动 cancel
2. retry policy 可配置
3. 审计日志覆盖关键操作
4. 有手动 cleanup API

## Phase 4 — DAG and schema improvements

### 目标

明显改善新 workflow 的 DAG 可视化和运行时状态映射能力。

### 主要工作

1. 引入 `SchemaExtractor`
2. 将 `WorkflowValidator` 改为“工具优先，正则 fallback”
3. 为 Nextflow 引入 inspect / nf-core schema 能力
4. 为 WDL 引入基于 `miniwdl` 的结构提取
5. 引入 `DagMatcher`
6. 在 schema 不完整时支持 runtime DAG 增量构建

### 退出条件

1. 复杂 Nextflow DSL2 的 schema 提取成功率明显高于当前实现
2. 运行时 DAG 匹配失败率下降
3. DAG 构建和运行时更新逻辑不再散落在多个模块里

## Phase 5 — Resource-aware scheduling

### 目标

在 scheduler 稳定后加一层保守资源检查，减少资源超卖。

### 主要工作

1. 引入 `ResourceMonitor`
2. 引入 `ResourceEstimator`
3. 引入 `ResourceChecker`
4. 增加 `/scheduler/resources`
5. 将资源不足时的任务延后重排

### 限制

本阶段只做“保守估计 + 安全余量”，不做精准容量规划。

### 退出条件

1. 能阻止明显资源不足的任务直接启动
2. 有基本资源状态查询

## Phase 6 — Batch submission and notifications

### 目标

在前置基础设施稳定后，再交付批量投递和通知能力。

### 主要工作

1. `batches` / `batch_runs`
2. `notification_configs`
3. 批次 API
4. webhook 通知
5. run completion hooks

### 限制

V2 不要求 webhook 做持久化重试投递；记录日志和尽力发送即可。

### 退出条件

1. 批量创建运行可用
2. 批次状态聚合正确
3. run complete/fail 时 webhook 能发送

## 各阶段依赖关系

| Phase | 依赖 |
|------|------|
| Phase 0 | 无 |
| Phase 1 | Phase 0 |
| Phase 2 | Phase 1 |
| Phase 3 | Phase 2 |
| Phase 4 | Phase 1，最好在 Phase 2 后执行 |
| Phase 5 | Phase 2 |
| Phase 6 | Phase 2，最好在 Phase 3 后执行 |

## 推荐的首批实施范围

如果希望尽快看到结构收益，建议第一轮只做：

1. Phase 0
2. Phase 1
3. Phase 2

这三阶段完成后，系统虽然功能上没有增加太多，但 run 执行架构已经从“进程内任务脚本”升级成“可扩展执行子系统”，后续开发成本会明显下降。

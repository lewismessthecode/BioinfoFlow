# 01 — 当前实现与验证后的发现

本文件基于当前代码而不是仅基于旧文档整理，目的是真正确认问题边界。

## 当前系统数据流

```text
POST /api/v1/runs
  -> app/api/v1/runs.py
  -> RunService.create_run()
  -> RunRepository.create()
  -> task_runner.submit(execute_run, run_id)
  -> execute_run()
  -> NextflowService.run() / MiniWDLService.run()
  -> _handle_run_event()
  -> publish_run_status / publish_run_log / publish_run_dag
  -> SSE frontend
```

## 已验证的优点

### 1. 输入和工作目录的路径安全做得比较好

- workspace 路径通过 `resolve()` 和 `is_relative_to()` 限制在项目根目录内。
- 参数和输入里看起来像路径的字段会做存在性检查和 glob 校验。

这意味着重构不应牺牲现有的安全边界。

### 2. 运行归档已经具备较好的复现基础

创建 run 时会把参数、inputs、config_overrides 和 resolved_runspec 存档到 `.bioinfoflow/{run_id}/inputs/` 下，并对 secret 做脱敏。

### 3. 事件和前端契约已经成型

`runtime/events.py` 的 envelope 和前端 SSE 消费链路已经稳定。重构应该复用这层，而不是推倒重来。

## 已验证的主要问题

### 1. `TaskRunner` 过于原始

当前 `runtime/task_runner.py` 只有：

- 固定 `max_concurrency=2`
- 进程内 `asyncio.Queue`
- 无持久化
- 无任务查询
- 无优先级
- 无背压

这意味着：

- 服务重启后无法恢复排队任务
- 大批量任务会被静默堆积
- 无法知道“队列里现在有什么”

### 2. `execute_run()` 仍然是系统中心

`runtime/jobs.py` 里的 `execute_run()` 负责：

- 切换 run 状态
- 加载 workflow/project
- 校验 workspace
- 生成 artifacts 路径
- 初始化 DAG
- Nextflow Docker/profile 逻辑
- Nextflow/WDL 分支选择
- 事件处理
- 错误状态收敛

这是当前最核心的耦合点。

### 3. 引擎服务没有共同抽象

现状：

- `NextflowService` 和 `MiniWDLService` 都直接管理子进程生命周期
- 都有独立的 `run()`、`cancel()`、输出解析逻辑
- 事件结构不一致
- resume 能力不一致

结果是 `jobs.py` 和 `run_service.py` 都必须知道引擎差异。

### 4. `Run.config` 已经承担了过多职责

当前 `Run.config` 同时存：

- 用户请求配置
- 解析后的路径
- runtime pid / engine / session_id
- DAG 数据
- 日志路径
- trace/dag 文件路径
- resume 标记

这会带来两个直接问题：

1. 更新局部 runtime 字段时要整体回写 JSON。
2. DAG 这种体积较大的数据和运行时细粒度状态绑在一起。

### 5. Workflow 校验和 schema 提取不稳定

当前 `WorkflowValidator`：

- WDL 优先用 `miniwdl` 解析
- Nextflow 主要靠正则和结构猜测

WDL 部分不算差，但 Nextflow 复杂 DSL2、多文件 include、nf-core 远程 schema 都不够稳。

### 6. DAG 运行时匹配脆弱

当前 DAG 节点匹配主要依赖：

- `clean_process_label()`
- `normalize_dag_id()`

规则过薄，只适合简单命名。复杂前缀、模块名、别名、运行时输出变体都可能匹配失败。

## V2 额外补充的发现

这些点在 V1 文档中提到不够明确，V2 需要补上。

### A. `task_runner` 不只服务 run

`ImageService.pull_image()` 也在使用 `task_runner.submit(...)`。因此不能简单把 `TaskRunner` 删除并假设所有异步后台工作都迁移到 run scheduler。

建议：

- 引入专用的 `RunScheduler`
- 保留一个轻量 `BackgroundTaskRunner` 给 image pull 等通用后台任务

### B. 启动恢复现在只是“标 stale 为 failed”

`recover_stale_runs()` 不是恢复调度，它只是把 `QUEUED` / `RUNNING` 且超时的 run 标记为 `FAILED`。

这意味着现阶段没有真正的任务恢复机制，只有启动时清理脏状态。

### C. Nextflow 的 Docker 处理逻辑埋在执行函数里

当前 Docker 可用性探测、`docker.enabled` 和 `docker.pull` 注入、profile 清空逻辑都在 `execute_run()` 的 Nextflow 分支里。这部分未来应进入 Nextflow adapter 或其 pre-submit hook。

### D. 事件处理和 DAG 更新有较高的 JSON 写放大

任务事件每来一次，就可能更新 `run.config["dag"]`、`run.config["runtime"]` 并 commit。短期可以接受，但如果任务数很多，会带来明显写放大。

### E. 当前 API 还没有为新能力预留输入字段

`RunCreate` 目前没有：

- `retry_policy`
- `timeout_seconds`
- `priority`
- `batch_id`

说明这些都是真正的新需求，不是现有能力只差一个 service。

## 当前实现的边界结论

### 当前适合承接的改造

1. 引擎抽象
2. 持久化 run scheduler
3. 超时、清理、审计
4. DAG/schema 能力提升

### 当前必须谨慎推进的改造

1. WDL resume
2. 资源感知调度
3. 大规模批量投递和通知

原因不是不能做，而是这些能力对“状态定义”和“执行语义”的要求更高。如果先做，容易放大底层耦合。

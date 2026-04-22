# Refactor-v4: Current State and Limitations

## Summary

当前调度器已经具备持久化队列、资源快照、重试/超时、状态恢复、审计与资源等待日志等基础能力，但资源判断的粒度仍然是 **run 级**，不是 **step/task 级**。

这意味着调度器只能回答“这条 run 现在能不能启动”，不能回答“这条 run 的某个轻量步骤现在能不能先跑，重步骤继续等”。对于生物信息学流程来说，这个限制会直接导致资源利用率偏低，尤其在多个 pipeline 同时排队时，小步骤无法穿插执行。

## Current Scheduler Behavior

### 1. 资源等待发生位置

当前资源等待发生在 `RunScheduler._wait_for_resources()`。

- 判断对象：整个 `run`
- 判断时机：worker 领取 `scheduled_tasks` 中的一条 run 后，在真正启动 engine 前
- 资源不足时行为：调用 `re_enqueue()`，设置 `delay_until`，等待下次轮询

当前日志事件 `scheduler.resource_wait` 体现的就是这个逻辑。

### 2. 资源需求来源优先级

当前资源需求估算来自 `ResourceEstimator.estimate()`，优先级如下：

1. `run.config.resources`
2. `run.config.request.resources`
3. `run.config.resolved.resources`
4. pipeline 名称模板推断
5. 默认 `medium`

当前模板大致为：

- `small`: `cpu=2`, `memory_gb=4`, `disk_gb=10`
- `medium`: `cpu=4`, `memory_gb=8`, `disk_gb=50`
- `large`: `cpu=8`, `memory_gb=16`, `disk_gb=100`
- `xlarge`: `cpu=16`, `memory_gb=32`, `disk_gb=200`
- `gpu`: `cpu=4`, `memory_gb=16`, `disk_gb=100`, `gpu=1`

### 3. 资源可用量判断

当前系统资源来源于 `ResourceMonitor` 的后台采样，调度器在判断时还会减去 safety margin：

- `scheduler_safety_cpu = 2`
- `scheduler_safety_memory_gb = 2.0`
- `scheduler_safety_disk_gb = 10.0`

因此日志里看到的：

- `required.cpu = 4`
- `available.cpu_available = 0.0`
- `required.memory_gb = 8.0`
- `available.memory_available_gb = 3.3`

在当前逻辑下必然无法满足，run 会持续排队重试。

## Workflow Schema Limitations

当前 `workflow.schema_json` 中的 `tasks[]` 仅包含：

- `name`
- `inputs`
- `outputs`
- `container`

不存在以下字段：

- `resources`
- `runtime`
- `scheduling_mode`
- `capabilities`

因此：

- Workflow 页面没有步骤资源配置入口是符合当前后端事实的
- DAG 页面也无法展示任务级资源声明
- 调度器也不可能从 workflow task 结构中推导步骤级资源需求

## Engine-Specific Limitations

### Nextflow

当前 Nextflow 运行路径的优点：

- 有 schema-based DAG fallback
- 有 `TASK_UPDATE` 实时事件
- 有 `trace.tsv` 可用于终态修复
- 有 `dag.dot` 可用于更好的 DAG 初始化

当前 Nextflow 运行路径的核心局限：

- 调度器只启动一个完整的 `nextflow run ...` 进程
- 应用层没有每个 process/task 的“执行令牌”
- 应用层无法在 task 将要启动前逐个放行

所以当前 Nextflow 虽然“看得见步骤”，但并不真正“控制步骤”。

### WDL

当前 WDL 运行路径的优点：

- 能提取 workflow/task/dependency 结构
- task 边界在 WDL AST 中是显式的
- WDL `runtime {}` 天然适合承载 `cpu/memory/disk/gpu`

当前 WDL 运行路径的局限：

- 运行时观测明显弱于 Nextflow
- 当前 `WDLAdapter.parse_event()` 基本只识别 `LOG / ERROR / COMPLETED`
- 没有可靠的 task-level 实时状态推进
- 当前也是整条 workflow 交给 `miniwdl run` 作为黑盒执行

所以当前 WDL 可以展示静态 DAG，但运行中的 DAG 状态更新能力较弱。

## Frontend / Product Misalignment

当前 UI 已经暴露了部分 persistent scheduler 能力，但还有明显错位。

### 已经反映到 UI 的能力

- scheduler mode / effective mode
- queue depth
- workers
- resource snapshot
- queued/dispatched/completed/failed 计数

### 还没有反映到 UI 的能力

- `scheduled_tasks.state`
- `attempt / max_attempts`
- `delay_until`
- `priority`
- `worker_id`
- `resource_shortages`
- `required_resources`
- engine capability 差异
- 调度模式差异（run-level vs step-level）

### 具体误导点

- Workflow 页面看起来像“步骤视图”，但没有步骤资源配置能力
- Scheduler 页面能看到系统资源，但看不到“哪个 run/step 因为什么资源在等待”
- Runs 页面只显示 queued/running/completed 等状态，没有解释 queued 的具体原因
- UI 没有告诉用户：当前 Nextflow 与 WDL 的调度能力并不一致

## Why Run-Level Admission Control Is Not Enough

对生物信息学流程而言，run 级 admission control 只能做保守保护，不能做高效资源编排。

例如：

- 初始化步骤：`1 CPU / 1 GB`
- 比对步骤：`8 CPU / 20 GB`

如果整个 run 以高水位资源需求被阻塞，那么：

- 初始化步骤也不能先执行
- 其他 run 的轻量步骤也可能被无谓延后
- 调度器无法跨多个 run 进行细粒度填充

这正是 v4 需要从 run 级调度升级到步骤级调度的根本原因。

## v4 Problem Statement

v4 要解决的问题不是“把资源模板做得更准”，而是：

1. 引入步骤级资源声明
2. 引入步骤级可执行队列
3. 让调度器在多个 run 的可执行步骤之间动态挑选
4. 对不同 engine 明确表达真实能力边界
5. 让前端诚实展示“当前是 run 级还是 step 级调度”

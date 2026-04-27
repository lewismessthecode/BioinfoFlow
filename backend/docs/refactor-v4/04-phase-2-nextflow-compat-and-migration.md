# Refactor-v4 Phase 2: Nextflow Compatibility and Migration

## Summary

Phase 2 不要求 Nextflow 立即具备真实的 step-level dispatch。

当前 Nextflow 路径的现实情况是：

- 运行时观测比 WDL 更强
- 但执行控制权仍然主要在 `nextflow run` 黑盒中

因此现阶段策略是：

1. 保留 Nextflow 的 run-level admission control
2. 把资源配置、调度状态、等待原因、模式差异完整暴露给 API 和 UI
3. 为后续迁移到 step-level scheduling 预留清晰接口与 capability

## Compatibility Goals

### 1. 不回退当前可用能力

必须保留：

- `TASK_UPDATE`
- `trace.tsv` 终态修复
- `dag.dot` 初始化
- cancel / retry / timeout / cleanup / audit 现有行为

### 2. 让 run-level 行为在产品上可解释

对于 Nextflow run，用户必须能直接看到：

- 当前调度模式：`run`
- 当前需要的资源：`required_resources`
- 当前可用资源：`resource_snapshot`
- shortage 原因：`resource_shortages`
- 下次重试时间：`delay_until`
- 当前队列状态：`scheduled_tasks.state`

### 3. 与 workflow task resources 对齐

即使第一阶段 Nextflow 不做真实 step-level dispatch，也要支持：

- workflow task resources 的查看
- workflow task resources 的编辑
- run 级资源覆盖

原因：

- 这些资源声明本身也是 workflow 元数据
- 后续迁移到 step-level scheduling 时可以复用

## API / Model Additions for Compatibility

### Workflow

Nextflow workflow 也需要具备：

- `scheduling_mode = run`
- `tasks[].resources`

### Run

Nextflow run 需要返回：

- `scheduler_mode = run`
- `scheduler_info`
  - `task_state`
  - `priority`
  - `attempt`
  - `max_attempts`
  - `delay_until`
  - `worker_id`
  - `required_resources`
  - `resource_shortages`
  - `resource_snapshot`
  - `wait_reason`

### Scheduler

新增 `GET /scheduler/blocked`，至少能列出：

- blocked run id
- mode
- shortages
- required vs available
- delay_until

## UI Alignment Requirements

Nextflow 兼容阶段最重要的是“诚实表达”。

### Workflow 页面

- 显示：
  - `Scheduling mode: Run-level`
  - task resources 已声明，但当前 Nextflow 不按 step queue 调度

### Runs 页面

- 对 queued 的 Nextflow run 显示：
  - `Waiting for CPU / memory / disk / GPU`
  - `Required vs available`
  - `Retry at ...`

### Scheduler 页面

- 区分：
  - blocked runs
  - blocked steps
- 对 Nextflow blocked item 显示 mode = `run`

## Migration Preconditions for Future Nextflow Step-Level Scheduling

如果后续要把 Nextflow 迁移到真实 step-level scheduling，至少需要满足：

1. 应用层能够在 task 级别获取更强的执行控制权
2. 调度器可在 task 启动前做放行
3. task 资源声明能可靠映射到实际运行单元
4. 事件模型能稳定回写到 step 实例

在这些前提不具备前，不应对外宣称 Nextflow 已支持真实步骤级调度。

## Migration Strategy

### Step 1

补 API 和 UI，对齐真实 run-level 行为。

### Step 2

把 workflow task resources 沉淀为结构化元数据，供未来迁移复用。

### Step 3

调研是否能引入新的 Nextflow execution control path，而不是继续完全依赖 `nextflow run` 黑盒。

### Step 4

只有在步骤控制权成立后，才把 `scheduling_mode` 从 `run` 迁移到 `step`。

## Success Criteria

- Nextflow 当前行为不回归
- UI 不再误导用户认为 Nextflow 已支持 step-level dispatch
- API 可以解释所有 queued/resource_wait 状态
- workflow task resources 能被展示和维护
- 后续迁移路径在代码结构上是可插拔的

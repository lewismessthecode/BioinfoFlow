# Refactor-v4 Phase 1: WDL Step-Level Scheduler

## Summary

Phase 1 的目标是在 `WDL` 路径上实现真正的步骤级动态调度。

这不是简单地给 WDL workflow 添加 `tasks[].resources` 字段，而是要把“调度对象”从 run 切换为 step，并且让资源不足只阻塞对应 step，而不是整条 run。

## Scope

### In Scope

- WDL task runtime 资源提取
- WDL workflow 默认 `scheduling_mode = step`
- run 创建时展开 step 实例
- scheduler 基于 step 领取与调度
- step 状态推进与 run 状态聚合
- run steps API

### Out of Scope

- Nextflow 真实 step-level dispatch
- project 级 task resources 覆盖
- 跨 engine 的完全统一 execution backend
- 高精度资源预测

## Data Model

建议新增 `run_steps` 表。

### Minimum Fields

- `id`
- `run_id`
- `step_key`
- `step_name`
- `state`
- `dependencies_json`
- `required_resources_json`
- `attempt`
- `max_attempts`
- `delay_until`
- `worker_id`
- `engine_payload_json`
- `started_at`
- `completed_at`
- `error_message`

### State Semantics

- `queued`: 还未满足依赖
- `ready`: 依赖满足，可以争抢资源
- `blocked`: 依赖满足，但资源不足
- `dispatched`: 已被 worker 领取
- `running`: step backend 已启动
- `completed`: 执行完成
- `failed`: 执行失败
- `cancelled`: 被取消

## Workflow Parsing and Resource Extraction

### Task Resource Sources

WDL task resources 第一阶段从以下位置提取：

- `runtime.cpu`
- `runtime.memory`
- `runtime.disks`
- `runtime.gpu` 或等价约定字段

如果 runtime 中没有资源声明，则写入默认值，且标记 `label = "default"`。

### Schema Storage

扩展 `workflow.schema_json.tasks[]`：

- `resources`

例如：

```json
{
  "name": "alignment",
  "inputs": ["reads"],
  "outputs": ["bam"],
  "container": "ubuntu:22.04",
  "resources": {
    "cpu": 8,
    "memory_gb": 20,
    "disk_gb": 50,
    "gpu": 0,
    "label": "declared"
  }
}
```

## Run Creation Flow

### New WDL Flow

1. 校验 project/workflow/binding
2. 创建 run 记录
3. 读取 workflow schema
4. 生成 step DAG
5. 为每个 task 创建 `RunStepInstance`
6. 将无前置依赖的 step 标记为 `ready`
7. 更新 run 为 `queued`

### Compatibility

若 WDL workflow 没有合法 DAG/task 结构：

- 可以拒绝进入 step-level scheduling
- 或降级为 run-level

Phase 1 推荐做法：

- 明确拒绝并返回可解释错误

因为 silent downgrade 会让产品语义变得不可信。

## Scheduler Worker Flow

### Step Claim

worker 从 step 队列中领取 `ready` step，而不是 run。

选择策略：

1. priority
2. created_at
3. step size fit

第一阶段不做复杂 bin-packing，采用“按优先级和就绪顺序选第一个满足资源约束的 step”即可。

### Resource Check

对每个 ready step：

1. 读取最新资源快照
2. 比较 `required_resources`
3. 若满足，发放 lease 并执行
4. 若不满足，将 step 标为 `blocked` 并设置 `delay_until`

### Completion

step 完成后：

1. 释放资源 lease
2. 标记 step `completed`
3. 检查依赖 DAG，推进后继 step 到 `ready`
4. 重新聚合 run 状态

## Execution Backend Strategy

### Important Constraint

现有 `miniwdl run` 是 workflow-level 黑盒执行，不适合直接承载 step-level dispatch。

因此 Phase 1 接受以下方向：

- 为 WDL 引入新的 step backend
- 或将 WDL 执行拆成“按 task/call 驱动”的应用层控制路径

### Principle

禁止为了追求“代码复用”而把真实步骤级调度继续包在 `miniwdl run` 黑盒外面假装实现。

只要调度器不能决定某个具体 step 何时启动，就不能称之为 step-level scheduling。

## Run Status Aggregation

### Rules

- 任一 step `running/dispatched` => `run.running`
- 所有 step `completed` => `run.completed`
- 任一不可恢复 step `failed` => `run.failed`
- 所有 ready step 都在等待资源 => `run.queued`

### UI-Oriented Derived Fields

对 run 还需要派生：

- `ready_steps`
- `blocked_steps`
- `running_steps`
- `completed_steps`
- `next_runnable_at`

## API Additions

### `GET /runs/{run_id}/steps`

返回：

- `run_id`
- `scheduler_mode`
- `items[]`
  - `step_key`
  - `step_name`
  - `state`
  - `dependencies`
  - `required_resources`
  - `attempt`
  - `delay_until`
  - `worker_id`
  - `error_message`

### `GET /runs/{run_id}/scheduler`

返回：

- `scheduler_mode`
- `summary`
  - `ready`
  - `blocked`
  - `running`
  - `completed`
- `blocked_reasons`
- `resource_snapshot`

## Tests

### Backend Unit Tests

- WDL runtime resources can be extracted from task runtime
- run creation expands step DAG into `run_steps`
- root steps are marked `ready`
- dependent steps stay queued until upstream completion
- resource shortage blocks only the current step
- small ready step from another run can still dispatch

### API Tests

- workflow returns task resources
- run returns `scheduler_mode = step`
- `/runs/{run_id}/steps` returns expanded queue
- `/runs/{run_id}/scheduler` returns summary and blocked reasons

### Integration Tests

- multiple WDL runs, mixed small/heavy steps
- heavy step blocked while small step continues

## Acceptance Criteria

- WDL workflow 能声明 task 级资源
- WDL run 创建后能展开为 step queue
- 调度器领取并执行 step 而非整条 run
- 资源不足只阻塞对应 step
- run 状态由 step 聚合得出
- 前端可以查看 WDL step queue 与 blocked reason

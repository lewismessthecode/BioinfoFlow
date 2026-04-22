# Refactor-v4: Frontend Alignment Plan

## Summary

前端在 v4 中的首要职责不是“美化调度页”，而是把后端真实能力诚实地表达出来。

v4 前端需要同时支持两种模式：

- `run-level scheduling`
- `step-level scheduling`

并且在 Workflow / Runs / Scheduler 三个页面上清晰展示：

- 当前 workflow/run 属于哪种模式
- 当前资源声明是什么
- 当前为什么在等
- 哪些等待是 step 级，哪些等待是 run 级

## Workflow Page

### Goals

- 展示 workflow 当前调度模式
- 支持 task resources 配置与回显
- 给出模式边界说明

### Required Changes

#### 1. Header / Overview

新增只读字段：

- `Scheduling mode`
- `Engine capability summary`

示例文案：

- `WDL · Step-level scheduling`
- `Nextflow · Run-level admission control`

#### 2. Tasks Tab

每个 task 展示：

- `container`
- `inputs`
- `outputs`
- `resources`

资源展示至少包括：

- CPU
- Memory
- Disk
- GPU
- Label

并提供编辑入口：

- 模板值
- 自定义值

#### 3. Explanatory Copy

必须明确写出：

- 对 WDL：这些 task resources 参与步骤级调度
- 对 Nextflow：这些 task resources 当前仅作为结构化声明与兼容数据，调度仍是 run 级

## Runs Page

### Goals

- 用户一眼看出 run 使用什么调度模式
- 用户能知道 queued 的具体原因
- step-level 模式下可查看 step 队列

### Required Changes

#### 1. Runs List Row

新增可见信息：

- `scheduler_mode`
- queued reason summary

示例：

- `Run-level · waiting for memory`
- `Step-level · 2 blocked / 1 running`

#### 2. Run Detail

新增 `Scheduling` 区块。

##### Run-Level 模式

展示：

- `required_resources`
- `resource_snapshot`
- `resource_shortages`
- `delay_until`
- `attempt / max_attempts`
- `worker_id`

##### Step-Level 模式

展示：

- `ready_steps`
- `blocked_steps`
- `running_steps`
- `completed_steps`
- blocked reasons
- step list / queue table

#### 3. Run Steps View

对于 step-level 模式，新增 tab 或 panel：

- step name
- state
- dependencies
- required resources
- delay_until
- worker_id
- error_message

## Scheduler Page

### Goals

- 从“系统概览页”升级为“调度解释页”
- 区分 blocked runs 与 blocked steps
- 区分资源瓶颈和普通排队

### Required Changes

#### 1. Summary Cards

新增：

- `blocked runs`
- `blocked steps`
- `step-level workflows`
- `run-level workflows`

#### 2. Blocked Items Panel

调用 `GET /scheduler/blocked` 后展示：

- item id
- run id
- mode
- shortages
- required vs available
- retry at

#### 3. Guidance Copy

文案必须明确区分：

- queue backlog
- worker saturation
- run-level resource wait
- step-level resource wait

## Copy and Labeling Requirements

禁止再使用会误导的统一表达。

必须避免：

- “步骤资源已全局支持”
- “所有 workflow 都支持 step scheduling”

推荐统一文案：

- `Run-level admission control`
- `Step-level scheduling`
- `Waiting for resources`
- `Blocked by dependency`
- `Blocked by CPU`
- `Blocked by memory`

## API Dependencies

前端实现依赖以下后端字段：

### Workflow

- `workflow.scheduling_mode`
- `workflow.schema_json.tasks[].resources`

### Run

- `run.scheduler_mode`
- `run.scheduler_info`

### Step

- `GET /runs/{run_id}/steps`

### Scheduler

- `GET /scheduler/blocked`

## Compatibility Rules

- 老 workflow 没有 `tasks[].resources` 时，页面展示 empty/default state
- 老 run 没有 `scheduler_info` 时，页面降级展示基础状态
- 页面逻辑只根据后端 mode/capability 字段分支，不自行猜 engine

## Acceptance Criteria

- Workflow 页面能配置并回显 task resources
- Workflow 页面能正确显示 mode 与说明文案
- Runs 页面能解释 queued/resource wait 原因
- Step-level run 能查看 step queue
- Scheduler 页面能列出 blocked runs/steps
- 所有文案都对能力边界保持诚实

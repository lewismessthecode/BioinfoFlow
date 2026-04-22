# Refactor-v4: Architecture Overview

## Summary

v4 将现有的“run queue + engine launch”结构扩展为“双模调度架构”：

- 对支持步骤级调度的 engine，调度对象是 `RunStepInstance`
- 对不支持步骤级调度的 engine，调度对象仍然是 `Run`

这要求我们把“调度策略”与“引擎能力”彻底分层，避免 engine 特例渗透到 API、前端和调度核心的每一处。

## Core Concepts

### Workflow Scheduling Mode

每个 workflow 需要有明确的 `scheduling_mode`：

- `run`
- `step`

该值决定：

- run 创建时生成什么队列单元
- scheduler worker 领取什么对象
- API/前端应该展示什么信息

### Engine Capability

每个 engine 需要显式声明 capability，而不是靠 scattered `if engine == ...` 推断：

- `supports_step_level_dispatch`
- `supports_runtime_step_events`
- `supports_step_resource_override`

第一阶段预期：

- `WDL`
  - `supports_step_level_dispatch = true`
  - `supports_runtime_step_events = partial/true`
  - `supports_step_resource_override = true`
- `Nextflow`
  - `supports_step_level_dispatch = false`
  - `supports_runtime_step_events = true`
  - `supports_step_resource_override = false` 或 limited

## New Core Objects

### 1. StepResourceRequirement

表示一个 task/step 的资源需求：

- `cpu`
- `memory_gb`
- `disk_gb`
- `gpu`
- `label`

来源：

- workflow task resources
- engine-specific runtime extraction
- run override（仅部分模式）

### 2. RunStepInstance

表示一次具体 run 中的一个可调度步骤实例。

建议字段：

- `id`
- `run_id`
- `step_key`
- `step_name`
- `state`
- `dependencies`
- `required_resources`
- `attempt`
- `max_attempts`
- `delay_until`
- `worker_id`
- `engine_payload`
- `started_at`
- `completed_at`
- `error_message`

### 3. StepDispatchLease

表示调度器把一份资源窗口临时授予某个 step 的记录。

第一阶段可以作为内存态/逻辑对象存在，不一定必须落数据库表；但语义上要明确：

- 哪个 worker 持有 lease
- 该 lease 关联哪个 step
- 占用哪些资源
- 何时释放

## Dual-Mode Scheduling Model

### Run-Level Path

适用于：

- 当前 Nextflow
- 任何暂不支持步骤级控制的 engine

行为：

1. run 入队
2. worker 领取 run
3. 基于 run 级需求做资源判断
4. 满足则启动完整 engine 进程
5. 不满足则 `re_enqueue + delay_until`

### Step-Level Path

适用于：

- v4 Phase 1 的 WDL

行为：

1. run 创建成功
2. 把 workflow DAG 展开为 step 实例
3. scheduler 从所有 ready steps 中选取可执行项
4. 为每个 step 分配资源窗口
5. 执行 step
6. 更新依赖图，释放后继 step
7. 聚合 run 状态

## Scheduler State Machine

### Run-Level

- `queued`
- `dispatched`
- `completed`
- `failed`
- `cancelled`

### Step-Level

run 状态仍保留上述集合，但内部 step 需要独立状态机：

- `queued`
- `ready`
- `blocked`
- `dispatched`
- `running`
- `completed`
- `failed`
- `cancelled`

其中：

- `queued`: 已创建但尚未满足依赖
- `ready`: 依赖满足，可尝试调度
- `blocked`: 依赖满足，但当前资源不足

## Aggregation Rules

step-level 模式下，run 状态由 step 聚合得到：

- 任意 step 处于 `running/dispatched` => `run.running`
- 全部 step 完成 => `run.completed`
- 任意关键 step 失败且不可恢复 => `run.failed`
- 用户取消 => `run.cancelled`
- 尚未有 step 开始执行但已展开 => `run.queued`

## Data Flow Overview

### Workflow Registration

1. 验证 workflow
2. 提取 schema
3. 提取 task resources
4. 设定默认 `scheduling_mode`
5. 存储 workflow

### Run Creation

#### Run-Level

1. 创建 run
2. 创建/更新 `scheduled_tasks`
3. run 入队

#### Step-Level

1. 创建 run
2. 解析 workflow DAG
3. 创建 `run_steps`
4. 计算初始 ready steps
5. ready steps 入队

### Worker Dispatch

#### Run-Level

1. claim run task
2. 资源检查
3. 启动 engine

#### Step-Level

1. claim ready step
2. 资源检查
3. 分配 lease
4. 启动 step backend
5. 完成后释放 lease
6. 解锁后继 step

## API Surface

v4 的 API 需要围绕“双模”提供统一视图：

- workflow:
  - `scheduling_mode`
  - `tasks[].resources`
- run:
  - `scheduler_mode`
  - `scheduler_info`
- step:
  - `GET /runs/{run_id}/steps`
- scheduler:
  - `GET /scheduler/blocked`

## Frontend Contract

前端不应自行猜测 engine 是否支持 step-level scheduling。

必须只依赖后端暴露的：

- `workflow.scheduling_mode`
- `run.scheduler_mode`
- `engine capabilities` 或派生字段

## Migration Principles

v4 架构必须支持：

1. 现有 run-level 路径不回归
2. 新增 step-level 路径不污染老路径
3. 后续可以把更多 engine 从 run-level 迁移到 step-level

因此关键原则是：

- capability 分层
- mode-driven API
- queue item 抽象清晰
- 不把 engine 细节散落到页面和服务中

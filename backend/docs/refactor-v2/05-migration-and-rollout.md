# 05 — 迁移与上线策略

本文件关注“怎么改而不把现有系统打断”。

## 迁移总原则

1. 优先做兼容式引入，不做一次性替换。
2. 每个阶段尽量保留旧接口，先替换内部实现。
3. 先建立新抽象，再迁移调用方。
4. 每次迁移都要有回归测试和可回滚点。

## 迁移对象拆分

### A. runs 执行链路

这是重构主目标，应迁移到：

- `RunScheduler`
- `ExecutionBackend`
- `EngineAdapter`

### B. generic background tasks

例如 image pull。

这类任务不应强行进入 run scheduler。建议保留轻量后台任务器，例如：

```text
runtime/background_tasks.py
```

这能避免：

- 把 Docker image pull 的状态机混入 run scheduler
- 为了 run 的持久化调度，连带重写所有后台任务

## 推荐迁移顺序

### 步骤 1: 先抽 dispatch seam

先把 `RunService` 里直接调用 `task_runner.submit(execute_run, run_id)` 的位置收口成统一 dispatch 接口。

目标：

- 不改 API
- 不改外层行为
- 只是让 dispatch 从“硬编码调用”变成“可替换依赖”

### 步骤 2: 引入 engine 抽象，但仍可复用当前执行路径

先让 Nextflow/WDL 行为进入 adapter/backend 层，再逐步把 `jobs.py` 中逻辑收缩。

### 步骤 3: 引入持久化 scheduler

当 run 的执行请求已经可以通过统一接口表达后，再切换调度器。

### 步骤 4: 将 retry/timeout/cleanup 等放入 scheduler 周边

这样这些能力都会围绕 scheduler 展开，而不是继续散落在 service 和 jobs 里。

## 数据迁移建议

### 1. 新表优先，旧表兼容

建议按下面顺序建表：

1. `scheduled_tasks`
2. `audit_logs`
3. `batches`
4. `batch_runs`
5. `notification_configs`

所有新表都应是增量引入，不要求修改现有 `runs` 表的核心字段语义。

### 2. `Run.config` 采用平滑迁移

建议：

1. 增加 `config_schema_version`
2. 新代码优先写入新的命名空间结构
3. 读取时兼容旧 key
4. 在多个阶段后再考虑删除旧 key

不建议：

- 一次 migration 扫所有历史 run 去重写 JSON

## API 迁移策略

### 保持兼容

这些接口应保持可用：

- `POST /runs`
- `POST /runs/{id}/cancel`
- `POST /runs/{id}/resume`
- `POST /runs/{id}/retry`
- `GET /runs/{id}`
- `GET /runs/{id}/logs`
- `GET /runs/{id}/dag`

### 增量扩展

当新增字段时，建议使用向后兼容方式：

```json
{
  "retry_policy": {
    "max_retries": 2,
    "delay_seconds": 30,
    "backoff_multiplier": 2.0,
    "retry_on": ["timeout", "oom"]
  },
  "timeout_seconds": 86400
}
```

旧客户端不传也应继续工作。

## SSE 兼容策略

### 保持现有事件

必须继续支持：

- `run.status`
- `run.log`
- `run.dag`

### 允许新增事件

例如：

- `scheduler.status`
- `scheduler.task`
- `run.audit`

但新增事件不应替代现有前端依赖的 run 事件。

## 风险控制建议

### 1. 建议增加 feature flag

例如：

```text
run_scheduler_mode = legacy | persistent
```

用途：

- 先上线 engine abstraction
- 再灰度切换到持久化 scheduler

如果项目不希望增加显式 feature flag，也至少要保证切换点集中在一个地方。

### 2. 每阶段都要有回退策略

例如：

- Phase 1 回退到旧 service 调用
- Phase 2 回退到 legacy dispatch

### 3. 不要在同一阶段同时改“调度”和“前端事件语义”

否则出了问题时很难定位是调度问题还是 UI 兼容问题。

## 测试策略

### Characterization tests

重构前先固化现有关键行为：

1. create run -> queued
2. execute run -> running -> completed/failed
3. cancel run
4. resume run for Nextflow
5. retry run
6. SSE run.status / run.log / run.dag

### New tests

新阶段建议分别补：

1. engine tests
2. scheduler tests
3. recovery tests
4. retry tests
5. timeout tests
6. cleanup tests
7. DAG matcher / schema extractor tests

### 回归重点

1. 现有 `test_runs.py`
2. 与 workflow registration / schema_json 相关测试
3. image pull 相关测试

最后一点很重要，因为 run 调度器改造不应误伤 image pull 的后台逻辑。

## 上线建议

### 推荐顺序

1. 先合入 Phase 0 和 Phase 1
2. 在测试环境启用新 adapter/backend
3. 再合入 Phase 2 并切换 run dispatch
4. 观察 queued/running/completed/cancelled 状态收敛
5. 再逐步增加 retry、timeout、cleanup

### 不推荐的顺序

不建议：

1. 先上 batch
2. 先上 resource-aware scheduling
3. 先承诺 WDL 完整 resume

这些都会在底层边界不稳时扩大问题面。

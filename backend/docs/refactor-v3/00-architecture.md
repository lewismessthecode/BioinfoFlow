# V3 — 分析与调度层重构：架构总览

## 一句话结论

当前 run 执行链路的核心问题是**职责耦合** — `RunService`, `TaskRunner`, `jobs.py`, 引擎服务之间缺少清晰边界。本次重构将其收敛成一个四层可扩展子系统，同时保持现有 API 和前端兼容。

## 决策前提

| 项 | 决策 | 理由 |
|----|------|------|
| 引擎 | Nextflow (主) + WDL (辅) | 引擎抽象层边际成本低，覆盖更广用户群 |
| 部署 | 先 Local, 预留 SSH/Cloud 接口 | 降低初期复杂度 |
| 调度 | 单进程单实例 DB-backed scheduler | SQLite 在此前提下成立 |
| Cromwell | 不接入 | 保持 Python 单体架构简洁 |
| WDL Resume | best-effort restart assist (非强保证) | MiniWDL 无 call-caching |
| Run.config | 收口命名空间 + schema version, 不拆表 | 止住无序增长即可 |
| TaskRunner | 保留给 image pull 等非 run 任务 | run scheduler 和通用后台任务需求不同 |
| Scope 外 | Agent 自动串流程, DAG drag-and-drop | 后续 worktree |

## 强保证 vs Best-effort

| 强保证 | Best-effort |
|--------|-------------|
| Run 状态转换合法性 | WDL resume (restart assist) |
| 持久化队列不因重启丢失 | 资源估算与管线模板映射 |
| Nextflow native resume | 运行时 DAG 动态补全 |
| Timeout 到期自动 cancel | Webhook 通知交付 |
| API/SSE 向后兼容 | OOM 自动扩容重试 |

## 目标架构

```
API /runs
  → RunService (验证 + 归档 + 入队)
    → RunScheduler (持久化优先级队列, 可恢复)
      → ExecutionBackend (Local first)
        → EngineAdapter (Nextflow / WDL)
          → EngineEvent (统一事件流)
            → RunEventHandler (状态 + DAG + 日志 + SSE)
```

### 模块边界

| 层 | 职责 | 不负责 |
|----|------|--------|
| **RunService** | 参数验证, run 记录, 归档, 入队/取消/查询 | 引擎命令, 事件解析, 调度重试 |
| **RunScheduler** | 持久化队列, 并发控制, 优先级, 启动恢复, 重试, timeout | 引擎细节 |
| **ExecutionBackend** | 进程启动, stdout/stderr drain, 进程取消 | 调度策略 |
| **EngineAdapter** | 命令构建, 事件解析, resume/cancel/schema | 进程管理 |
| **BackgroundTaskRunner** | image pull 等通用后台任务 | run 执行 |

### 目标目录

```
backend/app/
  engine/
    __init__.py
    backend.py           # ExecutionBackend ABC + EngineEvent
    adapter.py           # EngineAdapter ABC
    local.py             # LocalBackend
    registry.py          # engine → adapter mapping
    adapters/
      __init__.py
      nextflow.py        # NextflowAdapter
      wdl.py             # WDLAdapter
  scheduler/
    __init__.py
    config.py            # SchedulerConfig
    models.py            # ScheduledTask model
    queue.py             # DB-backed queue
    scheduler.py         # RunScheduler
    retry.py             # RetryPolicy + RetryEvaluator
    timeout.py           # TimeoutWatcher
    cleanup.py           # WorkDirCleaner
    hooks.py             # RunCompletionHooks
    resources.py         # ResourceRequirements + Checker
    monitor.py           # ResourceMonitor (psutil)
  runtime/
    events.py            # EventBus (保持不变)
    background_tasks.py  # 轻量后台任务器 (image pull 等)
```

### Run.config 命名空间

```json
{
  "config_schema_version": 1,
  "request": { "params": {}, "inputs": {}, "config_overrides": {} },
  "resolved": { "runspec": {} },
  "runtime": { "engine": "", "pid": null, "resume_token": null, "artifacts": {} },
  "policy": { "retry": {}, "timeout_seconds": null },
  "ui": { "dag": {} }
}
```

## 交付阶段

```
Phase 0: Baseline and seams              ← 安全网
Phase 1: Engine abstraction              ← 基础层
Phase 2: Persistent run scheduler        ← 基础层
Phase 3: Retry / timeout / ops baseline  ← 降低风险
Phase 4: DAG and schema improvements     ← 提升体验
Phase 5: Resource-aware scheduling       ← 效率优化
Phase 6: Batch submission + notifications ← 规模化
```

依赖:
```
Phase 0 → Phase 1 → Phase 2 → Phase 3
                             → Phase 4
                             → Phase 5
                             → Phase 6
```

**推荐首批**: Phase 0 + 1 + 2。完成后 run 执行架构从"进程内脚本"升级为"可扩展子系统"。

## 迁移策略

1. **兼容式引入**: 先建新抽象，再迁移调用方
2. **Feature flag**: `run_scheduler_mode = legacy | persistent` 控制调度器切换
3. **渐进回退**: 每个 phase 都有回退路径
4. **不同时改调度和事件语义**: 出问题时能快速定位

## 非功能约束

| 约束 | 标准 |
|------|------|
| 新代码测试覆盖率 | ≥ 80% |
| 单文件行数 | ≤ 400行 (推荐), ≤ 800行 (硬上限) |
| 单函数行数 | ≤ 50行 |
| 外部依赖 | 不引入 Redis/RabbitMQ/Celery/Cromwell |
| API 兼容 | 现有端点不破坏, 新增端点不影响旧前端 |
| SSE 兼容 | 保持 run.status/run.log/run.dag, 可新增事件类型 |

# Phase 2 — Persistent Run Scheduler

**依赖**: Phase 1 (引擎抽象)
**被依赖**: Phase 3, 4, 5, 6

## 目标

将 runs 从内存 FIFO 迁移到 DB-backed scheduler。**只迁移 run 执行链路。** image pull 等保留在 `BackgroundTaskRunner`。

## 新增文件

```
backend/app/scheduler/
├── __init__.py
├── config.py           # SchedulerConfig
├── models.py           # ScheduledTask model
├── queue.py            # DB-backed priority queue
└── scheduler.py        # RunScheduler
```

## 核心设计

### ScheduledTask Model

```python
# scheduler/models.py
class TaskPriority(str, Enum):
    URGENT = "urgent"   # resume/retry 触发
    NORMAL = "normal"   # 默认
    LOW = "low"         # 批量投递中的低优先级

class TaskState(str, Enum):
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ScheduledTask(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scheduled_tasks"
    run_id: Mapped[str] = mapped_column(String(50), ForeignKey("runs.run_id"), index=True)
    state: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    worker_id: Mapped[str | None] = mapped_column(String(50))
```

### SchedulerConfig

```python
# scheduler/config.py
@dataclass
class SchedulerConfig:
    max_concurrency: int = 4
    max_queue_depth: int = 500
    poll_interval_seconds: float = 1.0
    stale_timeout_minutes: int = 30
```

### RunScheduler

```python
# scheduler/scheduler.py
class RunScheduler:
    """Persistent run scheduler. Single-instance, DB-backed."""

    def __init__(self, config: SchedulerConfig, backend: ExecutionBackend):
        self._config = config
        self._backend = backend
        self._queue = TaskQueue()
        self._semaphore: asyncio.Semaphore
        self._workers: list[asyncio.Task] = []

    async def start(self):
        await self.recover()
        self._semaphore = asyncio.Semaphore(self._config.max_concurrency)
        for i in range(self._config.max_concurrency):
            self._workers.append(asyncio.create_task(self._worker(i)))

    async def stop(self):
        # cancel workers, await completion

    async def enqueue(self, run_id: str, *, priority: str = "normal") -> ScheduledTask:
        depth = await self._queue.depth()
        if depth >= self._config.max_queue_depth:
            raise QueueFullError(...)
        return await self._queue.enqueue(run_id, priority=priority)

    async def cancel(self, run_id: str) -> bool:
        # QUEUED → mark cancelled; DISPATCHED → backend.cancel()

    async def recover(self):
        # DISPATCHED 超过 stale_timeout → re-enqueue 或 mark failed

    async def get_status(self) -> dict:
        # queue depth, worker count, state counts

    async def _worker(self, worker_id: int):
        while self._running:
            task = await self._queue.dequeue()
            if not task:
                await asyncio.sleep(self._config.poll_interval_seconds)
                continue
            async with self._semaphore:
                await self._execute_task(task, worker_id)

    async def _execute_task(self, task, worker_id):
        await self._queue.mark_dispatched(task.id, f"worker-{worker_id}")
        try:
            # Load run, workflow, project from DB
            # Get adapter, call backend.submit()
            # Handle EngineEvent stream → update run status/dag/logs
            await self._queue.mark_completed(task.id)
        except Exception as exc:
            await self._queue.mark_failed(task.id, str(exc))
```

### TaskQueue (DB-backed)

```python
# scheduler/queue.py
class TaskQueue:
    async def enqueue(self, run_id, priority) -> ScheduledTask: ...
    async def dequeue(self) -> ScheduledTask | None:
        # SELECT state='queued' ORDER BY priority_rank ASC, created_at ASC LIMIT 1
        # priority_rank: urgent=0, normal=1, low=2
    async def depth(self) -> int: ...
    async def cancel(self, run_id) -> bool: ...
    async def mark_dispatched(self, task_id, worker_id): ...
    async def mark_completed(self, task_id): ...
    async def mark_failed(self, task_id, error): ...
    async def get_stale(self, timeout_minutes) -> list[ScheduledTask]: ...
```

> **SQLite note**: 不支持 `FOR UPDATE SKIP LOCKED`。当前单进程单实例，使用事务内 SELECT + UPDATE。迁移 PostgreSQL 时再启用行锁。

### RunDispatcher 集成

Phase 0 的 `RunDispatcher` 接口获得新实现:

```python
# services/run_dispatch.py (扩展)
class SchedulerDispatcher:
    def __init__(self, scheduler: RunScheduler):
        self._scheduler = scheduler

    def dispatch(self, run_id: str, *, priority: str = "normal") -> None:
        # schedule async enqueue (use asyncio.create_task to avoid blocking)
        asyncio.create_task(self._scheduler.enqueue(run_id, priority=priority))
```

### Feature Flag

```python
# config.py
run_scheduler_mode: str = "persistent"  # "legacy" | "persistent"
scheduler_max_concurrency: int = 4
scheduler_max_queue_depth: int = 500
scheduler_poll_interval: float = 1.0
scheduler_stale_timeout_minutes: int = 30
```

`main.py` startup:
```python
if settings.run_scheduler_mode == "persistent":
    dispatcher = SchedulerDispatcher(run_scheduler)
else:
    dispatcher = LegacyDispatcher()
```

## DB Migration

```sql
CREATE TABLE scheduled_tasks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    state TEXT NOT NULL DEFAULT 'queued',
    priority TEXT NOT NULL DEFAULT 'normal',
    attempt INTEGER NOT NULL DEFAULT 1,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    dispatched_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    worker_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX ix_scheduled_tasks_dequeue ON scheduled_tasks(state, priority, created_at);
CREATE INDEX ix_scheduled_tasks_run_id ON scheduled_tasks(run_id);
```

## 重构现有文件

| 文件 | 变更 |
|------|------|
| `config.py` | 新增 scheduler 配置项 |
| `main.py` | startup: 创建 RunScheduler; shutdown: stop |
| `services/run_service.py` | 构造函数接收 dispatcher (Phase 0 已准备) |
| `services/run_dispatch.py` | 新增 SchedulerDispatcher |
| `runtime/jobs.py` | `execute_run()` 逻辑迁入 `RunScheduler._execute_task()` |
| `api/v1/runs.py` | 注入 dispatcher |

### `runtime/jobs.py` 的演变

- `execute_run()` 的核心逻辑迁入 `RunScheduler._execute_task()`
- `recover_stale_runs()` 迁入 `RunScheduler.recover()`
- `_handle_engine_event()`, `_update_dag_task_status()`, `_finalize_dag_statuses()` 等保留为独立函数，供 scheduler 调用
- `jobs.py` 变成一个薄 wrapper (兼容 legacy mode)

## API 新增

```python
# api/v1/scheduler.py
@router.get("/scheduler/status")
async def scheduler_status():
    return success_response({
        "mode": settings.run_scheduler_mode,
        "workers": scheduler.config.max_concurrency,
        "queue_depth": await scheduler.queue_depth(),
        "states": await scheduler.state_counts(),
    })
```

## 测试计划

```
backend/tests/test_scheduler/
├── __init__.py
├── test_scheduler.py      # 生命周期, enqueue/cancel/recover
├── test_queue.py           # DB queue 操作, 优先级排序
├── test_concurrency.py     # 并发控制 (semaphore)
└── test_recovery.py        # stale task 恢复
```

### 关键测试用例

1. enqueue 3 tasks → dequeue 按 priority + created_at 顺序
2. max_concurrency=2, 5 tasks → 同时只有 2 个 dispatched
3. max_queue_depth=3, 4th enqueue → QueueFullError
4. stop + restart → queued tasks 仍在
5. dispatched task 超时 → recover 标记 failed
6. cancel queued → state=cancelled; cancel dispatched → backend.cancel()
7. feature flag legacy → 使用 LegacyDispatcher

### 回归

- `test_runs.py` 全部通过 (monkeypatch scheduler.enqueue)
- `test_run_lifecycle.py` 全部通过
- `test_images.py` 通过 (image pull 不受影响)

## 验收标准

- [ ] Run create/resume/retry 通过 RunScheduler.enqueue()
- [ ] 服务重启后 queued task 不丢失
- [ ] 并发数可配置
- [ ] `GET /scheduler/status` 返回队列状态
- [ ] Feature flag 可切回 legacy mode
- [ ] 现有测试全部通过
- [ ] 新代码覆盖率 ≥ 80%

# Plan 02 — 调度器核心

**依赖**: plan-01 (引擎抽象层)
**被依赖**: plan-03, plan-06, plan-07

## 目标

替换 `TaskRunner` (62行内存FIFO)，实现持久化优先级调度器，支持可配置并发、启动恢复、队列背压。

## 架构设计

```
┌────────────────────────────────────────────┐
│                RunService                   │
│  create_run() → scheduler.enqueue(task)    │
└──────────────────┬─────────────────────────┘
                   ▼
┌────────────────────────────────────────────┐
│              Scheduler                      │
│  ┌────────────┐  ┌──────────┐  ┌────────┐ │
│  │ TaskQueue   │  │ Workers  │  │ Config │ │
│  │ (DB-backed) │  │ (async)  │  │        │ │
│  └─────┬──────┘  └────┬─────┘  └────────┘ │
│        │ dequeue       │ execute            │
│        └───────────────┘                    │
├────────────────────────────────────────────┤
│  start() / stop() / enqueue() / cancel()   │
│  get_status() / recover()                   │
└──────────────────┬─────────────────────────┘
                   ▼
┌────────────────────────────────────────────┐
│         ExecutionBackend (plan-01)          │
│  backend.submit(adapter, config, workspace)│
└────────────────────────────────────────────┘
```

## 新增文件

```
backend/app/scheduler/
├── __init__.py
├── scheduler.py        # Scheduler 主类
├── models.py           # ScheduledTask SQLAlchemy model
├── queue.py            # DB-backed priority queue operations
└── config.py           # SchedulerConfig dataclass
```

## 详细设计

### 1. ScheduledTask Model (DB持久化)

```python
# scheduler/models.py
class TaskPriority(str, Enum):
    URGENT = "urgent"    # 用户手动触发的 resume/retry
    NORMAL = "normal"    # 默认
    LOW = "low"          # 批量投递中的低优先级任务

class TaskState(str, Enum):
    QUEUED = "queued"
    DISPATCHED = "dispatched"  # 已发给 worker, 正在执行
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ScheduledTask(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scheduled_tasks"

    run_id: str              # FK → runs.run_id
    state: TaskState         # 任务状态
    priority: TaskPriority   # 优先级
    attempt: int             # 当前重试次数
    max_attempts: int        # 最大重试次数 (from RetryPolicy)
    dispatched_at: datetime  # worker 开始执行的时间
    completed_at: datetime
    error_message: str | None
    worker_id: str | None    # 哪个 worker 在执行
```

### 2. SchedulerConfig

```python
# scheduler/config.py
@dataclass
class SchedulerConfig:
    max_concurrency: int = 4           # 从 config.py 读取
    max_queue_depth: int = 500         # 背压上限
    poll_interval_seconds: float = 1.0 # worker 轮询间隔
    stale_task_timeout_minutes: int = 30
```

### 3. Scheduler 主类

```python
# scheduler/scheduler.py
class Scheduler:
    def __init__(self, config: SchedulerConfig, backend: ExecutionBackend):
        self._config = config
        self._backend = backend
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._workers: list[asyncio.Task] = []
        self._running = False

    async def start(self):
        """启动 scheduler: 恢复 stale tasks + 启动 worker pool."""
        await self.recover()
        self._running = True
        for i in range(self._config.max_concurrency):
            self._workers.append(asyncio.create_task(self._worker(i)))

    async def stop(self):
        """优雅停止: 等待当前执行完成, 取消等待中的任务."""

    async def enqueue(self, run_id: str, *, priority: TaskPriority = TaskPriority.NORMAL) -> ScheduledTask:
        """入队: 检查背压 → 创建 ScheduledTask → 唤醒 worker."""
        # 背压检查
        queue_depth = await self._queue.depth()
        if queue_depth >= self._config.max_queue_depth:
            raise QueueFullError(f"Queue full: {queue_depth}/{self._config.max_queue_depth}")
        # 持久化
        task = await self._queue.enqueue(run_id, priority=priority)
        return task

    async def cancel(self, run_id: str) -> bool:
        """取消: QUEUED → 直接标记; DISPATCHED → 委托 backend.cancel()."""

    async def recover(self):
        """启动恢复: DISPATCHED 超时的任务 → 标记 FAILED 或重新入队."""

    async def get_status(self) -> dict:
        """返回调度器状态: 队列深度, worker数, 各状态计数."""

    async def _worker(self, worker_id: int):
        """Worker 循环: dequeue → acquire semaphore → execute → release."""
        while self._running:
            task = await self._queue.dequeue()
            if not task:
                await asyncio.sleep(self._config.poll_interval_seconds)
                continue
            async with self._semaphore:
                await self._execute_task(task, worker_id)

    async def _execute_task(self, task: ScheduledTask, worker_id: int):
        """执行单个任务: 更新状态 → 调用 backend → 处理结果."""
```

### 4. DB-backed Queue

```python
# scheduler/queue.py
class TaskQueue:
    """Priority queue backed by scheduled_tasks table."""

    async def enqueue(self, run_id: str, priority: TaskPriority) -> ScheduledTask:
        """INSERT with QUEUED state."""

    async def dequeue(self) -> ScheduledTask | None:
        """SELECT ... ORDER BY priority ASC, created_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED."""
        # priority: urgent(0) < normal(1) < low(2) → urgent 先出队

    async def depth(self) -> int:
        """COUNT where state = QUEUED."""

    async def cancel(self, run_id: str) -> bool:
        """Update state to CANCELLED if QUEUED."""

    async def mark_dispatched(self, task_id: str, worker_id: str):
        """Update state to DISPATCHED + dispatched_at."""

    async def mark_completed(self, task_id: str):
        """Update state to COMPLETED + completed_at."""

    async def mark_failed(self, task_id: str, error: str):
        """Update state to FAILED + error_message."""

    async def get_stale_tasks(self, timeout_minutes: int) -> list[ScheduledTask]:
        """DISPATCHED tasks older than timeout."""
```

> **Note**: SQLite 不支持 `FOR UPDATE SKIP LOCKED`。使用 `SELECT + UPDATE` 在事务中操作。由于当前是单进程 (多个 asyncio worker 共享一个进程)，不会有真正的并发竞争。当迁移到 PostgreSQL 时再启用行锁。

## 重构现有文件

### `runtime/task_runner.py`
- 删除 `TaskRunner` 类和 `task_runner` 全局实例
- 用 `Scheduler` 实例替代

### `runtime/jobs.py`
- `execute_run()` 被拆分:
  - 引擎调用部分 → `Scheduler._execute_task()` 内部调用 `ExecutionBackend.submit()`
  - 事件处理部分 → 保留 `_handle_engine_event()` (适配 EngineEvent)
  - DAG初始化/更新 → 保留
- `recover_stale_runs()` → 迁移到 `Scheduler.recover()`

### `services/run_service.py`
- `create_run()` (run_service.py:126-196):
  - `task_runner.submit(execute_run, run.run_id)` → `scheduler.enqueue(run.run_id)`
- `cancel_run()` (run_service.py:401-435):
  - 增加 `scheduler.cancel(run_id)` 调用 (取消队列中的任务)
- `resume_run()` / `retry_run()`:
  - 同样替换为 `scheduler.enqueue()`

### `main.py`
- startup: `task_runner.start()` → `scheduler.start()`
- shutdown: `task_runner.stop()` → `scheduler.stop()`

### `config.py`
新增配置项:
```python
scheduler_max_concurrency: int = 4
scheduler_max_queue_depth: int = 500
scheduler_poll_interval: float = 1.0
scheduler_stale_timeout_minutes: int = 30
```

## DB Migration

```python
# alembic migration
def upgrade():
    op.create_table("scheduled_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(50), sa.ForeignKey("runs.run_id"), nullable=False, index=True),
        sa.Column("state", sa.String(20), nullable=False, default="queued", index=True),
        sa.Column("priority", sa.String(20), nullable=False, default="normal"),
        sa.Column("attempt", sa.Integer, nullable=False, default=1),
        sa.Column("max_attempts", sa.Integer, nullable=False, default=1),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text),
        sa.Column("worker_id", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_scheduled_tasks_dequeue", "scheduled_tasks", ["state", "priority", "created_at"])
```

## API 新增

```python
# api/v1/scheduler.py
@router.get("/scheduler/status")
async def scheduler_status():
    """返回调度器状态"""
    return success_response(await scheduler.get_status())
```

返回:
```json
{
    "workers": 4,
    "queue_depth": 12,
    "dispatched": 3,
    "completed_total": 156,
    "failed_total": 8
}
```

## 测试计划

### 新增测试文件

```
backend/tests/test_scheduler/
├── __init__.py
├── test_scheduler.py          # Scheduler 生命周期
├── test_queue.py              # DB queue 操作
├── test_concurrency.py        # 并发控制
└── test_recovery.py           # stale task 恢复
```

### 关键测试用例

1. **enqueue + dequeue**:
   - 入队 3 个任务 → dequeue 按 priority + created_at 顺序出队
   - urgent 优先于 normal

2. **并发控制**:
   - max_concurrency=2, 入队 5 个任务 → 同时只有 2 个在执行

3. **背压**:
   - max_queue_depth=3, 入队 4 个 → 第4个抛 QueueFullError

4. **持久化恢复**:
   - 入队 3 个任务 → 模拟 scheduler stop → 重新 start → 3 个任务仍在队列

5. **stale task 恢复**:
   - DISPATCHED 任务超过 timeout → recover() 标记 FAILED

6. **cancel**:
   - cancel QUEUED 任务 → 状态变 CANCELLED
   - cancel DISPATCHED 任务 → 调用 backend.cancel()

7. **回归**:
   - 现有 `test_runs.py` 全部通过 (monkeypatch scheduler.enqueue)

## 验收标准

- [ ] `TaskRunner` 被完全替换
- [ ] 调度器状态通过 API 可查询
- [ ] 并发数可配置 (environment variable)
- [ ] 服务重启后 QUEUED 任务不丢失
- [ ] 现有 API 测试全部通过
- [ ] 新代码覆盖率 ≥ 80%

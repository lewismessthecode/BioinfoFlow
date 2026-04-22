# Plan 07 — 批量投递 + 通知机制

**依赖**: plan-02 (调度器核心)
**被依赖**: 无

## 目标

支持一次投递多个分析任务，批次级别的状态查询和操作，以及完成/失败时的 webhook 通知。

## 新增文件

```
backend/app/models/
├── batch.py              # Batch model
└── notification.py       # NotificationConfig model

backend/app/services/
├── batch_service.py      # BatchService
└── notification_service.py  # NotificationService

backend/app/api/v1/
└── batch.py              # 批量投递 API

backend/app/scheduler/
└── hooks.py              # 运行完成后的 hook (通知、清理)
```

## 详细设计

### 1. Batch Model

```python
# models/batch.py
class BatchStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"       # 至少一个在运行
    COMPLETED = "completed"   # 全部完成
    PARTIAL = "partial"       # 部分成功部分失败
    FAILED = "failed"         # 全部失败
    CANCELLED = "cancelled"

class Batch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "batches"

    batch_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default=BatchStatus.PENDING.value)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    completed_runs: Mapped[int] = mapped_column(Integer, default=0)
    failed_runs: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)

class BatchRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "batch_runs"

    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id", ondelete="CASCADE"), index=True)
```

### 2. NotificationConfig Model

```python
# models/notification.py
class NotificationChannel(str, Enum):
    WEBHOOK = "webhook"

class NotificationTrigger(str, Enum):
    ON_COMPLETE = "on_complete"
    ON_FAILURE = "on_failure"
    ON_BATCH_COMPLETE = "on_batch_complete"

class NotificationConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "notification_configs"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # {"url": "https://...", "headers": {...}}
    enabled: Mapped[bool] = mapped_column(default=True)
```

### 3. BatchService

```python
# services/batch_service.py
class BatchService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._run_service = RunService(session)

    async def create_batch(
        self,
        *,
        project_id: str,
        runs: list[dict],       # 每项等同 RunCreate payload
        description: str | None = None,
        priority: str = "normal",
    ) -> dict:
        """批量创建运行."""
        batch = Batch(
            batch_id=f"batch_{secrets.token_hex(3)}",
            project_id=project_id,
            total_runs=len(runs),
            description=description,
        )
        self._session.add(batch)
        await self._session.flush()

        results = []
        for run_spec in runs:
            try:
                run = await self._run_service.create_run(
                    project_id=project_id,
                    **run_spec,
                )
                batch_run = BatchRun(batch_id=batch.id, run_id=run.run_id)
                self._session.add(batch_run)
                results.append({"run_id": run.run_id, "status": "queued"})
            except Exception as exc:
                results.append({"run_id": None, "status": "failed", "error": str(exc)})
                batch.failed_runs += 1

        batch.status = BatchStatus.RUNNING.value
        await self._session.commit()

        return {
            "batch_id": batch.batch_id,
            "total": len(runs),
            "queued": sum(1 for r in results if r["status"] == "queued"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
            "runs": results,
        }

    async def get_batch(self, batch_id: str) -> dict | None:
        """获取批次状态汇总."""
        # Query batch + associated runs
        # Return aggregated status

    async def cancel_batch(self, batch_id: str) -> dict:
        """取消批次中所有 QUEUED/RUNNING 的运行."""

    async def update_batch_status(self, batch_id: str):
        """根据关联运行状态更新批次状态."""
        # All completed → COMPLETED
        # All failed → FAILED
        # Mix → PARTIAL
        # Any running → RUNNING
```

### 4. NotificationService

```python
# services/notification_service.py
import httpx

class NotificationService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def notify(self, project_id: str, trigger: str, payload: dict):
        """发送匹配触发器的所有通知."""
        configs = await self._get_configs(project_id, trigger)
        for config in configs:
            if config.channel == NotificationChannel.WEBHOOK.value:
                await self._send_webhook(config, payload)

    async def _send_webhook(self, config: NotificationConfig, payload: dict):
        """发送 webhook 通知 (HTTP POST)."""
        url = config.config.get("url")
        if not url:
            return
        headers = config.config.get("headers", {})
        headers.setdefault("Content-Type", "application/json")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                logger.info("notification.webhook.sent", url=url, status=resp.status_code)
        except Exception:
            logger.exception("notification.webhook.failed", url=url)

    async def _get_configs(self, project_id: str, trigger: str) -> list[NotificationConfig]:
        stmt = select(NotificationConfig).where(
            NotificationConfig.project_id == project_id,
            NotificationConfig.trigger == trigger,
            NotificationConfig.enabled == True,
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # CRUD for notification configs
    async def create_config(self, project_id: str, channel: str, trigger: str, config: dict) -> NotificationConfig:
        ...
    async def list_configs(self, project_id: str) -> list[NotificationConfig]:
        ...
    async def delete_config(self, config_id: str):
        ...
```

### 5. 运行完成 Hook

```python
# scheduler/hooks.py

class RunCompletionHooks:
    """运行完成后触发的 hook."""

    def __init__(self, notification_service, batch_service, cleaner):
        self._notifications = notification_service
        self._batch = batch_service
        self._cleaner = cleaner

    async def on_run_completed(self, run, status: str):
        """运行完成后的 hook chain."""
        project_id = str(run.project_id)

        # 1. 通知
        trigger = "on_complete" if status == "completed" else "on_failure"
        await self._notifications.notify(project_id, trigger, {
            "run_id": run.run_id,
            "status": status,
            "workflow": run.workflow_id,
            "duration_seconds": run.duration_seconds,
            "error": run.error_message,
        })

        # 2. 更新批次状态
        batch = await self._batch.find_batch_for_run(run.run_id)
        if batch:
            await self._batch.update_batch_status(batch.batch_id)
            # 检查批次是否全部完成
            updated = await self._batch.get_batch(batch.batch_id)
            if updated and updated["status"] in ("completed", "partial", "failed"):
                await self._notifications.notify(project_id, "on_batch_complete", updated)

        # 3. work-dir 清理 (from plan-06)
        await self._cleaner.cleanup_run(run.run_id, workspace_path, status)
```

## API 新增

```python
# api/v1/batch.py
router = APIRouter(prefix="/runs/batch", tags=["batch"])

@router.post("")
async def create_batch(payload: BatchCreate, ...):
    """批量创建运行."""
    result = await BatchService(db).create_batch(
        project_id=str(payload.project_id),
        runs=[r.model_dump() for r in payload.runs],
        description=payload.description,
    )
    return success_response(result, status_code=202)

@router.get("/{batch_id}")
async def get_batch(batch_id: str, ...):
    """获取批次状态."""

@router.post("/{batch_id}/cancel")
async def cancel_batch(batch_id: str, ...):
    """取消批次."""

# api/v1/notifications.py
router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.post("")
async def create_notification_config(payload: NotificationConfigCreate, ...):
    """创建通知配置."""

@router.get("")
async def list_notification_configs(project_id: str, ...):
    """列出项目的通知配置."""

@router.delete("/{config_id}")
async def delete_notification_config(config_id: str, ...):
    """删除通知配置."""
```

### Schemas

```python
# schemas/batch.py
class BatchRunSpec(BaseModel):
    workflow_id: str
    workspace: str
    params: dict | None = None
    inputs: dict | None = None
    config_overrides: dict | None = None
    retry_policy: RetryPolicyCreate | None = None

class BatchCreate(BaseModel):
    project_id: str
    runs: list[BatchRunSpec]    # 2-500 项
    description: str | None = None
    priority: str = "normal"
```

## DB Migration

```python
def upgrade():
    op.create_table("batches", ...)
    op.create_table("batch_runs", ...)
    op.create_table("notification_configs", ...)
```

## 测试计划

### 新增测试文件

```
backend/tests/test_services/
├── test_batch.py              # 批量服务
└── test_notifications.py      # 通知服务

backend/tests/test_api/
└── test_batch_api.py          # 批量API端点

backend/tests/test_scheduler/
└── test_hooks.py              # 完成 hook
```

### 关键测试用例

1. **BatchService.create_batch**:
   - 5个合法运行 → 5个 queued, batch status=running
   - 3个合法 + 2个非法 → 3 queued + 2 failed

2. **BatchService.cancel_batch**:
   - 5个运行, 2个 queued + 3个 running → 全部 cancelled

3. **BatchService.update_batch_status**:
   - 全部 completed → batch COMPLETED
   - 全部 failed → batch FAILED
   - 混合 → batch PARTIAL

4. **NotificationService.notify**:
   - 有匹配的 webhook config → HTTP POST 发出 (mock httpx)
   - 无匹配 → 不发送
   - webhook 发送失败 → 日志记录，不影响运行

5. **RunCompletionHooks.on_run_completed**:
   - 运行完成 → 通知 + 批次更新 + work-dir 清理 全部调用

6. **API**:
   - POST /runs/batch → 202 + batch_id
   - GET /runs/batch/{id} → 批次状态汇总
   - POST /runs/batch/{id}/cancel → 全部取消

## 验收标准

- [ ] `POST /runs/batch` 可一次投递多个运行
- [ ] 批次状态自动从关联运行聚合
- [ ] Webhook 通知在运行完成/失败时发出
- [ ] 批次完成时触发 on_batch_complete 通知
- [ ] 新代码覆盖率 ≥ 80%

# Phase 6 — Batch Submission + Notifications

**依赖**: Phase 2, 最好在 Phase 3 之后执行
**被依赖**: 无

## 目标

支持一次投递多个分析任务，批次状态聚合，以及运行完成后的 webhook 通知。

**Webhook 是 best-effort**: 尽力发送 + 日志记录，不做持久化重投递。

## 新增文件

```
backend/app/models/
├── batch.py              # Batch + BatchRun models
└── notification.py       # NotificationConfig model

backend/app/services/
├── batch_service.py
└── notification_service.py

backend/app/api/v1/
├── batch.py              # 批量 API
└── notifications.py      # 通知配置 API

backend/app/scheduler/
└── hooks.py              # 扩展: 通知 + 批次状态更新
```

## 核心设计

### Batch Model

```python
class BatchStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"        # 部分成功
    FAILED = "failed"
    CANCELLED = "cancelled"

class Batch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "batches"
    batch_id: Mapped[str]       # "batch_abc123"
    project_id: Mapped[str]     # FK
    status: Mapped[str]
    total_runs: Mapped[int]
    completed_runs: Mapped[int]
    failed_runs: Mapped[int]
    description: Mapped[str | None]

class BatchRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "batch_runs"
    batch_id: Mapped[str]       # FK
    run_id: Mapped[str]         # FK
```

### NotificationConfig Model

```python
class NotificationConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "notification_configs"
    project_id: Mapped[str]     # FK
    channel: Mapped[str]        # "webhook"
    trigger: Mapped[str]        # "on_complete" | "on_failure" | "on_batch_complete"
    config: Mapped[dict]        # {"url": "...", "headers": {...}}
    enabled: Mapped[bool]
```

### BatchService

```python
class BatchService:
    async def create_batch(self, *, project_id, runs: list[dict], description=None, priority="normal") -> dict:
        # 创建 Batch + 逐个创建 Run + 关联 BatchRun
        # 返回 {batch_id, total, queued, failed, runs: [{run_id, status}]}

    async def get_batch(self, batch_id) -> dict | None:
        # 聚合批次状态

    async def cancel_batch(self, batch_id) -> dict:
        # 取消所有 QUEUED/RUNNING 运行

    async def update_batch_status(self, batch_id):
        # 根据关联运行状态更新: all completed → COMPLETED, all failed → FAILED, mix → PARTIAL
```

### NotificationService

```python
class NotificationService:
    async def notify(self, project_id, trigger, payload):
        configs = await self._get_configs(project_id, trigger)
        for config in configs:
            await self._send_webhook(config, payload)

    async def _send_webhook(self, config, payload):
        url = config.config.get("url")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json=payload, headers=config.config.get("headers", {}))
        except Exception:
            logger.exception("notification.webhook.failed", url=url)
            # best-effort: 记录日志，不重试
```

### RunCompletionHooks 扩展

```python
# scheduler/hooks.py (扩展 Phase 3 的 hooks)
class RunCompletionHooks:
    async def on_run_completed(self, run, status):
        # Phase 3: cleanup + audit
        await self._cleaner.cleanup_run(...)
        await self._audit.log(...)
        # Phase 6: notification + batch
        trigger = "on_complete" if status == "completed" else "on_failure"
        await self._notifications.notify(project_id, trigger, {...})
        batch = await self._batch.find_batch_for_run(run.run_id)
        if batch:
            await self._batch.update_batch_status(batch.batch_id)
            updated = await self._batch.get_batch(batch.batch_id)
            if updated["status"] in ("completed", "partial", "failed"):
                await self._notifications.notify(project_id, "on_batch_complete", updated)
```

## API

```python
# api/v1/batch.py
POST /runs/batch              # 批量创建 → 202
GET  /runs/batch/{batch_id}   # 批次状态
POST /runs/batch/{batch_id}/cancel  # 批量取消

# api/v1/notifications.py
POST   /notifications         # 创建通知配置
GET    /notifications?project_id=  # 列出通知配置
DELETE /notifications/{id}    # 删除通知配置
```

### BatchCreate Schema

```python
class BatchRunSpec(BaseModel):
    workflow_id: str
    workspace: str
    params: dict | None = None
    inputs: dict | None = None
    config_overrides: dict | None = None
    retry_policy: RetryPolicyCreate | None = None

class BatchCreate(BaseModel):
    project_id: str
    runs: list[BatchRunSpec]       # 2-500 项
    description: str | None = None
    priority: str = "normal"
```

## DB Migration

```sql
CREATE TABLE batches (...);
CREATE TABLE batch_runs (...);
CREATE TABLE notification_configs (...);
```

## 测试计划

```
backend/tests/test_services/
├── test_batch.py
└── test_notifications.py

backend/tests/test_api/
└── test_batch_api.py

backend/tests/test_scheduler/
└── test_hooks_phase6.py
```

### 关键测试用例

1. **Batch create**: 5 valid runs → 5 queued; 3 valid + 2 invalid → 3 queued + 2 failed
2. **Batch cancel**: all QUEUED/RUNNING → cancelled
3. **Batch status**: all completed → COMPLETED; mix → PARTIAL; all failed → FAILED
4. **Notification**: matching config → webhook POST (mock httpx); failure → logged, no crash
5. **Hooks**: run complete → notification + batch update + cleanup

## 验收标准

- [ ] `POST /runs/batch` 一次投递多个运行
- [ ] 批次状态自动聚合
- [ ] Webhook 在 run complete/fail 时发送
- [ ] 批次完成时触发 on_batch_complete
- [ ] Webhook 失败不影响 run lifecycle
- [ ] 新代码覆盖率 ≥ 80%

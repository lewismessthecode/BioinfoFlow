# Plan 06 — 监控与运维

**依赖**: plan-02 (调度器核心), plan-01 (引擎抽象)
**被依赖**: 无

## 目标

实现运行超时保护、磁盘空间监控、work-dir 自动清理、审计日志。

## 新增文件

```
backend/app/scheduler/
├── timeout.py          # TimeoutWatcher
├── cleanup.py          # WorkDirCleaner
└── (existing)

backend/app/models/
└── audit_log.py        # AuditLog model

backend/app/services/
└── audit_service.py    # AuditService
```

## 详细设计

### 1. TimeoutWatcher

```python
# scheduler/timeout.py

class TimeoutWatcher:
    """监控运行中的任务，超时后自动取消."""

    def __init__(self, scheduler, check_interval: float = 60.0):
        self._scheduler = scheduler
        self._interval = check_interval
        self._task: asyncio.Task | None = None

    async def start(self):
        self._task = asyncio.create_task(self._watch_loop())

    async def stop(self):
        if self._task:
            self._task.cancel()

    async def _watch_loop(self):
        while True:
            await asyncio.sleep(self._interval)
            await self._check_timeouts()

    async def _check_timeouts(self):
        """检查所有 RUNNING 的 run，超时则取消."""
        async with async_session_maker() as session:
            repo = RunRepository(session)
            running_runs = await repo.list_by_status(RunStatus.RUNNING.value)

            for run in running_runs:
                timeout = self._get_timeout(run)
                if not timeout:
                    continue
                elapsed = (datetime.now(UTC) - run.started_at).total_seconds()
                if elapsed > timeout:
                    logger.warning("timeout.exceeded", run_id=run.run_id, elapsed=elapsed, timeout=timeout)
                    await self._scheduler.cancel(run.run_id)
                    run.error_message = f"Run timed out after {int(elapsed)}s (limit: {timeout}s)"
                    await session.commit()
                    await publish_run_status(run, message="Run timed out")

    def _get_timeout(self, run) -> int | None:
        """从 run.config 获取超时秒数, 有默认值."""
        config = run.config if isinstance(run.config, dict) else {}
        explicit = config.get("timeout_seconds")
        if explicit:
            return int(explicit)
        return 86400  # 默认 24 小时
```

### 2. WorkDirCleaner

```python
# scheduler/cleanup.py

@dataclass
class CleanupPolicy:
    keep_on_success: bool = False       # 成功后保留 work-dir?
    keep_on_failure: bool = True        # 失败后保留? (方便调试)
    max_age_days: int = 7               # 超过天数自动删除
    max_total_size_gb: float = 100.0    # work-dir 总大小上限

class WorkDirCleaner:
    """管理 Nextflow/WDL work directory 的清理."""

    def __init__(self, policy: CleanupPolicy | None = None):
        self._policy = policy or CleanupPolicy()
        self._task: asyncio.Task | None = None

    async def start(self, interval_hours: float = 6.0):
        """启动定期清理任务."""
        self._task = asyncio.create_task(self._cleanup_loop(interval_hours))

    async def cleanup_run(self, run_id: str, workspace_path: str, status: str):
        """清理单个运行的 work-dir (运行完成后调用)."""
        if status == "completed" and not self._policy.keep_on_success:
            await self._remove_work_dirs(run_id, workspace_path)
        elif status == "failed" and not self._policy.keep_on_failure:
            await self._remove_work_dirs(run_id, workspace_path)

    async def cleanup_expired(self):
        """清理过期的 work-dir."""
        cutoff = datetime.now(UTC) - timedelta(days=self._policy.max_age_days)
        # Scan Nextflow work dirs
        nf_work = Path(settings.nextflow_work_dir)
        if nf_work.exists():
            for run_dir in nf_work.iterdir():
                if run_dir.is_dir():
                    mtime = datetime.fromtimestamp(run_dir.stat().st_mtime, tz=UTC)
                    if mtime < cutoff:
                        await asyncio.to_thread(shutil.rmtree, run_dir)
                        logger.info("cleanup.expired", path=str(run_dir))

    async def manual_cleanup(self, run_id: str) -> dict:
        """手动清理 (API调用)."""
        # Find and remove work dirs for this run
        removed = []
        nf_path = Path(settings.nextflow_work_dir) / run_id
        if nf_path.exists():
            await asyncio.to_thread(shutil.rmtree, nf_path)
            removed.append(str(nf_path))
        return {"removed": removed, "count": len(removed)}

    async def _remove_work_dirs(self, run_id: str, workspace_path: str):
        """移除指定运行的所有 work directories."""
        # Nextflow work dir
        nf_path = Path(settings.nextflow_work_dir) / run_id
        if nf_path.exists():
            await asyncio.to_thread(shutil.rmtree, nf_path)

        # MiniWDL work dir
        wdl_path = Path(workspace_path) / ".bioinfoflow" / "miniwdl" / run_id
        if wdl_path.exists():
            await asyncio.to_thread(shutil.rmtree, wdl_path)
```

### 3. AuditLog Model

```python
# models/audit_log.py

class AuditAction(str, Enum):
    RUN_CREATED = "run.created"
    RUN_CANCELLED = "run.cancelled"
    RUN_RESUMED = "run.resumed"
    RUN_RETRIED = "run.retried"
    RUN_DELETED = "run.deleted"
    RUN_CLEANED = "run.cleaned"
    WORKFLOW_REGISTERED = "workflow.registered"
    WORKFLOW_DELETED = "workflow.deleted"

class AuditLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)   # "run", "workflow"
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(36))
    actor: Mapped[str] = mapped_column(String(100), default="api")  # "api", "scheduler", "system"
    details: Mapped[dict] = mapped_column(JSON, default=dict)       # 附加信息
    ip_address: Mapped[str | None] = mapped_column(String(45))
```

### 4. AuditService

```python
# services/audit_service.py

class AuditService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def log(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        *,
        project_id: str | None = None,
        actor: str = "api",
        details: dict | None = None,
        ip_address: str | None = None,
    ):
        entry = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            project_id=project_id,
            actor=actor,
            details=details or {},
            ip_address=ip_address,
        )
        self._session.add(entry)
        await self._session.flush()

    async def list_for_resource(self, resource_type: str, resource_id: str, limit: int = 50):
        stmt = select(AuditLog).where(
            AuditLog.resource_type == resource_type,
            AuditLog.resource_id == resource_id,
        ).order_by(AuditLog.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()
```

### 5. RunService 审计集成

在关键操作中添加审计:

```python
# services/run_service.py (扩展)
async def create_run(self, ...):
    # ... existing logic ...
    run = await self.repo.create(...)
    await AuditService(self.session).log(
        action=AuditAction.RUN_CREATED,
        resource_type="run",
        resource_id=run.run_id,
        project_id=str(project_id),
        details={"workflow_id": str(workflow_id), "workspace": workspace},
    )
    return run

async def cancel_run(self, run_id: str):
    # ... existing logic ...
    await AuditService(self.session).log(
        action=AuditAction.RUN_CANCELLED,
        resource_type="run",
        resource_id=run_id,
    )
```

## API 新增

```python
# api/v1/runs.py (扩展)
@router.post("/{run_id}/cleanup")
async def cleanup_run(run_id: str, ...):
    """手动清理运行的 work-dir."""
    result = await cleaner.manual_cleanup(run_id)
    await AuditService(db).log(action="run.cleaned", ...)
    return success_response(result)

@router.get("/{run_id}/audit")
async def get_run_audit(run_id: str, ...):
    """获取运行的审计日志."""
    entries = await AuditService(db).list_for_resource("run", run_id)
    return success_response([...])
```

## DB Migration

```python
def upgrade():
    op.create_table("audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("action", sa.String(50), nullable=False, index=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=False, index=True),
        sa.Column("project_id", sa.String(36)),
        sa.Column("actor", sa.String(100), default="api"),
        sa.Column("details", sa.JSON, default=dict),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
```

## 测试计划

### 新增测试文件

```
backend/tests/test_scheduler/
├── test_timeout.py        # 超时监控
├── test_cleanup.py        # work-dir 清理
└── (existing)

backend/tests/test_services/
└── test_audit.py          # 审计服务
```

### 关键测试用例

1. **TimeoutWatcher**:
   - 运行超过 timeout → 自动 cancel + error_message 包含超时信息
   - 运行未超时 → 不受影响
   - 无 timeout 配置 → 使用默认 24h

2. **WorkDirCleaner.cleanup_run**:
   - 成功 + keep_on_success=False → work-dir 被删除
   - 失败 + keep_on_failure=True → work-dir 保留
   - 路径不存在 → 无操作，不报错

3. **WorkDirCleaner.cleanup_expired**:
   - 8天前的 work-dir → 被删除 (policy: 7天)
   - 3天前的 work-dir → 保留

4. **AuditService.log**:
   - 记录 create → DB 中有记录
   - 记录 cancel → DB 中有记录 + details 正确

5. **AuditService.list_for_resource**:
   - 3 条记录 → 按 created_at DESC 返回

## 验收标准

- [ ] 运行超时后自动取消 + 有明确的超时错误信息
- [ ] Work-dir 按策略自动清理
- [ ] `POST /{run_id}/cleanup` 手动清理可用
- [ ] 审计日志记录所有关键操作
- [ ] `GET /{run_id}/audit` 返回审计历史
- [ ] 新代码覆盖率 ≥ 80%

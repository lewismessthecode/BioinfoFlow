# Phase 3 — Retry / Timeout / Resume / Ops Baseline

**依赖**: Phase 2 (调度器)
**被依赖**: 无

## 目标

交付一组"真正降低风险"的平台能力: 自动重试、运行超时、Nextflow resume 稳定化、WDL best-effort resume、work-dir 清理、审计日志。

## 能力分类

| 能力 | 保证级别 | 说明 |
|------|----------|------|
| 平台级自动重试 (RetryPolicy) | 强保证 | 可配置策略, 调度器执行 |
| 运行超时 | 强保证 | 到期自动 cancel |
| Nextflow native resume | 强保证 | `-resume {session_id}` |
| WDL restart assist | **best-effort** | 复用 work-dir + 已完成 task 记录, 不保证所有场景 |
| Work-dir 清理 | 强保证 | 可配置策略 + 手动 API |
| 审计日志 | 强保证 | 关键操作记录 |

## 新增文件

```
backend/app/scheduler/
├── retry.py            # RetryPolicy + RetryEvaluator
├── timeout.py          # TimeoutWatcher
├── cleanup.py          # WorkDirCleaner
└── hooks.py            # RunCompletionHooks

backend/app/models/
└── audit_log.py        # AuditLog model

backend/app/services/
└── audit_service.py    # AuditService

backend/app/engine/adapters/
└── wdl.py              # 扩展: WDL restart assist 逻辑
```

## 详细设计

### 1. RetryPolicy + RetryEvaluator

```python
# scheduler/retry.py
@dataclass
class RetryPolicy:
    max_retries: int = 0
    delay_seconds: float = 30
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 600
    retry_on: list[str] = field(default_factory=list)  # error patterns

# 预定义
RETRY_DEFAULT_BIO = RetryPolicy(max_retries=2, delay_seconds=60, retry_on=["connection", "oom", "137", "killed"])

class RetryEvaluator:
    def should_retry(self, task: ScheduledTask, error: str) -> bool:
        if task.attempt >= task.max_attempts: return False
        policy = self._parse_policy(task)
        if not policy.retry_on: return True  # 无模式限制 → 所有错误
        return any(p.lower() in error.lower() for p in policy.retry_on)

    def next_delay(self, task: ScheduledTask) -> float:
        policy = self._parse_policy(task)
        delay = policy.delay_seconds * (policy.backoff_multiplier ** (task.attempt - 1))
        return min(delay, policy.max_delay_seconds)

    def is_oom_error(self, error: str) -> bool:
        return any(p in error.lower() for p in ["out of memory", "oom", "137", "killed", "cannot allocate"])
```

### 2. Scheduler 重试集成

`RunScheduler._on_task_failed()`:
```python
async def _on_task_failed(self, task, error):
    evaluator = RetryEvaluator()
    if evaluator.should_retry(task, error):
        delay = evaluator.next_delay(task)
        await self._queue.re_enqueue(task.id, attempt=task.attempt + 1, delay_until=now + delay)
    else:
        await self._queue.mark_failed(task.id, error)
```

### 3. TimeoutWatcher

```python
# scheduler/timeout.py
class TimeoutWatcher:
    def __init__(self, scheduler, check_interval: float = 60.0): ...

    async def start(self): self._task = asyncio.create_task(self._watch_loop())

    async def _check_timeouts(self):
        running_runs = await repo.list_by_status("running")
        for run in running_runs:
            timeout = RunConfigHelper(run.config).timeout_seconds or 86400  # default 24h
            elapsed = (now - run.started_at).total_seconds()
            if elapsed > timeout:
                await self._scheduler.cancel(run.run_id)
                # update error_message, publish status
```

### 4. WDL Best-Effort Restart Assist

**语义边界 (必须文档化):**
- 复用 MiniWDL 的 `--dir` 保留 work directory
- 在 `run.config.runtime` 中记录已完成 task 名称
- 重新提交时传入相同 `--dir`，MiniWDL 可能复用已有文件
- **不保证**: 所有 subworkflow 跳过、所有 call caching 正确、输出完全一致

```python
# engine/adapters/wdl.py (扩展)
class WDLAdapter(EngineAdapter):
    @property
    def supports_native_resume(self) -> bool: return False
    @property
    def supports_best_effort_resume(self) -> bool: return True

    def get_resume_token(self, run_config: dict) -> str | None:
        """WDL resume token = work directory path."""
        h = RunConfigHelper(run_config)
        return h.runtime.get("wdl_work_dir")

    async def build_command(self, config, workspace):
        cmd = [self.bin, "run", config["workflow_path"]]
        resume_dir = config.get("resume_work_dir")
        if resume_dir:
            cmd.extend(["--dir", resume_dir])  # reuse work dir
        else:
            work_dir = ...  # normal path
            cmd.extend(["--dir", str(work_dir)])
        # ... inputs, options ...
        return cmd
```

RunService.resume_run() 扩展:
```python
if adapter.supports_native_resume:
    resume_token = adapter.get_resume_token(original.config)
elif adapter.supports_best_effort_resume:
    resume_token = adapter.get_resume_token(original.config)
    # add warning in response
else:
    raise ValueError("Resume not supported")
```

### 5. Nextflow 引擎级步骤重试注入

```python
# engine/adapters/nextflow.py (扩展 pre_submit)
async def pre_submit(self, config, workspace):
    config = await super().pre_submit(config, workspace)  # Docker
    retry = RunConfigHelper(config).retry_policy
    if retry.get("max_retries", 0) > 0:
        overrides = dict(config.get("request", {}).get("config_overrides", {}))
        overrides.setdefault("process.errorStrategy", "'retry'")
        overrides.setdefault("process.maxRetries", retry["max_retries"])
        # update config overrides
    return config
```

### 6. WorkDirCleaner

```python
# scheduler/cleanup.py
@dataclass
class CleanupPolicy:
    keep_on_success: bool = False
    keep_on_failure: bool = True
    max_age_days: int = 7

class WorkDirCleaner:
    async def cleanup_run(self, run_id, workspace_path, status): ...
    async def cleanup_expired(self): ...
    async def manual_cleanup(self, run_id) -> dict: ...
```

### 7. AuditLog + AuditService

```python
# models/audit_log.py
class AuditLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "audit_logs"
    action: Mapped[str]          # "run.created", "run.cancelled", ...
    resource_type: Mapped[str]   # "run", "workflow"
    resource_id: Mapped[str]
    project_id: Mapped[str | None]
    actor: Mapped[str]           # "api", "scheduler", "system"
    details: Mapped[dict]
```

### 8. RunCompletionHooks

```python
# scheduler/hooks.py
class RunCompletionHooks:
    async def on_run_completed(self, run, status):
        await self._cleaner.cleanup_run(run.run_id, workspace, status)
        await self._audit.log("run.completed" if status == "completed" else "run.failed", ...)
```

## API 变更

### RunCreate 扩展

```python
class RetryPolicyCreate(BaseModel):
    max_retries: int = Field(default=0, ge=0, le=10)
    delay_seconds: float = Field(default=30, ge=0)
    retry_on: list[str] = Field(default_factory=list)

class RunCreate(BaseModel):
    # ... existing ...
    retry_policy: RetryPolicyCreate | None = None
    timeout_seconds: int | None = None
```

### 新增端点

- `POST /runs/{id}/cleanup` — 手动清理 work-dir
- `GET /runs/{id}/audit` — 运行审计日志

### Resume 端点

`POST /runs/{id}/resume` 现在同时支持 Nextflow 和 WDL:
- Nextflow → native resume (不变)
- WDL → best-effort restart assist (response 中标注 `"resume_type": "best_effort"`)

## DB Migration

```sql
CREATE TABLE audit_logs (...);
-- scheduled_tasks 已在 Phase 2 创建, 本阶段增加 delay_until 列
ALTER TABLE scheduled_tasks ADD COLUMN delay_until TIMESTAMP;
```

## 测试计划

```
backend/tests/test_scheduler/
├── test_retry.py          # RetryPolicy + Evaluator
├── test_timeout.py        # TimeoutWatcher
├── test_cleanup.py        # WorkDirCleaner
└── test_hooks.py          # RunCompletionHooks

backend/tests/test_engine/
└── test_wdl_resume.py     # WDL restart assist

backend/tests/test_services/
└── test_audit.py          # AuditService
```

### 关键测试用例

1. **RetryEvaluator**: should_retry true/false, next_delay exponential, is_oom_error patterns
2. **Scheduler retry**: 失败 + policy → re-enqueue; max_attempts → final fail
3. **TimeoutWatcher**: 超时 → cancel; 未超时 → 不影响
4. **WDL resume**: work-dir 复用; response 标注 best_effort
5. **Cleanup**: success + !keep → deleted; failure + keep → preserved; expired → deleted
6. **AuditLog**: create/cancel → 记录; list → 按时间DESC
7. **API**: RunCreate with retry_policy → config 正确存储

## 验收标准

- [ ] RetryPolicy 可通过 API 配置
- [ ] 调度器自动重试失败任务 (符合 policy)
- [ ] 超时运行自动 cancel + 明确错误信息
- [ ] WDL resume API 可用 (response 标注 best_effort)
- [ ] Work-dir cleanup 手动 API 和自动策略可用
- [ ] 审计日志覆盖 create/cancel/resume/retry/delete
- [ ] 新代码覆盖率 ≥ 80%

# Plan 04 — 断点续运 + 平台级自动重试

**依赖**: plan-01 (引擎抽象), plan-02 (调度器)
**被依赖**: 无 (可独立交付)

## 目标

1. WDL 引擎支持断点续运 (应用层 task tracking)
2. 平台级自动重试策略 (RetryPolicy)
3. Nextflow 引擎级步骤重试配置注入
4. OOM 检测 + 自动资源升级

## 架构设计

```
RunService.create_run(retry_policy=...)
  → Scheduler.enqueue(run_id, retry_policy=policy)
    → Worker 执行
      → 成功 → 完成
      → 失败 → RetryEvaluator.should_retry(task, error)
        → Yes → Scheduler.re_enqueue(run_id, attempt+1, delay)
        → No  → 标记最终失败

WDL Resume:
  原始运行 → task_completions 记录 → 失败
  用户 resume → WDLAdapter.build_resume_command(completions) → 跳过已完成task
```

## 新增文件

```
backend/app/scheduler/
├── retry.py            # RetryPolicy + RetryEvaluator
└── (existing files from plan-02)

backend/app/engine/
├── adapters/
│   └── wdl_resume.py   # WDL task tracking + resume 逻辑
└── (existing files from plan-01)
```

## 详细设计

### 1. RetryPolicy

```python
# scheduler/retry.py
@dataclass
class RetryPolicy:
    max_retries: int = 0                # 0 = 不重试
    delay_seconds: float = 30           # 首次重试延迟
    backoff_multiplier: float = 2.0     # 指数退避
    max_delay_seconds: float = 600      # 最大延迟 (10分钟)
    retry_on: list[str] = field(default_factory=list)  # 错误模式匹配

# 预定义策略
RETRY_NETWORK = RetryPolicy(max_retries=3, delay_seconds=30, retry_on=["connection", "timeout", "download"])
RETRY_OOM = RetryPolicy(max_retries=2, delay_seconds=60, retry_on=["out of memory", "oom", "killed", "137"])
RETRY_TRANSIENT = RetryPolicy(max_retries=3, delay_seconds=10, retry_on=["temporary", "transient", "unavailable"])
RETRY_DEFAULT_BIO = RetryPolicy(max_retries=2, delay_seconds=60, retry_on=["connection", "oom", "137", "killed"])
```

### 2. RetryEvaluator

```python
# scheduler/retry.py
class RetryEvaluator:
    def should_retry(self, task: ScheduledTask, error_message: str) -> bool:
        """判断是否应该重试."""
        if task.attempt >= task.max_attempts:
            return False
        policy = self._get_policy(task)
        if not policy.retry_on:
            return True  # 无模式限制 → 所有错误都重试
        return any(pattern.lower() in error_message.lower() for pattern in policy.retry_on)

    def next_delay(self, task: ScheduledTask) -> float:
        """计算下次重试的延迟时间."""
        policy = self._get_policy(task)
        delay = policy.delay_seconds * (policy.backoff_multiplier ** (task.attempt - 1))
        return min(delay, policy.max_delay_seconds)

    def is_oom_error(self, error_message: str) -> bool:
        """检测 OOM 错误."""
        patterns = ["out of memory", "oom", "killed", "exit code 137", "cannot allocate"]
        return any(p in error_message.lower() for p in patterns)
```

### 3. 调度器集成

在 `Scheduler._execute_task()` 的失败处理中:

```python
async def _on_task_failed(self, task: ScheduledTask, error: str):
    evaluator = RetryEvaluator()
    if evaluator.should_retry(task, error):
        delay = evaluator.next_delay(task)
        await self._queue.re_enqueue(
            task_id=task.id,
            attempt=task.attempt + 1,
            delay_until=datetime.now(UTC) + timedelta(seconds=delay),
        )
        logger.info("scheduler.retry", run_id=task.run_id, attempt=task.attempt + 1, delay=delay)
    else:
        await self._queue.mark_failed(task.id, error)
```

### 4. WDL Task Tracking (应用层 Resume)

```python
# engine/adapters/wdl_resume.py

@dataclass
class TaskCompletion:
    task_name: str
    status: str          # "completed" / "failed"
    outputs: dict        # task outputs (for skip logic)
    completed_at: str

class WDLTaskTracker:
    """Track WDL task completions for application-level resume."""

    def record_completion(self, run_config: dict, task_name: str, status: str, outputs: dict) -> dict:
        """Record a task completion in run.config['task_completions']."""
        completions = run_config.get("task_completions", [])
        completions.append({
            "task_name": task_name,
            "status": status,
            "outputs": outputs,
            "completed_at": datetime.now(UTC).isoformat(),
        })
        return {**run_config, "task_completions": completions}

    def get_completed_tasks(self, run_config: dict) -> set[str]:
        """Get set of successfully completed task names."""
        completions = run_config.get("task_completions", [])
        return {c["task_name"] for c in completions if c["status"] == "completed"}

    def build_resume_inputs(self, original_config: dict, completed_tasks: set[str]) -> dict:
        """Build modified inputs that skip completed tasks.

        Strategy: Keep the same inputs, but MiniWDL's --dir flag
        preserves the work directory. Combined with our tracking,
        we can set up the run to reuse cached outputs.
        """
        # Use MiniWDL's --dir to preserve work directory
        # + mark completed tasks in config for the adapter
        return {
            **original_config,
            "resume": True,
            "completed_tasks": list(completed_tasks),
        }
```

### 5. WDLAdapter Resume 支持

扩展 `WDLAdapter`:

```python
# engine/adapters/wdl.py (扩展)
class WDLAdapter(EngineAdapter):
    @property
    def supports_resume(self) -> bool:
        return True  # 现在支持了 (应用层)

    def get_resume_token(self, run_config: dict) -> str | None:
        """For WDL, the resume token is the work directory path."""
        runtime = run_config.get("runtime", {})
        return runtime.get("wdl_work_dir")

    async def build_command(self, config: dict, workspace: str) -> list[str]:
        cmd = [self.bin, "run", config["workflow_path"]]
        if config.get("resume"):
            # Reuse the same work directory to benefit from MiniWDL's file caching
            work_dir = config.get("resume_work_dir")
            if work_dir:
                cmd.extend(["--dir", work_dir])
        else:
            work_dir = ...  # normal path
            cmd.extend(["--dir", str(work_dir)])
        # ... rest of command building
```

### 6. RunService 扩展

```python
# services/run_service.py 修改

async def create_run(self, ..., retry_policy: dict | None = None):
    # ... existing logic ...
    # Store retry_policy in run config
    run_config["retry_policy"] = retry_policy or {}
    # ... enqueue with retry info ...
    await scheduler.enqueue(run.run_id, priority=priority, retry_policy=retry_policy)

async def resume_run(self, run_id: str, ...):
    # 扩展: 支持 WDL resume
    if adapter.supports_resume:
        resume_token = adapter.get_resume_token(original.config)
        # ... build resume config ...
    else:
        raise ValueError(f"Resume not supported for {engine}")
```

### 7. Nextflow 引擎级步骤重试

通过 `config_overrides` 自动注入:

```python
# engine/adapters/nextflow.py (扩展)
class NextflowAdapter(EngineAdapter):
    def inject_retry_config(self, config: dict, retry_policy: RetryPolicy) -> dict:
        """Inject Nextflow process-level retry into config_overrides."""
        if retry_policy.max_retries <= 0:
            return config
        overrides = dict(config.get("config_overrides", {}))
        overrides.setdefault("process.errorStrategy", "'retry'")
        overrides.setdefault("process.maxRetries", retry_policy.max_retries)
        # OOM handling: increase memory on retry
        if any("oom" in p.lower() or "137" in p for p in retry_policy.retry_on):
            overrides.setdefault("process.memory", "{ task.attempt <= 1 ? '8 GB' : '16 GB' }")
        return {**config, "config_overrides": overrides}
```

## API 变更

### RunCreate Schema 扩展

```python
# schemas/run.py
class RetryPolicyCreate(BaseModel):
    max_retries: int = Field(default=0, ge=0, le=10)
    delay_seconds: float = Field(default=30, ge=0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    retry_on: list[str] = Field(default_factory=list)

class RunCreate(BaseModel):
    # ... existing fields ...
    retry_policy: RetryPolicyCreate | None = None
    timeout_seconds: int | None = None  # 预留给 plan-06
```

### Resume 端点扩展

`POST /{run_id}/resume` 现在同时支持 Nextflow 和 WDL:
- Nextflow: 使用 `-resume {session_id}` (不变)
- WDL: 使用 `--dir {work_dir}` + task_completions

## 测试计划

### 新增测试文件

```
backend/tests/test_scheduler/
├── test_retry.py              # RetryPolicy + RetryEvaluator
└── (existing from plan-02)

backend/tests/test_engine/
├── test_wdl_resume.py         # WDL task tracking + resume
└── (existing from plan-01)
```

### 关键测试用例

1. **RetryEvaluator.should_retry**:
   - attempt < max_attempts + error matches → True
   - attempt >= max_attempts → False
   - error doesn't match retry_on patterns → False
   - empty retry_on → always True (within attempt limit)

2. **RetryEvaluator.next_delay**:
   - attempt 1: 30s
   - attempt 2: 60s (30 * 2^1)
   - attempt 3: 120s (capped at max_delay)

3. **RetryEvaluator.is_oom_error**:
   - "Process killed (exit code 137)" → True
   - "Out of memory" → True
   - "File not found" → False

4. **WDLTaskTracker.record_completion**:
   - 记录完成 → config 中有 task_completions

5. **WDLTaskTracker.build_resume_inputs**:
   - 3/5 task completed → resume config 包含 completed_tasks 列表

6. **Scheduler retry 集成**:
   - 任务失败 + 有 retry_policy → 自动重新入队
   - 达到 max_retries → 标记最终失败
   - 延迟重试 → delay_until 正确计算

7. **Nextflow retry injection**:
   - retry_policy 有值 → config_overrides 包含 errorStrategy
   - OOM retry → 内存递增配置

8. **API**: POST /runs with retry_policy → 运行 config 中包含 retry_policy

## 验收标准

- [ ] WDL 引擎支持 resume (通过 task tracking)
- [ ] RetryPolicy 在 RunCreate API 中可配置
- [ ] 调度器在任务失败时自动评估重试策略
- [ ] Nextflow 引擎级重试配置可注入
- [ ] OOM 错误可检测
- [ ] 现有 resume/retry API 测试通过
- [ ] 新代码覆盖率 ≥ 80%

# Phase 0 — Baseline and Seams

**依赖**: 无
**被依赖**: Phase 1, 2, 3, 4, 5, 6 (所有后续)

## 目标

在不改变外部行为的前提下，补齐后续重构需要的**接口缝**、**回归保护**和**数据契约**。

## 原则

**只重组，不重写。** 本阶段不应改变任何 API 行为或前端可观测的行为。

## 工作清单

### 1. Characterization Tests (固化当前行为)

在 `backend/tests/test_api/` 下新增 `test_run_lifecycle.py`:

```python
# tests/test_api/test_run_lifecycle.py
# 固化当前端到端行为，重构时任何回归都会被发现

class TestRunLifecycle:
    async def test_create_run_returns_202_with_queued_status(self, ...):
        """POST /runs → 202, status=queued."""

    async def test_create_run_requires_enabled_workflow(self, ...):
        """POST /runs with unbound workflow → 403."""

    async def test_cancel_queued_run(self, ...):
        """POST /runs/{id}/cancel on queued → 200, status=cancelled."""

    async def test_cancel_completed_run_is_conflict(self, ...):
        """POST /runs/{id}/cancel on completed → 409."""

    async def test_resume_requires_failed_status(self, ...):
        """POST /runs/{id}/resume on running → 409."""

    async def test_resume_requires_nextflow(self, ...):
        """POST /runs/{id}/resume on WDL → 409."""

    async def test_retry_creates_new_run(self, ...):
        """POST /runs/{id}/retry → 202 with new_run_id."""

    async def test_get_dag_falls_back_to_schema(self, ...):
        """GET /runs/{id}/dag with no config dag → uses workflow schema."""

    async def test_get_logs_respects_tail(self, ...):
        """GET /runs/{id}/logs?tail=5 → at most 5 lines."""
```

目标: **≥ 15 个 characterization tests** 覆盖 run lifecycle 所有端点和关键边界。

### 2. Dispatch Seam (可替换调度接口)

在 `RunService` 中抽出一个可替换的 dispatch 接口:

```python
# services/run_dispatch.py (新建)
from __future__ import annotations
from typing import Protocol

class RunDispatcher(Protocol):
    def dispatch(self, run_id: str, *, priority: str = "normal") -> None:
        """Submit a run for execution."""
        ...

class LegacyDispatcher:
    """Current behavior: submit to in-memory TaskRunner."""
    def dispatch(self, run_id: str, *, priority: str = "normal") -> None:
        from app.runtime.task_runner import task_runner
        from app.runtime.jobs import execute_run
        task_runner.submit(execute_run, run_id)
```

然后在 `RunService` 中:

```python
# services/run_service.py (修改)
class RunService:
    def __init__(self, session: AsyncSession, dispatcher: RunDispatcher | None = None):
        # ... existing ...
        self._dispatcher = dispatcher or LegacyDispatcher()

    async def create_run(self, ...):
        # ... existing logic ...
        run = await self.repo.update(run, status=RunStatus.QUEUED.value)
        await publish_run_status(run, message="Run queued")
        self._dispatcher.dispatch(run.run_id)  # ← 替换 task_runner.submit(execute_run, run.run_id)
        return run
```

同样替换 `resume_run()` 和 `retry_run()` 中的 `task_runner.submit()` 调用。

### 3. BackgroundTaskRunner (非 run 后台任务)

```python
# runtime/background_tasks.py (新建)
from app.runtime.task_runner import TaskRunner

# 给 image pull 等非 run 任务使用的轻量后台执行器
# 内部实现与当前 TaskRunner 相同，只是语义独立
background_tasks = TaskRunner(max_concurrency=2)
```

将 `ImageService` 中的 `task_runner.submit()` 改为 `background_tasks.submit()`。

### 4. Run.config 收口

#### 4a. RunConfigHelper

```python
# models/run_config.py (新建)

class RunConfigHelper:
    """Type-safe accessor for Run.config JSON field."""

    def __init__(self, config: dict | None):
        self._config = config or {}

    @property
    def version(self) -> int:
        return self._config.get("config_schema_version", 0)

    # --- request namespace ---
    @property
    def params(self) -> dict:
        # v1: flat "params" key; v0: also flat
        req = self._config.get("request", {})
        return req.get("params", {}) or self._config.get("params", {})

    @property
    def inputs(self) -> dict:
        req = self._config.get("request", {})
        return req.get("inputs", {}) or self._config.get("inputs", {})

    @property
    def config_overrides(self) -> dict:
        req = self._config.get("request", {})
        return req.get("config_overrides", {}) or self._config.get("config_overrides", {})

    # --- runtime namespace ---
    @property
    def pid(self) -> int | None:
        rt = self._config.get("runtime", {})
        return rt.get("pid")

    @property
    def engine(self) -> str | None:
        rt = self._config.get("runtime", {})
        return rt.get("engine")

    @property
    def resume_token(self) -> str | None:
        rt = self._config.get("runtime", {})
        return rt.get("resume_token") or self._config.get("resume_from")

    # --- policy namespace ---
    @property
    def timeout_seconds(self) -> int | None:
        pol = self._config.get("policy", {})
        return pol.get("timeout_seconds")

    @property
    def retry_policy(self) -> dict:
        pol = self._config.get("policy", {})
        return pol.get("retry", {})

    # --- ui namespace ---
    @property
    def dag(self) -> dict:
        ui = self._config.get("ui", {})
        return ui.get("dag", {}) or self._config.get("dag", {"nodes": [], "edges": []})

    # --- builder ---
    @staticmethod
    def build_v1(*, params, inputs, config_overrides, resolved_runspec=None) -> dict:
        """Create a v1 config dict with proper namespacing."""
        return {
            "config_schema_version": 1,
            "request": {
                "params": params or {},
                "inputs": inputs or {},
                "config_overrides": config_overrides or {},
            },
            "resolved": {
                "runspec": resolved_runspec or {},
            },
            "runtime": {},
            "policy": {},
            "ui": {"dag": {}},
        }
```

#### 4b. 迁移 create_run 使用新格式

`RunService.create_run()` 改为使用 `RunConfigHelper.build_v1()`:

```python
config = RunConfigHelper.build_v1(
    params=resolved_params,
    inputs=inputs or {},
    config_overrides=config_overrides or {},
    resolved_runspec=resolved_runspec,
)
```

#### 4c. 读取兼容

`RunConfigHelper` 的每个 property 都兼容 v0 (旧格式) 和 v1 (新格式)，不需要迁移历史数据。

### 5. 确认 image pull 独立性

搜索代码中所有 `task_runner.submit()` 调用，确认:
- `execute_run` → 走 `RunDispatcher`
- `pull_image` 等 → 走 `background_tasks`

## 涉及文件

| 操作 | 文件 |
|------|------|
| 新建 | `services/run_dispatch.py` |
| 新建 | `runtime/background_tasks.py` |
| 新建 | `models/run_config.py` |
| 新建 | `tests/test_api/test_run_lifecycle.py` |
| 新建 | `tests/test_models/test_run_config.py` |
| 修改 | `services/run_service.py` (注入 dispatcher, 使用 RunConfigHelper) |
| 修改 | `runtime/jobs.py` (读取用 RunConfigHelper) |
| 修改 | `services/image_service.py` (迁移到 background_tasks) |

## 测试计划

### 新增测试

1. **test_run_lifecycle.py**: ≥ 15 个 characterization tests
2. **test_run_config.py**:
   - `build_v1()` 生成正确的 v1 结构
   - v0 格式 (旧数据) 的 property 访问兼容
   - v1 格式的 property 访问正确
   - `dag` 属性兼容旧的 flat `config["dag"]`

### 回归

- 现有 `test_runs.py` 全部通过
- 现有 `test_images.py` 全部通过 (image pull 迁移后)

## 验收标准

- [ ] ≥ 15 个 characterization tests 固化当前行为
- [ ] `RunService` 通过 `RunDispatcher` 接口提交 run (不再直接调用 task_runner)
- [ ] `ImageService` 使用 `background_tasks` (不再使用 run 的 task_runner)
- [ ] 新建 run 使用 `config_schema_version: 1` 格式
- [ ] `RunConfigHelper` 兼容读取 v0 和 v1 格式
- [ ] 所有现有测试通过，零行为变更

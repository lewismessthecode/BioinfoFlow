# Plan 01 — 引擎抽象层

**依赖**: 无 (基础层)
**被依赖**: plan-02, plan-04, plan-05

## 目标

建立 `ExecutionBackend` + `EngineAdapter` 双层抽象，消除 `execute_run()` 中的引擎 if/elif 分支，统一事件模型。

## 架构设计

```
┌──────────────────────────────────────┐
│           Scheduler (plan-02)         │
│  scheduler.submit(run) ──────────┐   │
└──────────────────────────────────┼───┘
                                   ▼
┌──────────────────────────────────────┐
│         ExecutionBackend (接口)       │
│  submit() / cancel() / get_status()  │
│  stream_events() / cleanup()         │
├──────────────────────────────────────┤
│ LocalBackend  │ SSHBackend(未来) │ ...│
└───────┬───────┴──────────────────────┘
        │ 使用
        ▼
┌──────────────────────────────────────┐
│         EngineAdapter (接口)          │
│  build_command() / parse_event()     │
│  get_resume_token() / cancel()       │
├──────────────────────────────────────┤
│ NextflowAdapter   │   WDLAdapter     │
└────────────────────┴─────────────────┘
```

## 新增文件

```
backend/app/engine/
├── __init__.py
├── backend.py          # ExecutionBackend ABC + EngineEvent dataclass
├── local.py            # LocalBackend 实现
├── adapter.py          # EngineAdapter ABC
├── adapters/
│   ├── __init__.py
│   ├── nextflow.py     # NextflowAdapter (从 nextflow_service.py 迁移)
│   └── wdl.py          # WDLAdapter (从 miniwdl_service.py 迁移)
└── registry.py         # engine name → adapter 映射
```

## 详细设计

### 1. EngineEvent (统一事件模型)

```python
# engine/backend.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class EngineEventType(str, Enum):
    STARTED = "started"
    PROCESS_INFO = "process"      # pid, engine name
    TASK_UPDATE = "task"          # task name + status
    LOG = "log"                   # log message
    ERROR = "error"               # error + optional exit_code
    COMPLETED = "completed"       # success flag

@dataclass(frozen=True)
class EngineEvent:
    type: EngineEventType
    data: dict[str, Any] = field(default_factory=dict)
    # Convenience accessors
    @property
    def message(self) -> str | None:
        return self.data.get("message")
    @property
    def task_name(self) -> str | None:
        return self.data.get("name")
    @property
    def task_status(self) -> str | None:
        return self.data.get("status")
    @property
    def pid(self) -> int | None:
        return self.data.get("pid")
```

### 2. EngineAdapter (引擎适配器接口)

```python
# engine/adapter.py
from abc import ABC, abstractmethod
from typing import AsyncIterator

class EngineAdapter(ABC):
    @abstractmethod
    async def build_command(self, config: dict, workspace: str) -> list[str]:
        """Build the CLI command for this engine."""

    @abstractmethod
    def parse_event(self, line: str, stream: str) -> EngineEvent | None:
        """Parse a stdout/stderr line into a typed event."""

    @abstractmethod
    async def cancel(self, *, pid: int | None, **kwargs) -> bool:
        """Cancel a running execution."""

    @abstractmethod
    def get_resume_token(self, run_config: dict) -> str | None:
        """Extract resume token from run config. None if not supported."""

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return engine identifier (e.g., 'nextflow', 'wdl')."""

    @property
    @abstractmethod
    def supports_resume(self) -> bool:
        """Whether this engine supports native resume."""
```

### 3. ExecutionBackend (执行后端接口)

```python
# engine/backend.py
from abc import ABC, abstractmethod
from typing import AsyncIterator

class ExecutionBackend(ABC):
    @abstractmethod
    async def submit(
        self, adapter: EngineAdapter, config: dict, workspace: str
    ) -> AsyncIterator[EngineEvent]:
        """Submit and stream events from an execution."""

    @abstractmethod
    async def cancel(self, adapter: EngineAdapter, *, pid: int | None, **kwargs) -> bool:
        """Cancel a running execution."""

    @abstractmethod
    async def cleanup(self, workspace: str, run_id: str) -> None:
        """Clean up execution artifacts."""
```

### 4. LocalBackend (本地执行)

迁移 `NextflowService.run()` 和 `MiniWDLService.run()` 中通用的子进程管理逻辑:

```python
# engine/local.py
class LocalBackend(ExecutionBackend):
    async def submit(self, adapter, config, workspace):
        cmd = await adapter.build_command(config, workspace)
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=PIPE, stderr=PIPE, cwd=workspace
        )
        yield EngineEvent(EngineEventType.PROCESS_INFO, {"pid": process.pid, "engine": adapter.engine_name})

        # Unified stream drain (reuse pattern from both services)
        async for event in self._drain_streams(process, adapter):
            yield event

        await process.wait()
        if process.returncode != 0 and not self._saw_error:
            yield EngineEvent(EngineEventType.ERROR, {...})
```

### 5. NextflowAdapter

从 `nextflow_service.py` 迁移，保留:
- `_build_command()` → `build_command()` (同逻辑)
- `_parse_output_line()` → `parse_event()` (返回 EngineEvent)
- `cancel()` (pid + run_name)
- `get_resume_token()` (从 config 解析 session_id/run_name)
- GPU pipeline 检测

### 6. WDLAdapter

从 `miniwdl_service.py` 迁移，保留:
- `_build_command()` → `build_command()`
- `_parse_output_line()` → `parse_event()` (返回 EngineEvent)
- `cancel()` (仅 pid)
- output copy 逻辑 (作为 post_run hook)
- `get_resume_token()` → 返回 None (当前不支持native resume)

### 7. EngineRegistry

```python
# engine/registry.py
_ADAPTERS: dict[str, type[EngineAdapter]] = {}

def register_adapter(engine: str, adapter_cls: type[EngineAdapter]):
    _ADAPTERS[engine] = adapter_cls

def get_adapter(engine: str) -> EngineAdapter:
    cls = _ADAPTERS.get(engine)
    if not cls:
        raise ValueError(f"Unknown engine: {engine}")
    return cls()
```

## 重构现有文件

### `runtime/jobs.py`

`execute_run()` 的引擎分支 (jobs.py:193-295) 替换为:

```python
adapter = get_adapter(engine_value)
backend = LocalBackend()
async for event in backend.submit(adapter, run_config, workspace_path):
    await _handle_engine_event(session, run, run_service, event, workspace_path)
```

### `services/run_service.py`

- `cancel_run()` (run_service.py:401-435): 用 `get_adapter(engine).cancel()` 替代 if/elif
- `resume_run()` (run_service.py:437-491): 用 `adapter.get_resume_token()` + `adapter.supports_resume`
- `_require_engine_binary()`: 用 adapter 的属性替代

### 保留但不删除的文件

- `services/nextflow_service.py` → 标记 deprecated, 引用 `engine/adapters/nextflow.py`
- `services/miniwdl_service.py` → 标记 deprecated, 引用 `engine/adapters/wdl.py`

在所有 plan 完成后统一删除旧文件。

## 测试计划

### 新增测试文件

```
backend/tests/test_engine/
├── __init__.py
├── test_engine_event.py       # EngineEvent 序列化/属性访问
├── test_nextflow_adapter.py   # 命令构建 + 事件解析
├── test_wdl_adapter.py        # 命令构建 + 事件解析
├── test_local_backend.py      # LocalBackend 集成测试 (mock subprocess)
└── test_registry.py           # adapter 注册和查找
```

### 关键测试用例

1. **NextflowAdapter.parse_event**:
   - `"process > FASTQC (sample1) [100%]"` → `EngineEvent(TASK_UPDATE, name="FASTQC...", status="completed")`
   - `"Launching \`nf-core/viralrecon\` [happy_euler]"` → `EngineEvent(STARTED, run_name="happy_euler")`
   - `"ERROR ~ ..."` → `EngineEvent(ERROR, message="...")`

2. **WDLAdapter.parse_event**:
   - `"... done ..."` → `EngineEvent(COMPLETED)`
   - `"... error ..."` → `EngineEvent(ERROR)`

3. **NextflowAdapter.build_command**:
   - 基本命令 + params
   - resume 模式 (带 `-resume {token}`)
   - config_overrides 生成临时文件
   - GPU pipeline 自动 profile

4. **LocalBackend.submit**:
   - mock subprocess → 验证事件流顺序 (PROCESS_INFO → TASK_UPDATE... → COMPLETED)
   - stderr 输出 → LOG events
   - 非零 exit code → ERROR event

5. **LocalBackend.cancel**:
   - mock terminate_process_tree → 验证调用

6. **EngineRegistry**:
   - 注册 + 查找
   - 未注册引擎 → ValueError

### 回归测试

- 现有 `test_runs.py` 必须在重构后全部通过 (monkeypatch submit 不变)
- `test_agent_stream.py` 不受影响 (agent 系统独立)

## 验收标准

- [ ] `execute_run()` 中不再有引擎 if/elif 分支
- [ ] NextflowAdapter 和 WDLAdapter 通过所有事件解析测试
- [ ] LocalBackend 通过 mock subprocess 集成测试
- [ ] 现有 API 测试全部通过
- [ ] 新代码覆盖率 ≥ 80%

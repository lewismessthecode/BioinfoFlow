# Phase 1 — Engine Abstraction

**依赖**: Phase 0
**被依赖**: Phase 2, 3, 4, 5, 6

## 目标

建立 `EngineAdapter` + `ExecutionBackend` 双层抽象，消除 `execute_run()` 中的引擎 if/elif 分支，统一事件模型。**将 Nextflow Docker 逻辑一并迁入 adapter。**

## 新增文件

```
backend/app/engine/
├── __init__.py
├── backend.py           # ExecutionBackend ABC + EngineEvent + EngineEventType
├── adapter.py           # EngineAdapter ABC
├── local.py             # LocalBackend (子进程管理)
├── registry.py          # engine name → adapter 映射
└── adapters/
    ├── __init__.py
    ├── nextflow.py      # NextflowAdapter (含 Docker 探测 + profile 注入)
    └── wdl.py           # WDLAdapter (含 output copy)
```

## 核心接口

### EngineEvent (统一事件)

```python
# engine/backend.py
class EngineEventType(str, Enum):
    STARTED = "started"           # 引擎启动, 含 run_name (NF)
    PROCESS_INFO = "process"      # pid + engine name
    TASK_UPDATE = "task"          # task name + status
    LOG = "log"                   # log message + level
    ERROR = "error"               # error + exit_code
    COMPLETED = "completed"       # success flag

@dataclass(frozen=True)
class EngineEvent:
    type: EngineEventType
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def message(self) -> str | None: return self.data.get("message")
    @property
    def task_name(self) -> str | None: return self.data.get("name")
    @property
    def task_status(self) -> str | None: return self.data.get("status")
    @property
    def pid(self) -> int | None: return self.data.get("pid")
    @property
    def exit_code(self) -> int | None: return self.data.get("exit_code")
```

### EngineAdapter (引擎适配器)

```python
# engine/adapter.py
class EngineAdapter(ABC):
    @property
    @abstractmethod
    def engine_name(self) -> str: ...

    @property
    @abstractmethod
    def supports_native_resume(self) -> bool: ...

    @abstractmethod
    async def build_command(self, config: dict, workspace: str) -> list[str]: ...

    @abstractmethod
    def parse_event(self, line: str, stream: str) -> EngineEvent | None: ...

    @abstractmethod
    async def cancel(self, *, pid: int | None, **kwargs) -> bool: ...

    def get_resume_token(self, run_config: dict) -> str | None:
        """默认不支持 resume. 子类覆盖."""
        return None

    async def pre_submit(self, config: dict, workspace: str) -> dict:
        """命令构建前的准备 (如 Docker 探测). 返回更新后的 config."""
        return config

    async def post_complete(self, config: dict, workspace: str, status: str) -> None:
        """执行完成后的清理 (如 WDL output copy)."""
        pass
```

### ExecutionBackend (执行后端)

```python
# engine/backend.py
class ExecutionBackend(ABC):
    @abstractmethod
    async def submit(self, adapter: EngineAdapter, config: dict, workspace: str) -> AsyncIterator[EngineEvent]: ...

    @abstractmethod
    async def cancel(self, adapter: EngineAdapter, *, pid: int | None, **kwargs) -> bool: ...
```

### LocalBackend (本地子进程)

```python
# engine/local.py
class LocalBackend(ExecutionBackend):
    async def submit(self, adapter, config, workspace):
        # 1. pre_submit hook (Docker探测等)
        config = await adapter.pre_submit(config, workspace)
        # 2. build command
        cmd = await adapter.build_command(config, workspace)
        # 3. start subprocess
        process = await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE, cwd=workspace)
        yield EngineEvent(EngineEventType.PROCESS_INFO, {"pid": process.pid, "engine": adapter.engine_name})
        # 4. drain stdout/stderr → EngineEvent
        async for event in self._drain_streams(process, adapter):
            yield event
        # 5. handle exit code
        await process.wait()
        if process.returncode != 0 and not self._had_terminal_event:
            yield EngineEvent(EngineEventType.ERROR, {"message": stderr_tail, "exit_code": process.returncode})
        elif not self._had_terminal_event:
            yield EngineEvent(EngineEventType.COMPLETED, {"success": True})
```

### NextflowAdapter 要点

从 `nextflow_service.py` 迁移，关键变化:

1. `_parse_output_line()` → `parse_event()` (返回 `EngineEvent`)
2. **Docker 逻辑迁入 `pre_submit()`**:
   ```python
   async def pre_submit(self, config, workspace):
       docker_available = await DockerService().is_available()
       overrides = dict(config.get("request", {}).get("config_overrides", {}))
       if docker_available:
           overrides.setdefault("docker.enabled", True)
           overrides.setdefault("docker.pull", True)
       else:
           overrides["docker.enabled"] = False
       # ... update config ...
       return config
   ```
3. GPU pipeline 检测保留在 adapter 中

### WDLAdapter 要点

从 `miniwdl_service.py` 迁移:

1. `_parse_output_line()` → `parse_event()` (返回 `EngineEvent`)
2. `_copy_outputs()` → `post_complete()` hook
3. `supports_native_resume = False`

### EngineRegistry

```python
# engine/registry.py
_ADAPTERS: dict[str, type[EngineAdapter]] = {}

def register_adapter(engine: str, cls: type[EngineAdapter]): _ADAPTERS[engine] = cls
def get_adapter(engine: str) -> EngineAdapter:
    cls = _ADAPTERS.get(engine)
    if not cls: raise ValueError(f"Unknown engine: {engine}")
    return cls()

# 自动注册
register_adapter("nextflow", NextflowAdapter)
register_adapter("wdl", WDLAdapter)
```

## 重构现有文件

### `runtime/jobs.py`

`execute_run()` 中的引擎分支 (jobs.py:193-295) 替换为:

```python
from app.engine.registry import get_adapter
from app.engine.local import LocalBackend

adapter = get_adapter(engine_value)
backend = LocalBackend()
run_config = RunConfigHelper(run.config).to_dict()  # structured config
async for event in backend.submit(adapter, run_config, str(workspace_path)):
    await _handle_engine_event(session, run, run_service, event, str(workspace_path))
```

`_handle_run_event()` 签名改为接收 `EngineEvent`:
```python
async def _handle_engine_event(session, run, run_service, event: EngineEvent, workspace_path):
    if event.type == EngineEventType.STARTED: ...
    elif event.type == EngineEventType.TASK_UPDATE: ...
    # (逻辑与现有相同，只是从 dict 改为 EngineEvent)
```

### `services/run_service.py`

- `cancel_run()`: `get_adapter(engine).cancel(pid=pid, run_name=...)` 替代 if/elif
- `_require_engine_binary()`: adapter 暴露 binary path property
- `resume_run()`: `adapter.supports_native_resume` + `adapter.get_resume_token()`

### 旧文件处理

- `services/nextflow_service.py` — 保留文件，添加 deprecation 注释，内部引用新 adapter
- `services/miniwdl_service.py` — 同上

## 迁移策略

1. 先创建 `engine/` 目录和所有新文件
2. NextflowAdapter/WDLAdapter 初始实现直接从旧 service 拷贝逻辑
3. 在 `jobs.py` 中切换到新接口 (一次 commit)
4. 在 `run_service.py` 中切换 cancel/resume 逻辑
5. 运行所有测试验证无回归

## 测试计划

```
backend/tests/test_engine/
├── __init__.py
├── test_engine_event.py       # EngineEvent 属性访问
├── test_nextflow_adapter.py   # 命令构建 + 事件解析 + Docker pre_submit
├── test_wdl_adapter.py        # 命令构建 + 事件解析 + output copy
├── test_local_backend.py      # mock subprocess 集成
└── test_registry.py           # 注册和查找
```

### 关键测试用例

1. **NextflowAdapter.parse_event**: 6 种输出行 → 正确 EngineEvent 类型
2. **NextflowAdapter.build_command**: resume, overrides, GPU profile 场景
3. **NextflowAdapter.pre_submit**: Docker 可用/不可用 → config 正确注入
4. **WDLAdapter.parse_event**: error/done/log 行 → 正确 EngineEvent
5. **WDLAdapter.post_complete**: output copy 到 outdir
6. **LocalBackend.submit**: mock subprocess → 事件流顺序正确
7. **LocalBackend.submit**: 非零 exit code → ERROR event
8. **EngineRegistry**: 已注册 → 返回实例; 未注册 → ValueError

### 回归

- `test_runs.py` 全部通过
- `test_run_lifecycle.py` (Phase 0) 全部通过

## 验收标准

- [ ] `execute_run()` 中不再有引擎 if/elif 分支
- [ ] `run_service.cancel_run()` 中不再有引擎 if/elif
- [ ] Docker 探测和 profile 注入逻辑在 NextflowAdapter.pre_submit() 中
- [ ] 所有引擎事件统一为 EngineEvent
- [ ] 现有 API 和 SSE 行为不变
- [ ] 新代码覆盖率 ≥ 80%

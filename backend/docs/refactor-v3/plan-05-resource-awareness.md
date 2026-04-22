# Phase 5 — Resource-Aware Scheduling

**依赖**: Phase 2 (调度器)
**被依赖**: 无

## 目标

在 scheduler 稳定后加一层**保守资源检查**，减少资源超卖。

**这是 best-effort 能力**: 目标是"避免明显资源超卖"和"给出运维可见性"，不是"精确预测资源曲线"。

## 新增文件

```
backend/app/scheduler/
├── resources.py        # ResourceRequirements + Estimator + Checker
└── monitor.py          # ResourceMonitor (psutil)
```

## 核心设计

### SystemResources (资源快照)

```python
# scheduler/resources.py
@dataclass(frozen=True)
class SystemResources:
    cpu_count: int
    cpu_available: float        # total - load_avg
    memory_total_gb: float
    memory_available_gb: float
    disk_total_gb: float
    disk_available_gb: float
    gpu_count: int = 0
    gpu_memory_gb: float = 0
```

### ResourceRequirements (任务需求)

```python
@dataclass(frozen=True)
class ResourceRequirements:
    cpu: int = 2
    memory_gb: float = 4.0
    disk_gb: float = 10.0
    gpu: int = 0
    label: str = "default"

RESOURCE_TEMPLATES = {
    "small":  ResourceRequirements(cpu=2, memory_gb=4, disk_gb=10, label="small"),
    "medium": ResourceRequirements(cpu=4, memory_gb=8, disk_gb=50, label="medium"),
    "large":  ResourceRequirements(cpu=8, memory_gb=16, disk_gb=100, label="large"),
    "xlarge": ResourceRequirements(cpu=16, memory_gb=32, disk_gb=200, label="xlarge"),
    "gpu":    ResourceRequirements(cpu=4, memory_gb=16, disk_gb=100, gpu=1, label="gpu"),
}
```

### ResourceEstimator

```python
class ResourceEstimator:
    PIPELINE_TEMPLATES = {
        "viralrecon": "small", "rnaseq": "large", "sarek": "xlarge",
        "fetchngs": "small", "ampliseq": "medium", "taxprofiler": "medium",
    }

    def estimate(self, run_config: dict, workflow_name: str | None = None) -> ResourceRequirements:
        # 1. Explicit resources in config → use them
        # 2. Known pipeline name → template
        # 3. Default → medium
```

### ResourceMonitor (psutil)

```python
# scheduler/monitor.py
class ResourceMonitor:
    def __init__(self, sample_interval=30.0, workspace_path="/"): ...
    async def start(self): ...  # 后台采样
    def current(self) -> SystemResources: ...

    def _sample_sync(self) -> SystemResources:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(self._workspace_path)
        load_avg = psutil.getloadavg()[0]
        gpu_count, gpu_mem = self._detect_gpu()  # nvidia-smi
        return SystemResources(...)
```

### ResourceChecker

```python
@dataclass(frozen=True)
class SafetyMargin:
    cpu: int = 2
    memory_gb: float = 2.0
    disk_gb: float = 10.0

class ResourceChecker:
    def can_schedule(self, available: SystemResources, required: ResourceRequirements) -> bool:
        if required.cpu > available.cpu_available - self._safety.cpu: return False
        if required.memory_gb > available.memory_available_gb - self._safety.memory_gb: return False
        if required.disk_gb > available.disk_available_gb - self._safety.disk_gb: return False
        if required.gpu > available.gpu_count: return False
        return True
```

### Scheduler 集成

```python
# scheduler/scheduler.py _worker() 扩展
if self._monitor:
    requirements = self._estimator.estimate(run_config, workflow_name)
    available = self._monitor.current()
    if not self._checker.can_schedule(available, requirements):
        await self._queue.re_enqueue(task.id, delay_seconds=30)
        continue  # 等待资源释放
```

## Config

```python
scheduler_resource_check_enabled: bool = True
scheduler_resource_sample_interval: float = 30.0
scheduler_safety_cpu: int = 2
scheduler_safety_memory_gb: float = 2.0
scheduler_safety_disk_gb: float = 10.0
```

## API

```python
@router.get("/scheduler/resources")
async def scheduler_resources():
    snapshot = monitor.current()
    return success_response({
        "cpu": {"total": snapshot.cpu_count, "available": snapshot.cpu_available},
        "memory": {"total_gb": snapshot.memory_total_gb, "available_gb": snapshot.memory_available_gb},
        "disk": {"total_gb": snapshot.disk_total_gb, "available_gb": snapshot.disk_available_gb},
        "gpu": {"count": snapshot.gpu_count, "memory_gb": snapshot.gpu_memory_gb},
    })
```

## 测试计划

```
backend/tests/test_scheduler/
├── test_resources.py      # Estimator + Checker
└── test_monitor.py        # Monitor (mock psutil)
```

### 关键测试用例

1. Monitor: mock psutil → 正确 SystemResources
2. Estimator: explicit → 使用; "viralrecon" → small; unknown → medium
3. Checker: 充足 → True; 不足 → False; safety margin 生效
4. Scheduler: 资源不足 → re-enqueue; 充足 → 执行

## 验收标准

- [ ] ResourceMonitor 后台采样
- [ ] 投递前资源检查
- [ ] 资源不足时延迟而非拒绝
- [ ] `/scheduler/resources` API
- [ ] 新代码覆盖率 ≥ 80%

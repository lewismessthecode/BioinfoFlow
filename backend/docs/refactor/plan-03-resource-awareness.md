# Plan 03 — 资源感知调度

**依赖**: plan-02 (调度器核心)
**被依赖**: 无

## 目标

让调度器在投递任务前检查系统可用资源，避免资源超卖导致 OOM 或性能塌方。

## 架构设计

```
ResourceMonitor (后台定时采样)
  → SystemResources snapshot (CPU, Memory, Disk, GPU)

Scheduler._worker():
  task = dequeue()
  requirements = ResourceEstimator.estimate(run_config)
  available = ResourceMonitor.current()
  if ResourceChecker.can_schedule(available, requirements):
      execute(task)
  else:
      re_enqueue(task, delay=30s)  # 等待资源释放
```

## 新增文件

```
backend/app/scheduler/
├── resources.py        # ResourceRequirements + ResourceEstimator + ResourceChecker
├── monitor.py          # ResourceMonitor (psutil-based)
└── (existing files)
```

## 详细设计

### 1. 资源数据模型

```python
# scheduler/resources.py

@dataclass(frozen=True)
class SystemResources:
    """系统资源快照."""
    cpu_count: int              # 总CPU核心数
    cpu_available: float        # 可用CPU (考虑负载)
    memory_total_gb: float      # 总内存 (GB)
    memory_available_gb: float  # 可用内存 (GB)
    disk_total_gb: float        # 磁盘总量 (workspace所在分区)
    disk_available_gb: float    # 磁盘可用
    gpu_count: int = 0          # GPU数量
    gpu_memory_gb: float = 0    # GPU可用显存

@dataclass(frozen=True)
class ResourceRequirements:
    """单个任务的资源需求."""
    cpu: int = 2                # CPU核心数
    memory_gb: float = 4.0      # 内存 (GB)
    disk_gb: float = 10.0       # 估计磁盘使用
    gpu: int = 0                # GPU数量
    label: str = "default"      # 资源模板名称

# 预定义模板 (按生信管线规模)
RESOURCE_TEMPLATES = {
    "small":  ResourceRequirements(cpu=2, memory_gb=4, disk_gb=10, label="small"),
    "medium": ResourceRequirements(cpu=4, memory_gb=8, disk_gb=50, label="medium"),
    "large":  ResourceRequirements(cpu=8, memory_gb=16, disk_gb=100, label="large"),
    "xlarge": ResourceRequirements(cpu=16, memory_gb=32, disk_gb=200, label="xlarge"),
    "gpu":    ResourceRequirements(cpu=4, memory_gb=16, disk_gb=100, gpu=1, label="gpu"),
}
```

### 2. ResourceMonitor

```python
# scheduler/monitor.py
import psutil

class ResourceMonitor:
    """定期采样系统资源. 线程安全."""

    def __init__(self, sample_interval: float = 30.0, workspace_path: str | None = None):
        self._interval = sample_interval
        self._workspace_path = workspace_path or "/"
        self._latest: SystemResources | None = None
        self._task: asyncio.Task | None = None

    async def start(self):
        """开始后台定期采样."""
        self._latest = await self._sample()
        self._task = asyncio.create_task(self._sample_loop())

    async def stop(self):
        if self._task:
            self._task.cancel()

    def current(self) -> SystemResources:
        """返回最新资源快照."""
        if not self._latest:
            raise RuntimeError("Monitor not started")
        return self._latest

    async def _sample(self) -> SystemResources:
        """采样当前系统资源."""
        return await asyncio.to_thread(self._sample_sync)

    def _sample_sync(self) -> SystemResources:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(self._workspace_path)
        cpu_count = psutil.cpu_count(logical=True) or 1
        # cpu_available: 使用 1 分钟负载平均值估算
        load_avg = psutil.getloadavg()[0]  # 1 minute
        cpu_available = max(0, cpu_count - load_avg)

        gpu_count, gpu_mem = self._detect_gpu()

        return SystemResources(
            cpu_count=cpu_count,
            cpu_available=round(cpu_available, 1),
            memory_total_gb=round(mem.total / (1024**3), 1),
            memory_available_gb=round(mem.available / (1024**3), 1),
            disk_total_gb=round(disk.total / (1024**3), 1),
            disk_available_gb=round(disk.free / (1024**3), 1),
            gpu_count=gpu_count,
            gpu_memory_gb=round(gpu_mem, 1),
        )

    def _detect_gpu(self) -> tuple[int, float]:
        """Detect NVIDIA GPUs via nvidia-smi."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
                total_free_mb = sum(float(l) for l in lines)
                return len(lines), total_free_mb / 1024
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return 0, 0.0
```

### 3. ResourceEstimator

```python
# scheduler/resources.py
class ResourceEstimator:
    """从运行配置推断资源需求."""

    # 已知管线 → 资源模板映射
    PIPELINE_TEMPLATES: dict[str, str] = {
        "viralrecon": "small",
        "rnaseq": "large",
        "sarek": "xlarge",
        "fetchngs": "small",
        "ampliseq": "medium",
        "taxprofiler": "medium",
        "mag": "large",
    }

    def estimate(self, run_config: dict, workflow_name: str | None = None) -> ResourceRequirements:
        """Estimate resource requirements for a run.

        Priority:
        1. Explicit resources in run config
        2. Pipeline template (known pipelines)
        3. Default template (medium)
        """
        # 1. Explicit
        explicit = run_config.get("resources")
        if explicit:
            return ResourceRequirements(
                cpu=explicit.get("cpu", 2),
                memory_gb=explicit.get("memory_gb", 4),
                disk_gb=explicit.get("disk_gb", 10),
                gpu=explicit.get("gpu", 0),
                label="explicit",
            )

        # 2. Pipeline template
        if workflow_name:
            name_lower = workflow_name.lower().replace("-", "").replace("_", "")
            for pattern, template_name in self.PIPELINE_TEMPLATES.items():
                if pattern in name_lower:
                    return RESOURCE_TEMPLATES[template_name]

        # 3. Default
        return RESOURCE_TEMPLATES["medium"]
```

### 4. ResourceChecker

```python
# scheduler/resources.py

@dataclass(frozen=True)
class SafetyMargin:
    """系统保留资源 (不分配给任务)."""
    cpu: int = 2              # 保留 2 核给系统
    memory_gb: float = 2.0    # 保留 2GB 给系统
    disk_gb: float = 10.0     # 保留 10GB

class ResourceChecker:
    def __init__(self, safety: SafetyMargin | None = None):
        self._safety = safety or SafetyMargin()

    def can_schedule(self, available: SystemResources, required: ResourceRequirements) -> bool:
        """检查是否有足够资源投递任务."""
        if required.cpu > available.cpu_available - self._safety.cpu:
            return False
        if required.memory_gb > available.memory_available_gb - self._safety.memory_gb:
            return False
        if required.disk_gb > available.disk_available_gb - self._safety.disk_gb:
            return False
        if required.gpu > 0 and required.gpu > available.gpu_count:
            return False
        return True

    def check_disk_space(self, available: SystemResources, min_gb: float = 10.0) -> bool:
        """投递前磁盘空间预检."""
        return available.disk_available_gb >= min_gb + self._safety.disk_gb
```

### 5. 调度器集成

```python
# scheduler/scheduler.py (扩展)
class Scheduler:
    def __init__(self, config, backend, monitor: ResourceMonitor | None = None):
        self._monitor = monitor
        self._checker = ResourceChecker()
        self._estimator = ResourceEstimator()

    async def _worker(self, worker_id: int):
        while self._running:
            task = await self._queue.dequeue()
            if not task:
                await asyncio.sleep(self._config.poll_interval_seconds)
                continue

            # 资源检查
            if self._monitor:
                run_config = await self._get_run_config(task.run_id)
                requirements = self._estimator.estimate(run_config)
                available = self._monitor.current()

                if not self._checker.can_schedule(available, requirements):
                    # 资源不足 → 重新入队，延迟执行
                    await self._queue.re_enqueue(task.id, delay_seconds=30)
                    logger.info("scheduler.resource_wait", run_id=task.run_id, required=requirements)
                    continue

            async with self._semaphore:
                await self._execute_task(task, worker_id)
```

## 配置扩展

```python
# config.py
scheduler_resource_check_enabled: bool = True
scheduler_resource_sample_interval: float = 30.0
scheduler_safety_cpu: int = 2
scheduler_safety_memory_gb: float = 2.0
scheduler_safety_disk_gb: float = 10.0
```

## API 新增

```python
# api/v1/scheduler.py (扩展)
@router.get("/scheduler/resources")
async def scheduler_resources():
    """返回当前系统资源状态."""
    snapshot = monitor.current()
    return success_response({
        "cpu": {"total": snapshot.cpu_count, "available": snapshot.cpu_available},
        "memory": {"total_gb": snapshot.memory_total_gb, "available_gb": snapshot.memory_available_gb},
        "disk": {"total_gb": snapshot.disk_total_gb, "available_gb": snapshot.disk_available_gb},
        "gpu": {"count": snapshot.gpu_count, "memory_gb": snapshot.gpu_memory_gb},
    })
```

## 测试计划

### 新增测试文件

```
backend/tests/test_scheduler/
├── test_resources.py      # ResourceEstimator + ResourceChecker
├── test_monitor.py        # ResourceMonitor (mock psutil)
└── (existing)
```

### 关键测试用例

1. **ResourceMonitor._sample_sync** (mock psutil):
   - 正常采样 → SystemResources 各字段正确
   - GPU不可用 → gpu_count=0

2. **ResourceEstimator.estimate**:
   - 显式 resources → 使用显式值
   - workflow_name="viralrecon" → small 模板
   - workflow_name="sarek" → xlarge 模板
   - 未知管线 → medium 默认模板

3. **ResourceChecker.can_schedule**:
   - available(8CPU, 16GB) + required(4CPU, 8GB) → True
   - available(2CPU, 4GB) + required(4CPU, 8GB) → False
   - available(8CPU, 16GB) + safety(2CPU, 2GB) + required(7CPU, 14GB) → False (safety margin)
   - GPU required but not available → False

4. **ResourceChecker.check_disk_space**:
   - 50GB available, min=10GB, safety=10GB → True
   - 15GB available, min=10GB, safety=10GB → False

5. **调度器资源等待**:
   - 资源不足 → 任务重新入队 (不执行)
   - 资源充足 → 正常执行

## 验收标准

- [ ] ResourceMonitor 后台采样正常工作
- [ ] 投递前进行资源检查
- [ ] 资源不足时任务延迟而非拒绝
- [ ] `/scheduler/resources` API 返回正确数据
- [ ] GPU 检测 (有则检测，无则跳过)
- [ ] 新代码覆盖率 ≥ 80%

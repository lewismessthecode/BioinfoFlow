# Task-Level Scheduling Architecture Design

> Status: **Final**
> Date: 2026-03-31
> Scope: Backend scheduler + engine adapter layer
> Approach: Progressive — lightweight self-built first, Cromwell/K8s extension later
> Contributors: Claude analysis + Codex (HQ/weblog) + Gemini (TES) + company WDL/Cromwell experience

---

## Problem Statement

The `RunScheduler` treats each workflow run as an atomic unit for resource allocation.
An RNA-seq pipeline reserves peak resources (e.g., 32GB for STAR alignment) for its
entire duration, even though most steps (FASTQC, featureCounts) need far less.

**Impact:**
- Low resource utilization (30GB idle during FASTQC)
- Unnecessary queuing (lightweight runs blocked by peak reservations)
- Scaling ceiling (~10 concurrent runs on typical hardware)
- Each Nextflow JVM costs ~500MB-1GB just for DAG orchestration

### Current Data Flow

```
User → enqueue(run) → RunScheduler._worker() → LocalBackend.submit()
                                                   ↓
                                            Engine subprocess (NF/WDL)
                                                   ↓
                                     stdout regex parsing (fragile)
                                                   ↓
                                        _handle_engine_event()
                                         ↓                ↓
                                    DB writes         SSE publish
                                 (run.config blob)     (frontend)
```

### Concurrency Limits

| Concurrent Runs | SQLite | JVM Memory | Verdict |
|-----------------|--------|-----------|---------|
| 10              | OK     | 5-10 GB   | OK |
| 30              | Pressure | 15-30 GB | Risky |
| 50+             | Bottleneck | 25-50 GB | Not viable |

Primary bottlenecks: SQLite single-writer lock, Nextflow JVM memory, worker model
(one worker per run, default `max_concurrency=4`).

---

## Core Architecture Decision

**"自研调度 + 委托执行"** — separate scheduling intelligence from task execution.

This is the same pattern used by the company's production WDL system
(custom Java scheduler + Cromwell execution) and by platforms like Terra and DNAnexus.

**Key insight**: Nextflow and WDL require fundamentally different strategies:
- **Nextflow** is imperative (Groovy DSL, channels, operators) — cannot replace its
  runtime, must work *with* it via executor abstraction
- **WDL** is declarative (static task definitions with explicit I/O) — can fully
  replace the runtime while keeping the parser

```
                        ┌─────────────────────────────┐
                        │      bpiper Scheduler        │
                        │  Run Queue + Run Lifecycle   │
                        └──────┬──────────┬────────────┘
                               │          │
                        NF run │          │ WDL run
                               │          │
                ┌──────────────┘          └──────────────────┐
                ▼                                            ▼
     ┌───────────────────┐              ┌────────────────────────────┐
     │ Nextflow JVM       │              │ bpiper WDL Orchestrator    │
     │ executor = 'hq'    │              │ miniWDL parser → AST       │
     │ weblog → bpiper    │              │ expression evaluation      │
     └──────┬─────────────┘              │ scatter/gather expansion   │
            │                            │ topological scheduling     │
            ▼                            └──────────┬───────────────┘
     ┌──────────────┐                               │
     │ HyperQueue    │                               │
     │ (resource     │                               │
     │  scheduling)  │                               │
     └──────┬───────┘                               │
            │                                        │
            ▼                                        ▼
     ┌──────────────────────────────────────────────────────┐
     │           TaskExecutionBackend (interface)            │
     ├──────────────────────────────────────────────────────┤
     │  LocalDockerBackend (Phase 1)                        │
     │  CromwellBackend    (Phase 3 — enterprise/cluster)   │
     │  KubernetesBackend  (Future — cloud-native)          │
     └──────────────────────────────────────────────────────┘
```

---

## Nextflow Strategy: HyperQueue + nf-weblog

Nextflow's Groovy DSL cannot be "parsed into static tasks" — the DAG is resolved at
runtime through channels and operators. We must let Nextflow manage DAG orchestration
and control execution at the task level via its executor abstraction.

### Why HyperQueue

[HyperQueue](https://github.com/It4innovations/hyperqueue) is a Rust-based task
scheduler with native CPU/memory/GPU resource management. Nextflow has a
[built-in HQ executor](https://www.nextflow.io/docs/latest/executor.html) (not a
third-party plugin).

- Single static binary, 0.1ms per-task overhead
- Works on single machines without Slurm/PBS
- Tasks only start when their requested resources are available
- Zero Java/Groovy code needed on our side

### Why nf-weblog

Replace fragile stdout regex parsing with structured JSON webhooks from the official
[nf-weblog plugin](https://github.com/nextflow-io/nf-weblog) (v1.1.2, 117K+ downloads).

Events include full trace data: `task_id`, `name`, `status`, `cpus`, `memory`,
`peak_rss`, `realtime`, `exit`, `workdir`.

### Implementation Components

**1. HyperQueueService** (`backend/app/services/hyperqueue_service.py` — new)

```python
class HyperQueueService:
    async def is_available(self) -> bool
    async def ensure_running(self) -> HQStatus
    async def get_status(self) -> HQStatus
    async def stop(self) -> None
```

Config: `HQ_ENABLED`, `HQ_BIN`, `HQ_SERVER_DIR`, `HQ_AUTO_START`,
`HQ_WORKER_CPUS`, `HQ_WORKER_MEMORY_GB`.

**2. NextflowAdapter HQ mode** (modify `nextflow.py` `pre_submit()`)

Inject config overrides:
```groovy
process.executor = 'hq'
plugins { id 'nf-weblog@1.1.2' }
weblog { enabled = true; url = 'http://localhost:8000/api/v1/engine-events/nextflow/weblog' }
```

**3. Weblog endpoint** (`backend/app/api/v1/engine_events.py` — new)

`POST /api/v1/engine-events/nextflow/weblog` — receives structured task events,
idempotent upsert into `engine_tasks` table.

**4. Scheduler behavior change**

When HQ enabled: remove `ResourceEstimator` gating for NF runs (HQ handles it).
Keep run admission to control JVM process count.

**5. Graceful fallback**

HQ unavailable → fall back to local executor + run-level scheduling with clear UI
indication.

---

## WDL Strategy: Self-Built Orchestrator

WDL's declarative nature allows us to replace miniWDL's runtime while keeping its
parser. This mirrors the company's production pattern (Java scheduler + Cromwell)
but in Python with a lighter execution backend.

### Architecture

```
WDL file → WDL.load() (miniWDL parser)
  → AST: workflow, tasks, dependencies, scatter, conditionals
  → bpiper WDL Orchestrator:
      1. Resolve input expressions (miniWDL evaluator)
      2. Expand scatter/gather into concrete task instances
      3. Build executable task graph with resource requirements
      4. Topological scheduling loop:
           for each ready task:
             → ResourceLeaseManager.acquire(cpu, memory)
             → TaskExecutionBackend.submit(task_descriptor)
             → wait for completion
             → ResourceLeaseManager.release(lease)
             → pass outputs to downstream tasks
```

### Key Components

**1. WDLOrchestrator** (`backend/app/engine/wdl_orchestrator.py` — new, ~400 lines)

```python
class WDLOrchestrator:
    """Replaces `miniwdl run` CLI. Uses miniWDL parser, bpiper execution."""

    def __init__(self, backend: TaskExecutionBackend, resource_mgr: ResourceLeaseManager):
        self.backend = backend
        self.resource_mgr = resource_mgr

    async def execute(self, wdl_path: str, inputs: dict, workspace: str) -> dict:
        doc = await asyncio.to_thread(WDL.load, wdl_path)
        task_graph = self._build_task_graph(doc.workflow, inputs)

        for batch in self._topological_batches(task_graph):
            results = await asyncio.gather(*[
                self._run_task(task, workspace) for task in batch
            ])
            self._propagate_outputs(batch, results, task_graph)

        return self._collect_final_outputs(task_graph)

    async def _run_task(self, task: TaskDescriptor, workspace: str) -> TaskResult:
        lease = await self.resource_mgr.acquire(cpu=task.cpu, memory_gb=task.memory_gb)
        try:
            handle = await self.backend.submit(task)
            result = await self.backend.wait(handle)
            return result
        finally:
            await self.resource_mgr.release(lease.id)
```

**2. TaskExecutionBackend** interface (`backend/app/engine/execution.py` — new, ~100 lines)

```python
class TaskExecutionBackend(ABC):
    @abstractmethod
    async def submit(self, task: TaskDescriptor) -> TaskHandle: ...

    @abstractmethod
    async def wait(self, handle: TaskHandle) -> TaskResult: ...

    @abstractmethod
    async def cancel(self, handle: TaskHandle) -> bool: ...

    @abstractmethod
    async def status(self, handle: TaskHandle) -> TaskStatus: ...
```

**3. LocalDockerBackend** (Phase 1, `backend/app/engine/backends/local_docker.py` — new, ~250 lines)

```python
class LocalDockerBackend(TaskExecutionBackend):
    """Run tasks as Docker containers on the local machine."""

    async def submit(self, task: TaskDescriptor) -> TaskHandle:
        work_dir = self._prepare_workdir(task)
        self._localize_inputs(task.inputs, work_dir)
        container_id = await self._docker_run(
            image=task.docker,
            command=task.command,
            work_dir=work_dir,
            cpu_limit=task.cpu,
            memory_limit=task.memory,
        )
        return TaskHandle(id=container_id, work_dir=work_dir)

    async def wait(self, handle: TaskHandle) -> TaskResult:
        exit_code = await self._docker_wait(handle.id)
        outputs = self._delocalize_outputs(handle.work_dir, task.output_declarations)
        return TaskResult(exit_code=exit_code, outputs=outputs)
```

**4. FileStager** (`backend/app/engine/file_stager.py` — new, ~200 lines)

Handles input localization (copy/symlink files into task work directory) and output
delocalization (collect results back to run workspace).

**5. ResourceLeaseManager** (shared, `backend/app/scheduler/lease_manager.py` — new, ~300 lines)

```python
class ResourceLeaseManager:
    async def acquire(self, cpu: int, memory_gb: float, ...) -> ResourceLease
    async def release(self, lease_id: str) -> None
    async def query(self) -> LeaseSnapshot
    async def expire_stale(self) -> int  # background sweeper
```

Both NF (via HQ stats) and WDL (via direct leases) coordinate through this manager
for cross-engine resource awareness.

### Complexity: What miniWDL Handles vs What We Build

| Capability | Who handles it | Complexity |
|-----------|---------------|-----------|
| WDL parsing → AST | miniWDL `WDL.load()` | Done (existing) |
| Expression evaluation | miniWDL evaluator | Reuse |
| DAG dependency extraction | Existing `_extract_workflow_dependencies()` | Done |
| Scatter/gather expansion | **New code** (using miniWDL AST) | Medium |
| Conditional execution | **New code** (evaluate WDL conditionals) | Medium |
| Docker container lifecycle | **New** `LocalDockerBackend` | Medium |
| File localization | **New** `FileStager` | Medium |
| Resource scheduling | **New** `ResourceLeaseManager` | Medium |
| Topological scheduling | **New** `WDLOrchestrator` | Low-Medium |

Estimated new code: ~1000-1300 lines of Python, no external dependencies beyond
miniWDL (already a dependency) and Docker (already required).

---

## Shared: engine_tasks Table

Both engines write to a unified task observation table.

```python
class EngineTask(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "engine_tasks"

    run_id: Mapped[str]          # FK to runs
    engine: Mapped[str]          # "nextflow" | "wdl"
    native_task_id: Mapped[str]  # HQ job ID or Docker container ID
    process_name: Mapped[str]    # "FASTQC", "STAR"
    task_name: Mapped[str]       # "FASTQC (sample1)"
    attempt: Mapped[int]
    state: Mapped[str]           # submitted/running/completed/failed
    cpus: Mapped[int | None]
    memory_bytes: Mapped[int | None]
    submitted_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    exit_code: Mapped[int | None]
    workdir: Mapped[str | None]
    peak_rss_bytes: Mapped[int | None]
    realtime_ms: Mapped[int | None]
```

---

## Cross-Engine Resource Coordination

HQ manages NF task resources, WDL orchestrator manages WDL task resources. They share
the same physical machine.

**Phase 1 — Static partitioning:**
```
Machine: 16 CPU, 64 GB
  └─ HQ worker: 12 CPU, 48 GB  (HQ_WORKER_CPUS/MEMORY)
  └─ WDL budget: 4 CPU, 16 GB  (ResourceLeaseManager cap)
  └─ System: safety margin
```

**Future — Dynamic partitioning:**
- No WDL runs active → ResourceLeaseManager releases WDL quota to HQ
- WDL run starts → shrink HQ worker allocation

---

## Fault Scenarios

| Scenario | Impact | Mitigation |
|----------|--------|------------|
| HQ server crashes | NF tasks may fail | NF detects error → run fails → retry policy |
| bpiper restarts | HQ continues independently | Reconnect on startup |
| NF process killed | HQ tasks orphaned | HQ native timeout; bpiper cancel triggers HQ cancel |
| Docker container OOM | WDL task fails | Retry with higher memory (if retry policy allows) |
| nf-weblog POST fails | Task events lost | Stdout parsing as fallback; trace file reconciliation on completion |
| Lease not released | Resources "leaked" | Background sweeper with TTL expiry |

---

## Evolution Roadmap

### Phase 1: Nextflow HQ + nf-weblog + engine_tasks (4-6 weeks)

- `HyperQueueService` — HQ lifecycle management
- `NextflowAdapter` — HQ + weblog config injection
- Weblog webhook endpoint
- `engine_tasks` model + Alembic migration
- Scheduler: skip NF resource gating when HQ enabled
- Frontend: mixed-mode display, HQ status
- Graceful fallback for non-HQ environments

### Phase 2: WDL Self-Built Orchestrator (6-8 weeks)

- `TaskExecutionBackend` interface
- `LocalDockerBackend` — Docker container lifecycle
- `FileStager` — input/output localization
- `ResourceLeaseManager` — acquire/release with TTL
- `WDLOrchestrator` — DAG scheduling with scatter/gather
- Replace `miniwdl run` CLI invocation with in-process orchestration
- Frontend: WDL step-level task panel

### Phase 3: Profile-Guided + Cromwell Extension (8-12 weeks)

- Resource profiles from `engine_tasks` history data
- `ResourceEstimator` evolution: static templates → data-driven
- `CromwellBackend` implementation (optional, for enterprise/cluster)
- TES API layer (optional, for cross-engine standardization)

### Parallel Track: Infrastructure

- DAG write debouncing (batch TASK_UPDATE DB writes)
- SQLite → PostgreSQL migration
- DAG state normalization (JSON blob → relational)

---

## Files to Create/Modify

| File | Action | Phase |
|------|--------|-------|
| `backend/app/services/hyperqueue_service.py` | New | 1 |
| `backend/app/api/v1/engine_events.py` | New | 1 |
| `backend/app/models/engine_task.py` | New | 1 |
| `backend/app/engine/adapters/nextflow.py` | Modify — HQ+weblog injection | 1 |
| `backend/app/scheduler/scheduler.py` | Modify — skip NF resource gating | 1 |
| `backend/app/scheduler/config.py` | Modify — HQ config | 1 |
| `backend/app/config.py` | Modify — HQ env vars | 1 |
| `backend/app/engine/execution.py` | New — TaskExecutionBackend | 2 |
| `backend/app/engine/backends/local_docker.py` | New | 2 |
| `backend/app/engine/file_stager.py` | New | 2 |
| `backend/app/engine/wdl_orchestrator.py` | New | 2 |
| `backend/app/scheduler/lease_manager.py` | New | 2 |
| `backend/app/engine/backends/cromwell.py` | New (optional) | 3 |
| `frontend/app/(app)/scheduler/page.tsx` | Modify — mixed-mode + tasks | 1-2 |

---

## Verification Plan

### Phase 1 Validation
- nf-core rnaseq with FASTQC (2GB) + STAR (32GB): FASTQC runs first, STAR waits
- Two concurrent NF runs: tasks interleave via shared HQ resource pool
- HQ not installed: clean fallback to local executor + clear UI message
- nf-weblog events correctly populate `engine_tasks` and update DAG

### Phase 2 Validation
- Simple WDL workflow (2-3 tasks): correct topological execution
- Scatter workflow: parallel tasks respect resource limits
- Task failure: correct error propagation, retry if configured
- Concurrent NF + WDL: no resource conflicts (static partitioning)

### Phase 3 Validation
- Resource profiles match actual trace data
- CromwellBackend: submit task → poll status → collect outputs (if implemented)

---

## Open Questions

1. **HQ + Docker**: Does Nextflow's HQ executor correctly handle `process.container`
   directives? Requires empirical validation with nf-core pipelines.
2. **miniWDL expression evaluator reuse**: Can we call miniWDL's expression evaluation
   functions without running its full runtime? Need to inspect the Python API.
3. **nf-weblog authentication**: Webhook needs auth to prevent spoofed events.
   Options: shared secret, bearer token, localhost-only.
4. **Scatter complexity**: Nested scatters and scatter-over-scatter patterns need
   careful handling in the WDL orchestrator.
5. **Cross-engine dynamic partitioning**: HQ supports runtime worker updates — verify
   this works reliably for CPU/memory reduction while tasks are running.

---

## References

- [HyperQueue](https://github.com/It4innovations/hyperqueue) — Rust task scheduler
- [HQ Resources](https://it4innovations.github.io/hyperqueue/stable/jobs/resources/) — CPU/mem/GPU
- [Nextflow HQ Executor](https://www.nextflow.io/docs/latest/executor.html) — built-in
- [nf-weblog](https://github.com/nextflow-io/nf-weblog) — structured webhooks (v1.1.2)
- [Cromwell](https://github.com/broadinstitute/cromwell) — WDL execution engine
- [Cromwell Backends](https://cromwell.readthedocs.io/en/stable/backends/Backends/) — pluggable execution
- [GA4GH TES](https://ga4gh.github.io/task-execution-schemas/) — task execution standard
- [miniWDL runner backends](https://miniwdl.readthedocs.io/en/latest/runner_backends.html)

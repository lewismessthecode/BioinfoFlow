# Automatic GPU Discovery and Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make plain `docker compose up -d --build` automatically discover host NVIDIA GPUs, support a UUID-based GPU allowlist, and present Docker, GPU, and scheduler state in one flat bilingual Dashboard surface.

**Architecture:** The backend will probe GPU capability through the Docker daemon by running `nvidia-smi` in a short-lived container created from the already-local backend image. A shared cached GPU inventory and policy service will become the source of truth for health APIs, readiness, scheduler capacity, CLI output, and workflow GPU visibility. The frontend will preserve the existing Geist/Tailwind workbench design while combining Docker, GPU, and scheduler information into one non-nested operations surface.

**Tech Stack:** Python 3.13, FastAPI, Pydantic Settings, Docker SDK for Python, asyncio, pytest, Nextflow, MiniWDL/Docker Swarm, Next.js 16, React 19, TypeScript, Tailwind CSS v4, next-intl, Vitest, Testing Library.

---

## File map

### New backend units

- `backend/app/services/gpu_policy.py`: parse `auto`, `manual`, and `disabled` modes; resolve UUID allowlists against discovered devices; fail closed on invalid selectors.
- `backend/app/services/gpu_probe.py`: native and Docker-backed `nvidia-smi` execution, output parsing, timeout handling, and cleanup.
- `backend/tests/test_services/test_gpu_policy.py`: policy parser and selection tests.
- `backend/tests/test_services/test_gpu_probe.py`: fake-Docker probe lifecycle and parser tests.

### Existing backend units to modify

- `backend/app/config.py`: expose GPU mode, device selectors, probe timeout, and cache duration.
- `backend/app/services/gpu_service.py`: own cached inventory, policy resolution, metrics, stable state codes, and compatibility fields.
- `backend/app/api/v1/system.py`: serialize the new status model and readiness facts.
- `backend/app/scheduler/monitor.py`: consume shared selected GPU inventory instead of launching its own subprocess.
- `backend/app/main.py`: inject the shared GPU service into the resource monitor.
- `backend/app/engine/miniwdl_container_backend.py`: pass the selected UUID set rather than unconditional `all`.
- `backend/app/engine/adapters/nextflow.py`: add selected NVIDIA visibility to GPU profiles.
- `backend/app/cli/commands/system.py`: display mode, state, detected count, selected count, UUID, and selection.
- `backend/app/cli/commands/doctor.py`: translate stable GPU state into actionable diagnostics.
- Existing backend tests under `backend/tests/test_api/`, `backend/tests/test_cli/`, `backend/tests/test_engine/`, `backend/tests/test_scheduler/`, and `backend/tests/test_services/`.

### Frontend units

- Create `frontend/app/(app)/dashboard/components/operations-overview.tsx`: one outer workbench surface composing three flat sections.
- Modify `frontend/app/(app)/dashboard/components/system-status.tsx`: render borderless Docker and GPU sections with stable-state copy.
- Modify `frontend/app/(app)/dashboard/components/scheduler-summary.tsx`: render a borderless scheduler section inside the shared surface.
- Modify `frontend/app/(app)/dashboard/components/dashboard-types.ts`: model GPU policy, state, UUID, counts, and selection.
- Modify `frontend/app/(app)/dashboard/components/dashboard-skeleton.tsx`: match the new single operations surface.
- Modify `frontend/app/(app)/dashboard/page.tsx`: replace the two-card layout with `OperationsOverview`.
- Modify `frontend/app/(app)/dashboard/components/readiness-helpers.ts`: select GPU readiness copy from stable state facts.
- Modify Dashboard component and integration tests.
- Modify `frontend/messages/en.json` and `frontend/messages/zh-CN.json` together.

### Deployment and documentation

- Modify `.env.example`: document default automatic detection and manual UUID selection.
- Modify `docker-compose.yml`, `docker-compose.prod.yml`, and `docker-compose.local.yml` only if new backend environment values need explicit pass-through; no GPU device declaration will be added.
- Modify `scripts/tests/install-test.sh`: assert one image path and default GPU policy preservation.
- Modify `RUNBOOK.md` and `docs/getting-started/docker.md`: make the normal startup path GPU-aware and reframe `docker-compose.gpu.yml` as compatibility troubleshooting.

No production file deletion is planned.

---

### Task 1: Add GPU configuration and fail-closed policy resolution

**Files:**
- Create: `backend/app/services/gpu_policy.py`
- Create: `backend/tests/test_services/test_gpu_policy.py`
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_config_env_loading.py`

- [ ] **Step 1: Write failing settings tests**

Add tests that prove defaults and environment binding:

```python
def test_gpu_settings_default_to_automatic_discovery(tmp_path, monkeypatch):
    root_env = tmp_path / "root.env"
    backend_env = tmp_path / "backend.env"
    root_env.write_text("BIOINFOFLOW_HOME=/tmp/bioinfoflow\n", encoding="utf-8")
    backend_env.write_text("", encoding="utf-8")
    monkeypatch.delenv("BIOINFOFLOW_GPU_MODE", raising=False)
    monkeypatch.delenv("BIOINFOFLOW_GPU_DEVICES", raising=False)

    configured = Settings(_env_file=(root_env, backend_env))

    assert configured.bioinfoflow_gpu_mode == "auto"
    assert configured.bioinfoflow_gpu_devices == "all"


def test_gpu_settings_bind_manual_uuid_selection(tmp_path):
    root_env = tmp_path / "root.env"
    backend_env = tmp_path / "backend.env"
    root_env.write_text(
        "BIOINFOFLOW_HOME=/tmp/bioinfoflow\n"
        "BIOINFOFLOW_GPU_MODE=manual\n"
        "BIOINFOFLOW_GPU_DEVICES=GPU-a,GPU-b\n",
        encoding="utf-8",
    )
    backend_env.write_text("", encoding="utf-8")

    configured = Settings(_env_file=(root_env, backend_env))

    assert configured.bioinfoflow_gpu_mode == "manual"
    assert configured.bioinfoflow_gpu_devices == "GPU-a,GPU-b"
```

- [ ] **Step 2: Run settings tests and verify failure**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_config_env_loading.py -k gpu -q
```

Expected: FAIL because the four GPU settings fields do not exist.

- [ ] **Step 3: Add configuration fields**

Add to `Settings` near Docker configuration:

```python
bioinfoflow_gpu_mode: str = "auto"
bioinfoflow_gpu_devices: str = "all"
gpu_probe_timeout_seconds: float = 10.0
gpu_inventory_cache_seconds: float = 30.0
```

Do not validate the mode at process startup; an invalid value must become the observable `policy_invalid` status instead of crashing the backend.

- [ ] **Step 4: Write failing policy tests**

Create device fixtures and test automatic, manual, disabled, duplicate, unknown UUID, and numeric-index resolution:

```python
DEVICES = (
    GpuDeviceRef(index=0, uuid="GPU-a"),
    GpuDeviceRef(index=1, uuid="GPU-b"),
)


def test_auto_selects_every_discovered_uuid():
    policy = resolve_gpu_policy("auto", "all", DEVICES)
    assert policy.state == "ready"
    assert policy.selected_uuids == ("GPU-a", "GPU-b")


def test_manual_resolves_indices_to_stable_uuids():
    policy = resolve_gpu_policy("manual", "1", DEVICES)
    assert policy.selected_uuids == ("GPU-b",)


@pytest.mark.parametrize("selectors", ["GPU-missing", "GPU-a,GPU-a", "all"])
def test_invalid_manual_policy_fails_closed(selectors):
    policy = resolve_gpu_policy("manual", selectors, DEVICES)
    assert policy.state == "policy_invalid"
    assert policy.selected_uuids == ()


def test_disabled_skips_selection():
    policy = resolve_gpu_policy("disabled", "all", DEVICES)
    assert policy.state == "disabled"
    assert policy.selected_uuids == ()
```

- [ ] **Step 5: Run policy tests and verify failure**

```bash
rtk uv run pytest tests/test_services/test_gpu_policy.py -q
```

Expected: FAIL because `gpu_policy.py` and its types do not exist.

- [ ] **Step 6: Implement the minimal policy module**

Use immutable dataclasses and stable state strings:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class GpuDeviceRef:
    index: int
    uuid: str


@dataclass(frozen=True)
class GpuPolicy:
    mode: str
    state: str
    selected_uuids: tuple[str, ...]
    error: str | None = None


def resolve_gpu_policy(
    mode: str,
    selectors: str,
    devices: tuple[GpuDeviceRef, ...],
) -> GpuPolicy:
    normalized_mode = mode.strip().lower()
    if normalized_mode == "disabled":
        return GpuPolicy("disabled", "disabled", ())
    if normalized_mode == "auto":
        return GpuPolicy("auto", "ready", tuple(device.uuid for device in devices))
    if normalized_mode != "manual":
        return GpuPolicy(normalized_mode, "policy_invalid", (), "Unknown GPU mode")

    tokens = tuple(token.strip() for token in selectors.split(",") if token.strip())
    by_uuid = {device.uuid: device.uuid for device in devices}
    by_index = {str(device.index): device.uuid for device in devices}
    resolved = tuple(by_uuid.get(token) or by_index.get(token) or "" for token in tokens)
    if not tokens or "all" in tokens or "" in resolved or len(set(resolved)) != len(resolved):
        return GpuPolicy("manual", "policy_invalid", (), "Invalid GPU selection")
    return GpuPolicy("manual", "ready", resolved)
```

- [ ] **Step 7: Run focused tests and refactor without changing behavior**

```bash
rtk uv run pytest tests/test_config_env_loading.py -k gpu -q
rtk uv run pytest tests/test_services/test_gpu_policy.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit the policy seam**

```bash
rtk git add backend/app/config.py backend/app/services/gpu_policy.py backend/tests/test_config_env_loading.py backend/tests/test_services/test_gpu_policy.py
rtk git commit -m "feat: add GPU selection policy"
```

---

### Task 2: Probe NVIDIA GPUs through Docker without backend GPU passthrough

**Files:**
- Create: `backend/app/services/gpu_probe.py`
- Create: `backend/tests/test_services/test_gpu_probe.py`
- Modify: `backend/app/services/docker_service.py`
- Modify: `backend/tests/test_services/test_docker_service.py`

- [ ] **Step 1: Write failing CSV parser tests**

```python
def test_parse_inventory_csv_preserves_uuid_and_h20_fields():
    devices = parse_inventory_csv(
        "GPU-123, 0, NVIDIA H20, 97871, 96000, 550.54, 9.0\n"
    )
    assert devices == [
        ProbedGpu(
            uuid="GPU-123",
            index=0,
            name="NVIDIA H20",
            memory_total_mb=97871,
            memory_free_mb=96000,
            driver_version="550.54",
            compute_capability="9.0",
        )
    ]


def test_parse_inventory_csv_skips_blank_rows_and_rejects_malformed_rows():
    with pytest.raises(GpuProbeOutputError, match="expected 7 columns"):
        parse_inventory_csv("GPU-123, 0, NVIDIA H20\n")
```

- [ ] **Step 2: Run parser tests and verify failure**

```bash
rtk uv run pytest tests/test_services/test_gpu_probe.py -k parse -q
```

Expected: FAIL because the parser and dataclass do not exist.

- [ ] **Step 3: Implement inventory and metrics parsing**

Create `ProbedGpu`, `GpuMetric`, `GpuProbeOutputError`, `parse_inventory_csv()`, and `parse_metrics_csv()`. Keep numeric parsing helpers private and treat `[N/A]` as `None` only for optional metric fields.

- [ ] **Step 4: Write failing Docker lifecycle tests**

Use fake image, current-container, and probe-container objects. Assert the device request, entrypoint, timeout, logs, and forced cleanup:

```python
@pytest.mark.asyncio
async def test_docker_probe_runs_same_image_with_all_gpu_device_request():
    client = FakeDockerClient(stdout=H20_CSV, status_code=0)
    probe = DockerGpuProbe(client=client, hostname="backend-container", timeout=3)

    devices = await probe.inventory()

    assert devices[0].name == "NVIDIA H20"
    run_kwargs = client.containers.run_kwargs
    assert run_kwargs["image"] == "sha256:backend-image"
    assert run_kwargs["entrypoint"] == ["nvidia-smi"]
    assert run_kwargs["network_disabled"] is True
    assert run_kwargs["device_requests"][0]["Count"] == -1
    assert run_kwargs["device_requests"][0]["Capabilities"] == [["gpu"]]
    assert client.probe.removed_forcefully is True


@pytest.mark.asyncio
async def test_docker_probe_removes_container_after_timeout():
    client = FakeDockerClient(wait_error=ReadTimeout("probe timed out"))
    probe = DockerGpuProbe(client=client, hostname="backend-container", timeout=1)

    with pytest.raises(GpuProbeTimeout):
        await probe.inventory()

    assert client.probe.removed_forcefully is True
```

- [ ] **Step 5: Run lifecycle tests and verify failure**

```bash
rtk uv run pytest tests/test_services/test_gpu_probe.py -k docker -q
```

Expected: FAIL because `DockerGpuProbe` does not exist.

- [ ] **Step 6: Implement Docker-backed probing**

The synchronous Docker work runs inside `asyncio.to_thread`:

```python
device_request = docker.types.DeviceRequest(
    count=-1,
    capabilities=[["gpu"]],
)
probe_container = client.containers.run(
    image=current_container.image.id,
    command=[
        "--query-gpu=uuid,index,name,memory.total,memory.free,driver_version,compute_cap",
        "--format=csv,noheader,nounits",
    ],
    entrypoint=["nvidia-smi"],
    detach=True,
    network_disabled=True,
    device_requests=[device_request],
    environment={
        "NVIDIA_VISIBLE_DEVICES": "all",
        "NVIDIA_DRIVER_CAPABILITIES": "compute,utility",
    },
    labels={"bioinfoflow.gpu-probe": "true"},
)
try:
    result = probe_container.wait(timeout=timeout_seconds)
    output = probe_container.logs(stdout=True, stderr=False).decode("utf-8", "replace")
    error = probe_container.logs(stdout=False, stderr=True).decode("utf-8", "replace")
finally:
    probe_container.remove(force=True)
```

Map Docker errors into typed exceptions: daemon unavailable, toolkit unavailable/device request rejected, timeout, no devices, and malformed output. Sanitize diagnostic text to one line and cap it at 400 characters.

- [ ] **Step 7: Replace runtime-name probing with observed capability**

Add a focused `DockerService.gpu_probe_client()` or client accessor used by the probe. Keep `check_nvidia_runtime()` only for API compatibility and make its future caller derive capability from the probe result rather than searching for a literal runtime name.

- [ ] **Step 8: Run focused tests**

```bash
rtk uv run pytest tests/test_services/test_gpu_probe.py tests/test_services/test_docker_service.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Docker probing**

```bash
rtk git add backend/app/services/gpu_probe.py backend/app/services/docker_service.py backend/tests/test_services/test_gpu_probe.py backend/tests/test_services/test_docker_service.py
rtk git commit -m "feat: probe GPUs through Docker"
```

---

### Task 3: Make GPU service the cached source of truth

**Files:**
- Modify: `backend/app/services/gpu_service.py`
- Modify: `backend/tests/test_services/test_gpu_service.py`

- [ ] **Step 1: Replace old behavior tests with stable-state tests**

Cover Docker H20 success, auto selection, manual restriction, disabled mode, toolkit error, no devices, invalid policy, native Apple Silicon, metrics, stale cache, and concurrent coalescing:

```python
@pytest.mark.asyncio
async def test_status_reports_two_h20s_with_one_selected_in_manual_mode():
    probe = FakeProbe(devices=[h20("GPU-a", 0), h20("GPU-b", 1)])
    service = GpuService(
        probe=probe,
        mode="manual",
        selectors="GPU-b",
        cache_seconds=30,
    )

    status = await service.get_status()

    assert status.state == "ready"
    assert status.detected_count == 2
    assert status.selected_count == 1
    assert status.selected_gpu_uuids == ("GPU-b",)
    assert [gpu.selected for gpu in status.gpus] == [False, True]
    assert status.usable_for_gpu_workflows is True


@pytest.mark.asyncio
async def test_concurrent_status_calls_share_one_probe():
    probe = BlockingFakeProbe([h20("GPU-a", 0)])
    service = GpuService(probe=probe, mode="auto", selectors="all")
    first, second = await asyncio.gather(service.get_status(), service.get_status())
    assert first == second
    assert probe.inventory_calls == 1
```

- [ ] **Step 2: Run service tests and verify failure**

```bash
rtk uv run pytest tests/test_services/test_gpu_service.py -q
```

Expected: FAIL against the old direct-subprocess model.

- [ ] **Step 3: Implement the new inventory/status model**

Use immutable device/status dataclasses with compatibility properties:

```python
@dataclass(frozen=True)
class GpuInfo:
    uuid: str
    index: int
    name: str
    memory_total_mb: int
    memory_free_mb: int
    driver_version: str
    cuda_version: str | None
    compute_capability: str | None
    gpu_type: str = "NVIDIA"
    selected: bool = False


@dataclass(frozen=True)
class GpuStatus:
    mode: str
    state: str
    detected: bool
    container_toolkit_available: bool
    usable_for_gpu_workflows: bool
    gpus: tuple[GpuInfo, ...]
    selected_gpu_uuids: tuple[str, ...]
    recommendation: str
    error: str | None = None
    stale: bool = False

    @property
    def detected_count(self) -> int:
        return len(self.gpus)

    @property
    def selected_count(self) -> int:
        return len(self.selected_gpu_uuids)
```

Keep `available`, `nvidia_smi_found`, `docker_nvidia_runtime`, `runtime_visible_to_backend`, and `parabricks_compatible` as derived compatibility properties until API consumers migrate.

- [ ] **Step 4: Add bounded caching and metrics reuse**

Guard inventory refresh with `asyncio.Lock`. Preserve a successful cache only within a bounded stale window when refresh fails; label it `stale=True`. Expose `selected_visible_devices()` returning `all`, a comma-separated UUID list, or `None` for disabled/invalid/unavailable policy.

- [ ] **Step 5: Run and refactor service tests**

```bash
rtk uv run pytest tests/test_services/test_gpu_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the shared inventory service**

```bash
rtk git add backend/app/services/gpu_service.py backend/tests/test_services/test_gpu_service.py
rtk git commit -m "refactor: centralize GPU inventory"
```

---

### Task 4: Update system APIs, readiness, and CLI diagnostics

**Files:**
- Modify: `backend/app/api/v1/system.py`
- Modify: `backend/app/cli/commands/system.py`
- Modify: `backend/app/cli/commands/doctor.py`
- Modify: `backend/tests/test_api/test_system_envelope.py`
- Modify: `backend/tests/test_cli/test_cli_system.py`
- Modify: `backend/tests/test_cli/test_cli_doctor.py`

- [ ] **Step 1: Write failing API contract tests**

```python
@pytest.mark.asyncio
async def test_gpu_endpoint_exposes_policy_counts_uuid_and_selection(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.system.get_gpu_service",
        lambda: MockGpuService(manual_h20_status()),
    )
    response = await client.get("/api/v1/system/gpu")
    data = response.json()["data"]
    assert data["mode"] == "manual"
    assert data["state"] == "ready"
    assert data["detected_count"] == 2
    assert data["selected_count"] == 1
    assert data["selected_gpu_uuids"] == ["GPU-b"]
    assert data["gpus"][1]["uuid"] == "GPU-b"
    assert data["gpus"][1]["selected"] is True


@pytest.mark.asyncio
async def test_readiness_reports_toolkit_action_without_compose_override(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.system.get_gpu_service",
        lambda: MockGpuService(toolkit_unavailable_status()),
    )
    response = await client.get("/api/v1/system/readiness")
    gpu = next(item for item in response.json()["data"]["checks"] if item["id"] == "gpu")
    assert gpu["facts"]["state"] == "toolkit_unavailable"
    assert "compose override" not in gpu["facts"]["recommendation"].lower()
```

- [ ] **Step 2: Run API tests and verify failure**

```bash
rtk uv run pytest tests/test_api/test_system_envelope.py -q
```

Expected: FAIL because new fields and state facts are absent.

- [ ] **Step 3: Serialize stable status fields**

Return the new fields from `/system/gpu`, keep old fields, and update `_gpu_readiness_check()` to use `state`, counts, selected UUIDs, and `container_toolkit_available`. GPU remains optional readiness.

- [ ] **Step 4: Write failing CLI output tests**

Assert `bif system gpu` prints mode, detected/selected counts, UUID suffixes, and selection, while `bif doctor` gives state-specific recovery without mentioning the GPU Compose override.

- [ ] **Step 5: Implement CLI formatting and run tests**

```bash
rtk uv run pytest tests/test_cli/test_cli_system.py tests/test_cli/test_cli_doctor.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit API and CLI behavior**

```bash
rtk git add backend/app/api/v1/system.py backend/app/cli/commands/system.py backend/app/cli/commands/doctor.py backend/tests/test_api/test_system_envelope.py backend/tests/test_cli/test_cli_system.py backend/tests/test_cli/test_cli_doctor.py
rtk git commit -m "feat: expose actionable GPU status"
```

---

### Task 5: Feed selected GPU capacity into the scheduler monitor

**Files:**
- Modify: `backend/app/scheduler/monitor.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_scheduler/test_monitor.py`

- [ ] **Step 1: Write a failing async inventory test**

```python
@pytest.mark.asyncio
async def test_resource_monitor_uses_selected_gpu_inventory(monkeypatch):
    gpu_service = FakeGpuService(
        selected=[
            gpu(uuid="GPU-b", free_mb=48 * 1024),
        ]
    )
    monitor = ResourceMonitor(workspace_path="/tmp", gpu_service=gpu_service)

    snapshot = await monitor._sample()

    assert snapshot.gpu_count == 1
    assert snapshot.gpu_memory_gb == 48.0
    assert gpu_service.status_calls == 1
```

Also add a regression test that monkeypatches `subprocess.run` to raise if called.

- [ ] **Step 2: Run monitor tests and verify failure**

```bash
rtk uv run pytest tests/test_scheduler/test_monitor.py -q
```

Expected: FAIL because `ResourceMonitor` has no GPU service dependency.

- [ ] **Step 3: Split system sampling from GPU sampling**

Keep CPU/memory/disk work in a synchronous helper run through `asyncio.to_thread`. Await `gpu_service.get_status()` in `_sample()`, then count only selected devices and sum their free memory. Remove `_detect_gpu()` and the `subprocess` import.

- [ ] **Step 4: Inject the singleton in application startup**

```python
gpu_service = get_gpu_service()
monitor = ResourceMonitor(
    sample_interval=settings.scheduler_resource_sample_interval,
    gpu_service=gpu_service,
)
```

- [ ] **Step 5: Run monitor and scheduler API tests**

```bash
rtk uv run pytest tests/test_scheduler/test_monitor.py tests/test_api/test_scheduler_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit scheduler integration**

```bash
rtk git add backend/app/scheduler/monitor.py backend/app/main.py backend/tests/test_scheduler/test_monitor.py
rtk git commit -m "refactor: share GPU capacity with scheduler"
```

---

### Task 6: Restrict GPU workflow visibility to the selected UUID pool

**Files:**
- Modify: `backend/app/engine/miniwdl_container_backend.py`
- Modify: `backend/app/engine/adapters/nextflow.py`
- Modify: `backend/tests/test_engine/test_miniwdl_container_backend.py`
- Modify: `backend/tests/test_engine/test_nextflow_adapter.py`

- [ ] **Step 1: Write failing MiniWDL selection tests**

```python
def test_misc_config_uses_selected_gpu_uuid_pool(tmp_path, monkeypatch):
    monkeypatch.setattr(
        backend_module,
        "selected_gpu_visible_devices",
        lambda: "GPU-a,GPU-b",
    )
    container = _make_container(tmp_path)
    container.runtime_values = {"gpu": True, "env": {}}

    resources, _user, _groups = container.misc_config(logging.getLogger(__name__))

    assert container.runtime_values["env"]["NVIDIA_VISIBLE_DEVICES"] == "GPU-a,GPU-b"
    assert resources["Reservations"]["GenericResources"] == [
        {"DiscreteResourceSpec": {"Kind": "NVIDIA-GPU", "Value": 1}}
    ]


def test_misc_config_fails_gpu_task_when_policy_has_no_visible_devices(tmp_path, monkeypatch):
    monkeypatch.setattr(backend_module, "selected_gpu_visible_devices", lambda: None)
    container = _make_container(tmp_path)
    container.runtime_values = {"gpu": True, "env": {}}
    with pytest.raises(RuntimeError, match="GPU workflow requested"):
        container.misc_config(logging.getLogger(__name__))
```

- [ ] **Step 2: Run MiniWDL tests and verify failure**

```bash
rtk uv run pytest tests/test_engine/test_miniwdl_container_backend.py -k gpu -q
```

Expected: FAIL because the implementation hardcodes `all`.

- [ ] **Step 3: Implement selected visibility for MiniWDL**

Use a synchronous cached accessor from `gpu_service` because MiniWDL calls `misc_config()` synchronously. Preserve existing user-supplied `NVIDIA_VISIBLE_DEVICES` only when it is a subset of the platform pool; otherwise replace it with the allowed pool.

- [ ] **Step 4: Write failing Nextflow override tests**

```python
@pytest.mark.asyncio
async def test_gpu_profile_adds_selected_nvidia_visibility(monkeypatch):
    monkeypatch.setattr(nextflow_module, "selected_gpu_visible_devices", lambda: "GPU-b")
    monkeypatch.setattr(nextflow_module, "DockerService", AvailableDockerService)
    adapter = NextflowAdapter()

    updated = await adapter.pre_submit(
        _nextflow_config(pipeline="parabricks/main.nf", profile="consumer_gpu"),
        "/tmp/workspace",
    )

    overrides = updated["request"]["config_overrides"]
    assert overrides["env.NVIDIA_VISIBLE_DEVICES"] == "'GPU-b'"
    assert overrides["env.NVIDIA_DRIVER_CAPABILITIES"] == "'compute,utility'"
```

- [ ] **Step 5: Implement Nextflow GPU policy injection**

Only apply NVIDIA overrides when the selected profile or detected pipeline is GPU-aware. Raise a clear pre-submit error if a GPU workflow is requested while policy state exposes no devices. CPU workflows and non-GPU profiles remain byte-for-byte equivalent.

- [ ] **Step 6: Run engine tests**

```bash
rtk uv run pytest tests/test_engine/test_miniwdl_container_backend.py tests/test_engine/test_nextflow_adapter.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit workflow restrictions**

```bash
rtk git add backend/app/engine/miniwdl_container_backend.py backend/app/engine/adapters/nextflow.py backend/tests/test_engine/test_miniwdl_container_backend.py backend/tests/test_engine/test_nextflow_adapter.py
rtk git commit -m "fix: honor selected GPUs in workflow engines"
```

---

### Task 7: Build the flat Dashboard operations surface with frontend TDD

**Files:**
- Create: `frontend/app/(app)/dashboard/components/operations-overview.tsx`
- Modify: `frontend/app/(app)/dashboard/components/system-status.tsx`
- Modify: `frontend/app/(app)/dashboard/components/scheduler-summary.tsx`
- Modify: `frontend/app/(app)/dashboard/components/dashboard-types.ts`
- Modify: `frontend/app/(app)/dashboard/components/dashboard-skeleton.tsx`
- Modify: `frontend/app/(app)/dashboard/page.tsx`
- Modify: `frontend/tests/unit/components/system-status.test.tsx`
- Modify: `frontend/tests/integration/pages/dashboard-page.test.tsx`

- [ ] **Step 1: Extend frontend fixtures and write failing GPU-state tests**

Add the API fields to `GpuInfo` and write unit tests:

```tsx
const manualH20Status: GpuInfo = {
  mode: "manual",
  state: "ready",
  detected: true,
  detected_count: 2,
  selected_count: 1,
  selected_gpu_uuids: ["GPU-b"],
  container_toolkit_available: true,
  usable_for_gpu_workflows: true,
  available: true,
  parabricks_compatible: true,
  recommendation: "",
  error: null,
  gpus: [
    { index: 0, uuid: "GPU-a", name: "NVIDIA H20", selected: false, memory_total_mb: 97871, memory_free_mb: 96000, gpu_type: "NVIDIA" },
    { index: 1, uuid: "GPU-b", name: "NVIDIA H20", selected: true, memory_total_mb: 97871, memory_free_mb: 95000, gpu_type: "NVIDIA" },
  ],
}

it("shows detected hardware separately from the selected GPU pool", () => {
  render(<SystemStatus health={healthy} gpuInfo={manualH20Status} />)
  expect(screen.getByText("2 × NVIDIA H20")).toBeInTheDocument()
  expect(screen.getByText("Manual · using 1 of 2 GPUs")).toBeInTheDocument()
  expect(screen.getByText(/GPU-b/)).toBeInTheDocument()
})
```

Add tests for `disabled`, `toolkit_unavailable`, `policy_invalid`, and `probe_failed` copy.

- [ ] **Step 2: Run component tests and verify failure**

From `frontend/`:

```bash
rtk bun run test tests/unit/components/system-status.test.tsx
```

Expected: FAIL because the types and state rendering do not exist.

- [ ] **Step 3: Update Dashboard types and make SystemStatus borderless**

`SystemStatus` must render semantic `<section>` elements for Docker and GPU, not `CardRoot`. Use existing tokens and icons. GPU rows use hairline dividers, tabular memory, a selected label, and UUID suffix. It must never infer state by matching recommendation strings.

- [ ] **Step 4: Convert SchedulerSummary into an inner section**

Keep the `/scheduler` link and focus ring, but remove its internal `CardRoot`. It should expose `data-dashboard-section="scheduler"` and align its heading and numbers with the Docker/GPU sections.

- [ ] **Step 5: Write a failing integration test for one outer surface**

```tsx
it("renders one flat operations surface without nested workbench cards", async () => {
  mockDashboardApi({ gpu: manualH20Status, scheduler: schedulerStatus })
  renderAppPage(<DashboardPage />)

  const operations = await screen.findByTestId("dashboard-operations-overview")
  expect(operations).toHaveAttribute("data-layout", "flat-sections")
  expect(within(operations).getByTestId("dashboard-docker-section")).toBeInTheDocument()
  expect(within(operations).getByTestId("dashboard-gpu-section")).toBeInTheDocument()
  expect(within(operations).getByTestId("dashboard-scheduler-section")).toBeInTheDocument()
  expect(operations.querySelectorAll("[data-slot='bioflow-card-root']")).toHaveLength(1)
})
```

- [ ] **Step 6: Implement OperationsOverview and responsive layout**

Create one `CardRoot variant="workbench"` containing a header and a grid:

```tsx
<div className="grid md:grid-cols-2 xl:grid-cols-[0.8fr_minmax(0,1.35fr)_0.9fr]">
  <SystemStatus health={health} gpuInfo={gpuInfo} />
  {schedulerStatus ? <SchedulerSummary schedulerStatus={schedulerStatus} /> : null}
</div>
```

Use `border-t` on stacked mobile sections and `xl:border-l xl:border-t-0` between desktop sections. Do not add shadows, gradients, new global tokens, or motion.

- [ ] **Step 7: Update the skeleton and page composition**

Replace the old two-card skeleton and page grid with the single operations surface while leaving readiness, KPI cards, and recent activity unchanged.

- [ ] **Step 8: Run focused frontend tests**

```bash
rtk bun run test tests/unit/components/system-status.test.tsx tests/integration/pages/dashboard-page.test.tsx
```

Expected: PASS.

- [ ] **Step 9: Commit the Dashboard structure**

```bash
rtk git add 'frontend/app/(app)/dashboard' frontend/tests/unit/components/system-status.test.tsx frontend/tests/integration/pages/dashboard-page.test.tsx
rtk git commit -m "refactor: flatten dashboard system status"
```

---

### Task 8: Add precise English and Chinese operator copy

**Files:**
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Modify: `frontend/app/(app)/dashboard/components/readiness-helpers.ts`
- Modify: `frontend/tests/unit/components/readiness-center.test.tsx`
- Modify: `frontend/tests/unit/components/system-status.test.tsx`

- [ ] **Step 1: Write failing readiness-copy tests**

Cover each stable state and assert that old instructions to enable a Compose override disappear:

```tsx
expect(screen.getByText(/Install or configure NVIDIA Container Toolkit/)).toBeInTheDocument()
expect(screen.queryByText(/compose override/i)).not.toBeInTheDocument()
expect(screen.getByText(/BIOINFOFLOW_GPU_MODE=manual/)).toBeInTheDocument()
```

- [ ] **Step 2: Run copy tests and verify failure**

```bash
rtk bun run test tests/unit/components/readiness-center.test.tsx tests/unit/components/system-status.test.tsx
```

Expected: FAIL because stable-state copy keys are absent.

- [ ] **Step 3: Add paired locale keys**

Add sentence-case keys for:

- automatic/all selected
- manual selected count
- discovery disabled
- Docker unavailable
- toolkit unavailable
- no devices
- invalid policy
- probe failed
- stale inventory
- selected/not selected device labels
- recreate backend instruction
- runbook link/action

English copy must say exactly what to set and run. Chinese copy must retain the environment variable and command literals unchanged.

- [ ] **Step 4: Select copy by state code**

Update readiness helpers and Dashboard components to switch on `gpuInfo.state` or readiness `facts.state`. Do not branch on `error` or `recommendation` substrings.

- [ ] **Step 5: Run locale and component verification**

```bash
rtk bun run lint:i18n
rtk bun run test tests/unit/components/readiness-center.test.tsx tests/unit/components/system-status.test.tsx tests/integration/pages/dashboard-page.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit bilingual copy**

```bash
rtk git add frontend/messages/en.json frontend/messages/zh-CN.json 'frontend/app/(app)/dashboard/components/readiness-helpers.ts' frontend/tests/unit/components/readiness-center.test.tsx frontend/tests/unit/components/system-status.test.tsx
rtk git commit -m "docs: explain automatic GPU selection"
```

---

### Task 9: Update environment, installer regression coverage, and operator docs

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Modify: `docker-compose.local.yml`
- Modify: `scripts/install.sh`
- Modify: `scripts/tests/install-test.sh`
- Modify: `RUNBOOK.md`
- Modify: `docs/getting-started/docker.md`

- [ ] **Step 1: Write a failing installer regression assertion**

Extend the shell test to verify the generated `.env` contains automatic defaults and the installer still starts one backend image without a GPU-specific compose file:

```sh
assert_contains "$(cat "$HOME_DIR/.bioinfoflow/install/.env")" "BIOINFOFLOW_GPU_MODE=auto"
assert_contains "$(cat "$HOME_DIR/.bioinfoflow/install/.env")" "BIOINFOFLOW_GPU_DEVICES=all"
if grep -q 'docker-compose.gpu.yml' "$CALLS"; then
  fail "installer should not require a GPU compose override"
fi
```

- [ ] **Step 2: Run installer tests and verify failure**

From repo root:

```bash
rtk sh scripts/tests/install-test.sh
```

Expected: FAIL because the generated environment lacks the GPU defaults.

- [ ] **Step 3: Add environment defaults to every normal deployment path**

Add:

```env
BIOINFOFLOW_GPU_MODE=auto
BIOINFOFLOW_GPU_DEVICES=all
```

to `.env.example` with comments for `manual` and `disabled`. Add the values to the installer-generated `.env`. Compose files may pass them explicitly with `${BIOINFOFLOW_GPU_MODE:-auto}` and `${BIOINFOFLOW_GPU_DEVICES:-all}` but must not declare `gpus: all`.

- [ ] **Step 4: Rewrite GPU operations documentation**

Document:

```bash
nvidia-smi -L
docker run --rm --gpus all ubuntu:24.04 nvidia-smi -L
docker compose up -d --build --force-recreate backend
curl -fsS http://localhost:8000/api/v1/system/gpu
```

Explain automatic mode, manual UUID selection, disabled mode, CPU fallback, and the hardware-versus-workflow distinction. Move `docker-compose.gpu.yml` instructions into a compatibility/troubleshooting note and state that normal startup does not need it.

- [ ] **Step 5: Run documentation and installer checks**

```bash
rtk sh scripts/tests/install-test.sh
rtk git diff --check
rtk rg -n "compose override|docker-compose.gpu.yml" RUNBOOK.md docs/getting-started/docker.md frontend/messages/en.json frontend/messages/zh-CN.json
```

Expected: installer PASS; only compatibility/troubleshooting references remain.

- [ ] **Step 6: Commit operator guidance**

```bash
rtk git add .env.example docker-compose.yml docker-compose.prod.yml docker-compose.local.yml scripts/install.sh scripts/tests/install-test.sh RUNBOOK.md docs/getting-started/docker.md
rtk git commit -m "docs: document automatic GPU discovery"
```

---

### Task 10: Run full verification and local visual inspection

**Files:**
- Modify only files required to fix verification failures.

- [ ] **Step 1: Run backend focused and full checks**

From `backend/`:

```bash
rtk uv run pytest tests/test_services/test_gpu_policy.py tests/test_services/test_gpu_probe.py tests/test_services/test_gpu_service.py tests/test_api/test_system_envelope.py tests/test_scheduler/test_monitor.py tests/test_engine/test_miniwdl_container_backend.py tests/test_engine/test_nextflow_adapter.py tests/test_cli/test_cli_system.py tests/test_cli/test_cli_doctor.py
rtk uv run pytest
rtk uv run ruff check .
rtk uv run ruff format --check .
```

Expected: all PASS.

- [ ] **Step 2: Run frontend focused and full checks**

From `frontend/`:

```bash
rtk bun run test tests/unit/components/system-status.test.tsx tests/unit/components/readiness-center.test.tsx tests/integration/pages/dashboard-page.test.tsx
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
```

Expected: all PASS.

- [ ] **Step 3: Run installer and repository checks**

From repo root:

```bash
rtk sh scripts/tests/install-test.sh
rtk git diff --check
rtk git status --short
```

Expected: installer PASS, no whitespace errors, only intentional changes.

- [ ] **Step 4: Perform browser verification**

Set `AUTH_MODE=dev`, restart services, and inspect `/dashboard` in light and dark mode at 1440, 768, 414, 375, and 320 pixels. Confirm:

- one outer operations surface
- no nested card border
- no horizontal overflow
- section dividers switch orientation correctly
- long H20 names and UUID suffixes truncate without hiding selection state
- focus ring remains visible on the scheduler link
- every failure state has one concise action

- [ ] **Step 5: Record NVIDIA-host commands that could not run locally**

Provide these exact H20 checks in the PR:

```bash
nvidia-smi -L
docker run --rm --gpus all ubuntu:24.04 nvidia-smi -L
docker compose up -d --build --force-recreate backend
curl -fsS http://localhost:8000/api/v1/system/gpu | jq '.data | {mode,state,detected_count,selected_count,gpus}'
```

- [ ] **Step 6: Commit verification-only fixes if needed**

```bash
rtk git status --short
rtk git add -u
rtk git commit -m "fix: resolve GPU discovery verification findings"
```

Skip this commit when verification requires no code changes.

---

### Task 11: Complete code review, Hallmark review, and re-verification

**Files:**
- Review all files changed since `origin/main`.

- [ ] **Step 1: Review backend safety and correctness**

Inspect `rtk git diff origin/main...HEAD` for:

- probe containers always removed, including timeout and Docker errors
- no image pull or network dependency during probing
- no privileged mode, host PID, host network, or unnecessary mounts
- manual selectors fail closed
- UUID selection never broadens to `all`
- CPU workflows remain unaffected
- stale cache has a finite bound and visible label
- API compatibility fields remain coherent
- no event-loop blocking Docker calls

- [ ] **Step 2: Review UI against the requested design constraints**

Score Philosophy, Hierarchy, Execution, Specificity, Restraint, and Variety from 1–5. Revise any axis below 3. Confirm:

- no card inside another card
- no new theme, global token system, gradient, shadow, or decorative motion
- Docker/GPU/scheduler hierarchy is understandable without color
- GPU state and operator action remain readable in both languages
- semantic markup and focus behavior are intact

- [ ] **Step 3: Load and run the Hallmark post-build checks**

Read `hallmark/references/slop-test.md` and `hallmark/references/contract.md` only now. Apply the relevant app/component gates and fix every failure before proceeding.

- [ ] **Step 4: Re-run all checks affected by review fixes**

At minimum:

```bash
rtk uv run pytest
rtk uv run ruff check .
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
rtk sh scripts/tests/install-test.sh
rtk git diff --check
```

Expected: all PASS.

- [ ] **Step 5: Commit review fixes**

```bash
rtk git status --short
rtk git add -u
rtk git commit -m "fix: address GPU discovery review"
```

Skip this commit if review finds nothing actionable.

---

### Task 12: Sync, push, and create the pull request

**Files:**
- No planned source edits; resolve only genuine rebase conflicts.

- [ ] **Step 1: Confirm clean worktree and inspect commits**

```bash
rtk git status --short
rtk git log --oneline origin/main..HEAD
```

Expected: clean status and a sequence of focused Conventional Commits.

- [ ] **Step 2: Sync the latest default branch**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

Expected: successful rebase. If conflicts occur, preserve unrelated upstream changes, resolve only overlapping files, and rerun affected tests.

- [ ] **Step 3: Run the final risk-proportional smoke suite after rebase**

```bash
rtk uv run pytest tests/test_services/test_gpu_policy.py tests/test_services/test_gpu_probe.py tests/test_services/test_gpu_service.py tests/test_api/test_system_envelope.py tests/test_scheduler/test_monitor.py tests/test_engine/test_miniwdl_container_backend.py tests/test_engine/test_nextflow_adapter.py
rtk bun run test tests/unit/components/system-status.test.tsx tests/unit/components/readiness-center.test.tsx tests/integration/pages/dashboard-page.test.tsx
rtk bun run lint:i18n
rtk sh scripts/tests/install-test.sh
rtk git diff --check
```

Expected: all PASS.

- [ ] **Step 4: Push the branch**

```bash
rtk git push -u origin codex/auto-gpu-dashboard-redesign
```

- [ ] **Step 5: Create the PR**

Use the canonical title:

```text
fix: auto-detect host GPUs in Docker deployments
```

The body must include:

- root cause: backend-container visibility and Docker CLI/runtime-name heuristics
- architecture: Docker API probe plus UUID policy
- UI: one flat operations surface, no nested cards
- operator actions for auto/manual/disabled modes
- test commands and results
- commands not runnable without an NVIDIA host
- H20 verification commands
- compatibility note for `docker-compose.gpu.yml`

Create a ready-for-review PR only after all local review findings are resolved.

---

## Plan self-review checklist

- Every design-spec goal maps to a task above.
- Automatic, manual, disabled, CPU-only, Apple Silicon, invalid policy, toolkit missing, probe failure, and stale-cache behavior have explicit tests.
- Backend discovery, scheduler capacity, workflow visibility, API facts, CLI output, frontend copy, installer defaults, and docs all consume the same policy terminology.
- No step requires a second image or mandatory GPU Compose override.
- No production deletion or global design-system rewrite is included.
- TDD order is explicit: failing test, observed failure, minimal implementation, passing test, commit.
- Review and PR creation are required deliverables rather than optional follow-ups.

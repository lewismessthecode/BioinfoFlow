# Automatic GPU Discovery and Dashboard Redesign

**Date:** 2026-07-24  
**Status:** Design approved; implementation pending  
**Scope:** Backend GPU discovery and policy, workflow GPU visibility, Dashboard system-status layout, operator documentation, and tests

## Problem

Bioinfoflow currently conflates four different questions:

1. Does the host contain a GPU?
2. Can Docker assign that GPU to a container?
3. Which GPUs may Bioinfoflow use?
4. Which GPUs are visible to a particular workflow task?

The default `docker compose up -d --build` path does not request GPU devices for
the backend container. The Dashboard therefore reports no GPU on an NVIDIA H20
host unless the operator knows to add `docker-compose.gpu.yml`. The managed
installer has the same conceptual limitation because it launches its generated
Compose file without GPU device requests.

The current detection path also relies on commands inside the backend process:

- `GpuService` searches for `nvidia-smi` inside the backend container.
- Its Docker runtime check searches for a `docker` CLI that the backend image
  does not install.
- `ResourceMonitor` independently runs `nvidia-smi`, creating a second source of
  truth.
- GPU workflow configuration commonly exposes `NVIDIA_VISIBLE_DEVICES=all`, so
  a multi-GPU operator cannot define a stable platform-level allowlist.

The Dashboard compounds the diagnosis problem by separating Docker, NVIDIA
runtime, GPU, and scheduler information into visually uneven card surfaces.
This produces empty space, weak hierarchy, and status labels that do not explain
what the operator should do next.

## Goals

- Make plain `docker compose up -d --build` sufficient for automatic NVIDIA GPU
  discovery on a correctly configured Linux host.
- Keep one backend image and one normal Compose startup path for CPU, NVIDIA,
  and Apple Silicon machines.
- Do not require the backend container itself to receive a GPU device.
- Detect GPU support at the same Docker boundary used to launch workflow
  containers.
- Support automatic, disabled, and explicit multi-GPU allowlist policies.
- Persist GPU identity by NVIDIA UUID rather than mutable device index.
- Feed one shared GPU inventory into the API, readiness checks, scheduler
  resource reporting, and workflow launch configuration.
- Give operators precise English and Chinese guidance for every failure state.
- Redesign the Dashboard status area in place, preserving the existing visual
  system and avoiding nested cards.
- Develop through tests first, perform a focused review, and deliver the change
  through a pull request.

## Non-goals

- No new frontend theme, font, icon library, or animation system.
- No broad Dashboard rewrite or route reorganization.
- No deletion of `docker-compose.gpu.yml` in this change. It remains as a
  compatibility path until a later release can remove it deliberately.
- No multi-node GPU agent or remote cluster inventory protocol.
- No exclusive per-task GPU lease scheduler. This change defines the platform
  GPU pool and passes the allowed devices to GPU workloads; exclusive sharing
  and topology-aware placement can build on the same UUID model later.
- No claim that Apple Silicon can run NVIDIA-only container workflows.

## Design Principles

### Detect capability at the execution boundary

The Docker daemon, not the backend container namespace, determines whether a
workflow container can receive an NVIDIA GPU. GPU discovery must therefore use
the Docker API already mounted into the backend rather than treating direct
backend access to `/dev/nvidia*` as the source of truth.

### Separate inventory from policy

Bioinfoflow should discover every available GPU, then independently decide
which devices are permitted for workflows. Detection never silently hides a
device merely because the operator excluded it from the workflow pool.

### Prefer observed behavior over runtime-name heuristics

Modern NVIDIA Container Toolkit configurations may use runtime or CDI paths
that are not accurately represented by checking whether Docker reports a
runtime literally named `nvidia`. A successful GPU device request and
`nvidia-smi` probe is stronger evidence than daemon metadata alone.

### Fail safely and explain precisely

CPU workflows must remain available when GPU probing fails. Manual allowlists
must fail closed for unknown UUIDs and return a concrete corrective action.

## Backend Architecture

### Shared GPU inventory service

Refactor the current GPU service into the single source of truth used by:

- `/api/v1/system/health`
- `/api/v1/system/gpu`
- `/api/v1/system/gpu/metrics`
- `/api/v1/system/readiness`
- scheduler resource snapshots
- GPU workflow launch configuration
- CLI `bif system gpu` and `bif doctor`

The service owns an asynchronous cache and lock so concurrent Dashboard,
readiness, and scheduler requests do not launch duplicate probes. Static
inventory may be cached for approximately 30 seconds. Metrics may use a shorter
cache while still coalescing simultaneous requests.

### Docker GPU probe

On Linux with Docker available, the service will:

1. Inspect the running backend container through the Docker socket and resolve
   its already-local image ID.
2. Start a short-lived container from that image with an NVIDIA device request,
   utility and compute driver capabilities, no application volumes, and an
   overridden entrypoint that runs `nvidia-smi`.
3. Query UUID, index, name, total and free memory, driver version, compute
   capability, and utilization fields required by the API.
4. Apply a strict timeout, capture stderr and Docker errors, and remove the
   probe container in every completion path.
5. Parse the result into the shared inventory model.

The probe must not pull a new CUDA image. Reusing the running backend image
keeps discovery offline-capable and avoids introducing a second image lifecycle.
The NVIDIA runtime supplies `nvidia-smi` when the utility capability is
available.

Direct native probes remain valid fallbacks:

- Native Linux development may run a local `nvidia-smi` when present.
- Native macOS development may report Apple Silicon hardware through
  `system_profiler`, but must mark NVIDIA container workflow capability false.
- A Linux backend running under Docker Desktop must not claim that Apple Silicon
  is available to NVIDIA workloads.

### Status model

The GPU API will retain compatible fields while adding explicit facts:

- `mode`: `auto`, `manual`, or `disabled`
- `state`: `ready`, `disabled`, `docker_unavailable`,
  `toolkit_unavailable`, `no_gpus`, `policy_invalid`, or `probe_failed`
- `detected`: whether physical NVIDIA GPUs were discovered
- `container_toolkit_available`: whether Docker successfully served a GPU device
  request
- `usable_for_gpu_workflows`: whether at least one detected GPU is permitted
- `detected_count`
- `selected_count`
- `selected_gpu_uuids`
- per-GPU `uuid`, `selected`, and existing hardware fields
- structured `recommendation` and diagnostic `error`

The legacy `docker_nvidia_runtime` field remains during the compatibility window
but derives from observed container GPU capability rather than the presence of a
named Docker runtime or CLI binary.

### GPU policy

Configuration defaults:

```env
BIOINFOFLOW_GPU_MODE=auto
BIOINFOFLOW_GPU_DEVICES=all
```

Semantics:

- `auto`: probe automatically and allow every discovered NVIDIA GPU.
- `manual`: probe automatically and allow only UUIDs listed in
  `BIOINFOFLOW_GPU_DEVICES`.
- `disabled`: skip active GPU probing and prevent GPU workflow dispatch.

Device UUIDs are the canonical persisted identifiers. Numeric indices may be
accepted only as a documented convenience during environment parsing and must
be resolved to UUIDs before entering the policy model. Unknown or duplicated
selectors produce a `policy_invalid` state and no GPU workflow capacity.

The first implementation exposes configuration through environment variables.
The Dashboard reports the active policy and selected devices but does not edit
the deployment environment. This keeps the operational boundary honest: an
admin changes `.env`, recreates the backend, and verifies the new policy. A
future persisted settings UI can use the same policy interface without changing
discovery or workflow code.

### Scheduler and workflow integration

The scheduler resource snapshot will consume the selected GPU inventory rather
than invoking `nvidia-smi` independently. Its GPU count and available memory
therefore reflect the platform allowlist, not every host device.

GPU-aware workflow launchers will receive the selected UUID list from the shared
policy service. They must stop unconditionally setting
`NVIDIA_VISIBLE_DEVICES=all` when a restricted pool exists. CPU workflows remain
unchanged.

Where an engine supports Docker device IDs directly, it should request selected
UUIDs. Where an engine uses an existing Swarm or profile abstraction, it should
propagate the selected UUID list through the supported NVIDIA visibility
mechanism and continue enforcing the requested GPU count. Engine-specific
limitations must be documented rather than hidden behind a generic “ready”
label.

## Dashboard Redesign

### Existing system preservation

The redesign preserves:

- Next.js 16, React 19, Tailwind v4, and existing components
- Geist Sans and Geist Mono
- current warm neutral tokens, semantic status colors, dark mode, and radii
- the greeting, readiness center, statistic cards, recent activity, routes, and
  data-fetch behavior
- existing icon system

It introduces no new global token file or visual theme. Existing project tokens
remain the source of truth.

### Structural change

Replace the uneven System Status and Scheduler card pairing with one flat
operations surface:

```text
System status                                             Healthy
────────────────────────────────────────────────────────────────
Docker                 GPU                         Scheduler
Running                2 × NVIDIA H20             Queue 0
Socket accessible      Ready for workflows        Completed 14
                       Auto · all 2 selected
```

The surface contains one outer boundary only. Docker, GPU, and scheduler are
semantic sections separated by whitespace and hairline dividers, not nested
cards. Desktop uses three columns, with GPU receiving additional width when
details require it. Mobile stacks the sections and replaces vertical dividers
with horizontal rules.

The NVIDIA runtime label moves out of the Docker section because it describes
GPU container capability, not basic Docker health.

### GPU presentation states

Ready state:

- primary line: count and model, for example `2 × NVIDIA H20`
- secondary line: `Ready for GPU workflows`
- policy line: `Automatic · using all 2 GPUs` or
  `Manual · using 1 of 2 GPUs`
- compact device rows show selected state, UUID suffix, and total memory when
  multiple distinct GPUs need disambiguation

Failure states use one direct sentence and one action:

- Docker unavailable: start Docker and refresh.
- Toolkit unavailable: install/configure NVIDIA Container Toolkit, then recreate
  the backend.
- No GPUs: CPU workflows remain available; no NVIDIA device was returned.
- Policy invalid: correct `BIOINFOFLOW_GPU_DEVICES` using UUIDs listed by
  `nvidia-smi -L`, then recreate the backend.
- Disabled: set `BIOINFOFLOW_GPU_MODE=auto` or `manual`, recreate the backend,
  and refresh.
- Probe failed: show the safe diagnostic summary and link to the runbook.

Apple Silicon copy must distinguish “Apple GPU detected on the native host” from
“usable for NVIDIA container workflows.” It must never imply Parabricks
compatibility.

### Visual constraints

- No card inside another card.
- No new shadows, gradients, textures, background art, or decorative motion.
- No large colored status panels.
- Use semantic color only in compact badges, dots, or warning text.
- Use tabular figures for counts and memory values.
- Preserve accessible focus styles and reduced-motion behavior.
- Keep headings sentence case and operational copy direct.
- Verify responsive behavior at 320, 375, 414, and 768 pixels as well as the
  existing desktop breakpoints.

## Operator Documentation and Copy

Update both English and Simplified Chinese locale files. New copy must explain:

- automatic detection is the default
- no GPU-specific Compose file is required for the normal path
- CPU workflows continue when no GPU is available
- how to disable discovery
- how to restrict Bioinfoflow to selected GPU UUIDs
- why UUIDs are preferred over indices
- why changing `.env` requires recreating the backend container
- how to verify the host with `nvidia-smi` and Docker with a GPU test container
- the difference between hardware detection and workflow usability

Update `.env.example`, `RUNBOOK.md`, and Docker getting-started documentation.
The documented normal startup remains:

```bash
docker compose up -d --build
```

Manual selection example:

```env
BIOINFOFLOW_GPU_MODE=manual
BIOINFOFLOW_GPU_DEVICES=GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
```

Apply changes with:

```bash
docker compose up -d --build --force-recreate backend
```

The compatibility GPU override may be described as legacy or troubleshooting
only; normal instructions must not require it.

## Error Handling

- Docker connection failures never crash health or scheduler endpoints.
- Probe timeout and cleanup paths are tested independently.
- Probe stderr is sanitized and truncated before returning it through the API.
- Missing NVIDIA support produces a stable state code, not string matching in
  the frontend.
- Invalid policy never falls back silently to all GPUs.
- Cache failures preserve the last successful inventory only for a bounded
  stale window and label it stale; otherwise capacity becomes zero.
- CPU scheduling and non-GPU workflow execution remain available throughout.

## TDD Strategy

Implementation follows red-green-refactor in this order:

1. GPU mode and UUID allowlist parser tests.
2. Docker probe tests using a fake Docker client for success, no toolkit, no
   device, timeout, malformed output, cleanup, and concurrent request coalescing.
3. Shared inventory and policy tests covering auto, manual, disabled, invalid,
   and Apple Silicon semantics.
4. API and readiness envelope tests for every stable state code and backward
   compatible field.
5. Scheduler monitor tests proving it consumes selected shared inventory and no
   longer invokes its own `nvidia-smi` subprocess.
6. Engine tests proving CPU jobs are unchanged and GPU jobs receive the allowed
   UUID set instead of unconditional `all`.
7. Frontend component tests for ready, restricted, disabled, toolkit-missing,
   no-GPU, and probe-failed states in both narrow and desktop structure.
8. Dashboard integration tests for the single operations surface and removal of
   nested status cards.
9. Locale coverage and documentation checks.
10. Installer and Compose regression tests confirming no second image or
    mandatory GPU override is introduced.

Real-H20 verification is an additional deployment check, not a replacement for
automated tests. The PR will include copy-paste commands for verifying host
`nvidia-smi`, Docker GPU allocation, API output, and Dashboard display.

## Review and Verification

Before opening the PR:

- run focused tests after each red-green cycle
- run the full backend test suite and Ruff checks
- run frontend lint, i18n lint, dead-code lint, tests, and production build
- run `git diff --check`
- inspect the Dashboard in light and dark mode at desktop and required mobile
  widths
- perform a dedicated code review for Docker cleanup, privilege boundaries,
  stale-cache behavior, allowlist fail-closed behavior, engine propagation, API
  compatibility, copy clarity, and absence of nested cards
- run the Hallmark post-build restraint/slop review on the changed UI

Any command that requires an NVIDIA host will be clearly marked as not runnable
locally and supplied for the H20 deployment verification.

## Expected Implementation Surface

The detailed implementation plan will confirm exact files after TDD seam
inspection. Expected areas include:

- `backend/app/services/gpu_service.py`
- a focused GPU policy/probe module if separation improves testability
- `backend/app/scheduler/monitor.py`
- affected workflow engine adapters
- `backend/app/api/v1/system.py`
- backend service, API, scheduler, and engine tests
- `frontend/app/(app)/dashboard/components/system-status.tsx`
- `frontend/app/(app)/dashboard/components/scheduler-summary.tsx`
- `frontend/app/(app)/dashboard/page.tsx`
- Dashboard types, tests, and skeleton where necessary
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`
- `.env.example`
- `RUNBOOK.md`
- `docs/getting-started/docker.md`

No production file deletion is planned.

## Acceptance Criteria

- On a correctly configured H20 host, plain `docker compose up -d --build`
  reports the H20 inventory without loading `docker-compose.gpu.yml`.
- On a CPU host, the same command starts successfully and reports an actionable
  non-blocking GPU state.
- `auto` selects all detected NVIDIA GPUs.
- `manual` selects only configured UUIDs and rejects unknown values without
  falling back to all devices.
- `disabled` performs no active probe and advertises zero GPU workflow capacity.
- Scheduler and API counts match the selected pool.
- GPU workflow launch configuration never broadens a restricted selection to
  `all`.
- Dashboard displays Docker, GPU, and scheduler status in one flat surface with
  no nested cards.
- English and Chinese copy tell the operator exactly how to change modes,
  select GPUs, recreate the backend, and verify the result.
- Backend and frontend verification suites pass, review findings are resolved,
  and a Conventional Commit PR is opened.

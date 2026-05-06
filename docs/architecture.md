# Architecture

This is the canonical public architecture entrypoint for Bioinfoflow. For the
full implementation map, see [Architecture Reference](reference/architecture.md).

## System Shape

Bioinfoflow is a local-first web app for registering, running, and observing
bioinformatics workflows on infrastructure you control.

- `frontend/` is a Next.js App Router application.
- `backend/` is a FastAPI service with a Typer CLI (`bif`).
- Nextflow and WDL/MiniWDL execution live behind a workflow engine abstraction.
- A persistent scheduler owns queue depth, slots, resource checks, retries,
  timeouts, cleanup, and run completion hooks.
- `BIOINFOFLOW_HOME` is the shared platform root for state, inputs, references,
  caches, and outputs.

## Request And Run Flow

```text
browser or bif CLI
  -> FastAPI routes
  -> service layer
  -> repositories and storage roots
  -> run submission / DAG / lifecycle services
  -> scheduler dispatch
  -> Nextflow or WDL adapter
  -> logs, events, outputs
  -> SSE / REST / WebSocket back to frontend
```

The run service is intentionally thin. New business logic should go into focused
submission, DAG, lifecycle, archive, dispatch, scheduler, or engine modules
instead of growing a catch-all facade.

## Agent Runtime

Agent Runtime v2 lives in:

```text
backend/app/services/agent/runtime/
```

The default flow is:

```text
user input -> agent service -> async runtime loop -> tool dispatch -> persisted/SSE events -> frontend
```

Agent tools use `BaseTool` plus `@register_tool`. Risk levels are `read`,
`act_low`, and `act_high`, so higher-impact actions can be surfaced for review
instead of being hidden inside a chat transcript.

## Local-First Path Contract

Path Contract v3 requires the host, backend, workflow runner, and task
containers to see the same absolute paths under `BIOINFOFLOW_HOME`. Docker
Compose identity-mounts that root so workflow outputs and cached engine files
remain inspectable from both the UI and the host shell.

See [Storage And Data Layout](concepts/storage.md) for the storage model and
[Docker Quick Start](getting-started/docker.md) for deployment details.

# Glossary

This page keeps Bioinfoflow-specific terms grounded in the current codebase.

## Platform Terms

### `BIOINFOFLOW_HOME`

The absolute platform data root used by the backend, workflow runners, task
containers, and the UI. It stores state, auth data, project data, shared input
sources, engine caches, run inputs, and run outputs.

The repo-root `.env` is the default place to configure it. If unset under Docker
Compose, Bioinfoflow uses the repo-local `data/` directory.

### Identity-Mount Path Contract

Workflow execution assumes `BIOINFOFLOW_HOME_HOST` and `BIOINFOFLOW_HOME`
resolve to the same absolute path. Docker Compose bind-mounts the host
directory to the identical container path, so Nextflow, MiniWDL, backend code,
and task containers can pass absolute paths without translation.

### Run Workspace

The per-run directory under a project's `runs/<run_id>/` tree. It contains
materialized inputs, engine work directories, results, and audit metadata.

## Workflow Terms

### Engine Adapter

The interface implemented by the Nextflow and WDL adapters. It hides
engine-specific command generation, schema extraction, event parsing, and resume
behavior behind the common run scheduler.

### Execution Backend

The strategy used to launch a workflow engine. Current backend code includes
local process execution and containerized MiniWDL execution.

### Form Spec

A workflow input schema generated from Nextflow or WDL source. The backend
stores it with workflow metadata and the frontend uses it to render run forms.

## Scheduler Terms

### Persistent Scheduler

The database-backed queue in `backend/app/scheduler/`. It tracks priority,
slots, resource pressure, retry policy, timeout handling, cleanup, and
completion hooks. It survives backend restarts and recovers stale runs.

### Slot

A unit of scheduler concurrency. Workflows may have a weight, and the scheduler
dispatches only when enough slots and resources are available.

## Agent Terms

### Agent Runtime

The default agent orchestration path under
`backend/app/services/agent/runtime/`. It runs an explicit async loop for LLM
streaming, tool calls, context compaction, todo/task state, background commands,
skills, subagents, and SSE event delivery.

### Tool Dispatch

The map from model tool requests to Python tool implementations. Tools use
`BaseTool` plus `@register_tool` and carry a risk level: `read`, `act_low`, or
`act_high`.

### Approval

The review gate for high-impact agent actions. `act_high` tools route through
the approval service before side effects are executed.

## Abbreviations

| Term | Meaning |
| --- | --- |
| BIF | Bioinfoflow and the `bif` CLI |
| DAG | Directed acyclic graph, used to display workflow structure and progress |
| SSE | Server-Sent Events, used for run, image, and agent streams |
| WDL | Workflow Description Language |
| NF | Nextflow |
| WAL | SQLite write-ahead logging mode |

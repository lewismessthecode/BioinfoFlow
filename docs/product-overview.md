# Bioinfoflow — Product Overview

## One-Liner

Bioinfoflow is a local-first, AI-powered platform that lets bioinformatics researchers orchestrate complex pipelines through natural language — no cloud lock-in, no data leaving your machine.

## The Problem

Bioinformatics infrastructure is stuck between two bad options:

1. **Cloud platforms** (Terra, DNAnexus, Seven Bridges): powerful but expensive, lock in your data, and force you to upload sensitive genomic data to someone else's servers. Compliance headaches. Vendor lock-in.
2. **Raw CLI tools** (running Nextflow/WDL by hand): full control, but steep learning curve, no project management, no scheduling, no visibility into what's running. Every lab reinvents the same wrapper scripts.

Meanwhile, researchers are spending 30-60% of their time on infrastructure instead of science. They want to run `nf-core/rnaseq` on their data, not debug Nextflow config files.

## The Solution

Bioinfoflow sits on your machine (or your lab's server) and gives you:

- **An AI agent** that understands bioinformatics workflows — ask it to "run a differential expression analysis on these FASTQ files" and it figures out the pipeline, parameters, and execution.
- **Dual engine support** — runs both Nextflow and WDL/MiniWDL pipelines through a unified interface. Your existing workflows work unchanged.
- **A modern web UI** — project management, real-time run monitoring, DAG visualization, file browser, integrated terminal. Not another TUI.
- **A CLI tool (`bif`)** — for power users and automation. Full API coverage, streaming output, NDJSON for scripting.
- **A persistent scheduler** — resource-aware queue with retry, timeout, cleanup, and batch runs. No more babysitting long-running pipelines.

Everything runs locally. Your data never leaves your machine. SQLite database, zero external dependencies beyond an LLM API key.

## Who It's For

- **Bioinformatics researchers** who run pipelines regularly and are tired of infrastructure overhead.
- **Computational biology teams** who need project organization, audit trails, and shared visibility into runs.
- **Core facilities** processing samples for multiple labs — batch runs, scheduling, and resource management matter here.
- **Anyone with sensitive genomic data** who can't or won't upload to cloud platforms.

## How It Works

```
User (chat or CLI)
  → AI Agent (understands bioinformatics context, dispatches tools)
    → Workflow Engine (Nextflow or MiniWDL adapter)
      → Local Execution (with resource monitoring)
        → Real-time Results (SSE streaming to UI)
```

1. **You describe what you want** — in the chat UI or via `bif agent chat`.
2. **The agent plans and executes** — it reads your files, selects the right workflow, configures parameters, and validates inputs before submitting.
3. **The scheduler queues and runs** — respects resource limits (CPU, memory, disk, GPU), retries on failure, enforces timeouts.
4. **You watch in real-time** — DAG progress, logs, task status all stream to the UI via SSE. No refreshing.
5. **Results land in your project** — outputs, logs, and audit trail are organized per-project.

High-risk actions (like deleting runs or modifying configurations) go through an approval workflow — the agent asks before acting.

## Key Capabilities

| Capability | Status |
|---|---|
| Project management (CRUD, workspace isolation) | Shipped |
| AI agent chat with bioinformatics context | Shipped |
| Nextflow pipeline execution | Shipped |
| WDL/MiniWDL pipeline execution | Shipped |
| Persistent scheduler with priority queue | Shipped |
| Resource monitoring (CPU, memory, disk, GPU) | Shipped |
| Batch run submission and tracking | Shipped |
| DAG visualization (React Flow) | Shipped |
| Real-time log and status streaming (SSE) | Shipped |
| Integrated terminal (PTY + WebSocket) | Shipped |
| File browser and upload | Shipped |
| Docker image management | Shipped |
| Retry policies and timeout enforcement | Shipped |
| Audit logging | Shipped |
| Webhook notifications | Shipped |
| CLI tool (`bif`) with full API coverage | Shipped |
| i18n (English + Chinese) | Shipped |
| Multi-provider LLM support (Anthropic, OpenAI, Gemini) | Shipped |
| User authentication (Better Auth) | Scaffolded, not enforcing backend access |
| Multi-user / team features | Not yet |
| Remote execution backends | Not yet |

## Why Local-First

This is a deliberate architectural choice, not a limitation:

- **Data sovereignty** — genomic data is sensitive. HIPAA, GDPR, institutional policies often prohibit uploading to third-party clouds. Local-first means compliance by default.
- **No vendor lock-in** — your pipelines are standard Nextflow/WDL. Your data stays in your filesystem. Walk away anytime.
- **Cost** — lab GPUs and institutional HPC are already paid for. Cloud compute bills add up fast for genomics workloads.
- **Latency** — no upload/download overhead for large datasets. Run where the data lives.
- **Works offline** — except for the LLM API calls, everything runs without internet.

## Architecture at a Glance

- **Backend**: Python 3.13+, FastAPI, async SQLAlchemy, SQLite (via aiosqlite)
- **Frontend**: Next.js 16, React 19, Radix UI, Tailwind CSS 4, React Flow
- **Agent**: Runtime v2 — explicit async loop with tool dispatch, context compaction, between-turn hooks
- **Engines**: Nextflow adapter (GPU detection, resume support) + MiniWDL adapter
- **Scheduler**: DB-backed priority queue, resource gating, retry, timeout, cleanup, completion hooks
- **CLI**: Typer + Rich, 3 transport modes (remote/local/auto), streaming support
- **Auth**: Better Auth (session-based, frontend-enforced currently)
- **Realtime**: SSE fan-out for runs, agent events, image progress

## Current State — Honest Assessment

**What works well:**
- Full pipeline lifecycle from natural language to completion
- Scheduler handles concurrent runs with resource awareness
- The UI is genuinely useful — DAG visualization, real-time logs, file browser, terminal
- CLI is production-quality with proper error handling and streaming

**What's not there yet:**
- Auth is frontend-only scaffolding — backend API is open
- Single-node only — no distributed execution
- No multi-user collaboration features
- No pipeline marketplace or community sharing
- Test coverage is solid but not exhaustive for all edge cases

**What we're not building (for now):**
- Cloud execution backends — the wedge is local-first
- Pipeline authoring — we orchestrate existing Nextflow/WDL, not replace them
- Electronic lab notebooks — stay in your lane

## What's Next

Near-term priorities, grounded in what users have asked for:

1. **Backend auth enforcement** — close the gap between frontend auth and API access control
2. **Multi-user support** — team workspaces, role-based access, shared project visibility
3. **Remote execution** — SSH-based execution on lab servers and institutional HPC
4. **Pipeline templates** — curated starter configurations for common analyses (RNA-seq, variant calling, etc.)
5. **Improved agent capabilities** — better workflow recommendation, parameter tuning, result interpretation

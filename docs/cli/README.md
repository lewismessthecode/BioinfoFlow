# bif — Bioinfoflow CLI

## 1. What It Is

`bif` is the command-line interface for the Bioinfoflow platform. It provides full access to project management, workflow execution, run monitoring, file operations, and AI agent interactions — all from your terminal.

Two primary audiences:
- **Power users** who prefer terminal workflows for batch processing, scripting, and CI/CD
- **LLM-driven agents** that need structured, parseable output (JSON/NDJSON) for automated pipeline orchestration

## 2. Install and First Run

```bash
cd backend
uv sync
uv run bif --help
```

The `bif` entry point is defined in `pyproject.toml`:

```toml
[project.scripts]
bif = "app.cli.main:app"
```

For system-wide installation:

```bash
cd backend && uv pip install -e .
bif --help
```

## 3. Modes: auto / remote / local

`bif` supports three transport modes, selected via `--mode`:

| Mode | Behavior |
|------|----------|
| `auto` (default) | Try remote first; fall back to local on **connection failure** only. HTTP errors (4xx/5xx) are NOT retried locally |
| `remote` | HTTP calls to a running backend at `--base-url` |
| `local` | In-process via ASGI — no running server needed. Imports the FastAPI app, enters its lifespan (DB init, scheduler, seeding), and routes requests through `httpx.ASGITransport` |

```bash
# Explicit remote mode
bif --mode remote --base-url http://api.example.com/api/v1 project list

# Local mode (no server required)
bif --mode local project list

# Auto mode (default — tries remote, falls back to local)
bif project list
```

## 4. Default Config and Project Context

### Config File

Stored at `~/.config/bioinfoflow/cli.toml`. Initialize with:

```bash
bif config init
```

Set values:

```bash
bif config set mode remote
bif config set base_url http://localhost:8000/api/v1
bif config set output json
bif config use-project proj-abc123
```

View current config:

```bash
bif config show
```

```bash
bif config show --output json
# {"success": true, "data": {"mode": "remote", "base_url": "http://localhost:8000/api/v1"}}
```

### Resolution Priority

Config values are resolved in this order (highest to lowest):

1. CLI flags (`--mode`, `--project`, etc.)
2. Environment variables (`BIOFLOW_MODE`, `BIOFLOW_PROJECT`, etc.)
3. Config file (`~/.config/bioinfoflow/cli.toml`)
4. Defaults (`auto`, `http://localhost:8000/api/v1`, `human`)

### Global Options

```
--mode auto|remote|local       (env: BIOFLOW_MODE, default: auto)
--base-url <url>               (env: BIOFLOW_API_URL, default: http://localhost:8000/api/v1)
--project <project-id>         (env: BIOFLOW_PROJECT)
--output human|json            (env: BIOFLOW_OUTPUT, default: human)
--no-color                     (env: NO_COLOR)
--verbose                      (show request/response debug info)
```

## 5. Human Output vs JSON Output

### Human Mode (default)

Rich tables, panels, colors, and spinners for interactive use:

```bash
bif project list
# ┌──────────┬─────────┬────────────┬─────────────────────┐
# │ ID       │ Name    │ Workspace  │ Created             │
# ├──────────┼─────────┼────────────┼─────────────────────┤
# │ p-abc    │ RNAseq  │ /data/rna  │ 2025-01-15T10:30:00 │
# └──────────┴─────────┴────────────┴─────────────────────┘
```

### JSON Mode

For scripts and LLM agents. Emits the exact API envelope:

```bash
bif --output json project list
# {"success": true, "data": [{"id": "p-abc", "name": "RNAseq", ...}], "meta": {"request_id": "...", "timestamp": "..."}}
```

For streaming commands (`watch`, `logs --follow`, `chat`, `events stream`), JSON mode emits NDJSON — one JSON object per line:

```bash
bif --output json events stream --project p-abc
# {"event": "run.status", "data": {"status": "running"}}
# {"event": "run.log", "data": {"line": "Starting FASTQC..."}}
# {"event": "run.status", "data": {"status": "completed"}}
```

## 6. Project / Workflow / Run Quickstart

### Projects

```bash
# List projects
bif project list

# Create a project
bif project create --name "Viral Analysis" --workspace /data/viral

# Show project details
bif project show p-abc123

# Set as default project
bif project use p-abc123
# or: bif config use-project p-abc123

# Delete (with confirmation)
bif project delete p-abc123
bif project delete p-abc123 --force  # skip confirmation
```

### Workflows

```bash
# List available workflows
bif workflow list

# Register a new workflow
bif workflow register --name "RNAseq" --engine nextflow --source /path/to/main.nf

# Show workflow details
bif workflow show wf-abc

# View workflow source
bif workflow source wf-abc

# Bind workflow to project
bif workflow bind wf-abc --project p-abc

# Pin a workflow version
bif workflow pin wf-abc --project p-abc
```

### Runs

```bash
# Submit a run
bif run submit --workflow wf-abc --project p-abc --values '{"reference": "asset://reference/hg38.fa"}'

# Submit from a JSON spec file
bif run submit --workflow wf-abc --project p-abc --spec run-config.json

# Submit from stdin (for agents)
echo '{"project_id":"p-1","workflow_id":"wf-1","values":{"sample_id":"S1"}}' | bif run submit --workflow wf-1 --project p-1 --spec -

# List runs
bif run list --project p-abc
bif run list --status completed,failed --limit 50

# Show run details
bif run show r-abc

# Watch a run in real-time
bif run watch r-abc --project p-abc

# View logs
bif run logs r-abc
bif run logs r-abc --follow --project p-abc
bif run logs r-abc --task FASTQC --tail 50

# Cancel / retry / resume
bif run cancel r-abc
bif run retry r-abc
bif run resume r-abc --spec overrides.json

# Clean up run resources
bif run cleanup r-abc
```

JSON mode examples:

```bash
bif --output json run list --project p-abc
# {"success": true, "data": [...], "meta": {"pagination": {"has_more": true, "next_cursor": "..."}}}

bif --output json run show r-abc
# {"success": true, "data": {"run_id": "r-abc", "status": "running", ...}}
```

## 7. Batch Runs

```bash
# Submit a batch from a spec file
bif run batch submit --spec batch.json

# Show batch status
bif run batch show b-abc

# Cancel a batch
bif run batch cancel b-abc
```

Example `batch.json`:
```json
{
  "project_id": "p-abc",
  "runs": [
    {"workflow_id": "wf-1", "values": {"sample_id": "A"}},
    {"workflow_id": "wf-1", "values": {"sample_id": "B"}}
  ]
}
```

## 8. Files and Workspace Ops

Unix-style verbs for file management:

```bash
# List files
bif file ls p-abc
bif file ls p-abc --recursive --pattern "*.fastq.gz"

# View file contents
bif file cat p-abc /results/output.txt
bif file cat p-abc /results/output.txt --lines 50 --offset 100

# Upload a file
bif file upload p-abc /local/data.csv --dest /project/data/

# Download a file
bif file download p-abc /results/output.vcf --dest ./downloads/

# Scan workspace
bif file scan p-abc

# Remove a file
bif file rm p-abc /tmp/scratch.txt --force
```

### Run Outputs

```bash
# List outputs for a run
bif run outputs list r-abc

# Download run outputs
bif run outputs download r-abc --dest ./results/
bif run outputs download r-abc --file result.vcf --dest ./
```

## 9. Agent Commands

### Single-shot Message (non-interactive)

Ideal for LLM agents and scripts:

```bash
bif agent send "list all projects" --project p-abc
bif --output json agent send "analyze this sample" --project p-abc
```

### Interactive Chat

```bash
bif agent chat --project p-abc
# bif> list my projects
# [agent response...]
# bif> analyze the RNAseq results
# [agent response...]
# bif> /exit
```

In JSON mode, reads from stdin line-by-line and writes NDJSON:

```bash
echo "list projects" | bif --output json agent chat --project p-abc
```

Inline approval prompts appear during chat when the agent needs permission:

```
Approval needed for: execute_code
[y/n] > y
```

### History and Status

```bash
# View conversation history
bif agent history conv-abc

# Check if agent is running
bif agent status conv-abc

# Cancel a running agent
bif agent cancel conv-abc

# View execution trace
bif agent trace conv-abc
```

### Approvals

```bash
# List pending approvals
bif agent approvals list conv-abc --pending

# Approve or reject
bif agent approvals resolve approval-id approve
bif agent approvals resolve approval-id reject
```

## 10. Event Streaming for Agents

Raw SSE pass-through — useful for agents monitoring a project:

```bash
# Stream all events for a project
bif events stream --project p-abc

# Filter by run
bif events stream --project p-abc --run r-abc

# Filter by conversation
bif events stream --project p-abc --conversation conv-abc
```

In JSON mode, each event is a single NDJSON line:

```bash
bif --output json events stream --project p-abc
# {"event": "run.status", "data": {"run_id": "r-abc", "status": "running"}}
# {"event": "run.log", "data": {"line": "Processing sample A..."}}
# {"event": "agent.message", "data": {"content": "Analysis complete."}}
```

## 11. Doctor and Troubleshooting

```bash
bif doctor
# ┌──────────────┬────────┬──────────────────────┐
# │ Check        │ Status │ Details              │
# ├──────────────┼────────┼──────────────────────┤
# │ backend      │ pass   │ healthy              │
# │ scheduler    │ pass   │ mode=persistent      │
# │ gpu          │ pass   │ available            │
# │ nextflow     │ pass   │ /usr/local/bin/nf    │
# │ docker       │ pass   │ /usr/bin/docker      │
# └──────────────┴────────┴──────────────────────┘
```

```bash
bif --output json doctor
# {"success": true, "data": {"backend": {"ok": true, "detail": "healthy"}, ...}}
```

Checks performed:
- **Backend health** — `GET /system/health`
- **Scheduler status** — `GET /scheduler/status` (mode, queue depth)
- **GPU availability** — `GET /system/gpu`
- **Local binaries** — `nextflow`, `miniwdl`, `docker` (via `shutil.which`)

## 12. Exit Codes

| Code | Meaning | Example |
|------|---------|---------|
| 0 | Success | Command completed normally |
| 2 | User input error | Bad flags, missing `--project`, invalid JSON spec |
| 3 | Backend error | API returned 4xx/5xx (not found, validation, conflict) |
| 4 | Connection error | Can't reach API, local mode init failure |
| 1 | Other error | Unhandled exception |

Exit codes enable reliable scripting:

```bash
bif run submit --workflow wf-1 --project p-1
if [ $? -eq 3 ]; then
  echo "Backend error — check API logs"
elif [ $? -eq 4 ]; then
  echo "Cannot connect — is the server running?"
fi
```

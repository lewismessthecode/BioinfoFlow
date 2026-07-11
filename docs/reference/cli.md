# CLI Reference

`bif` is an HTTP client for a running Bioinfoflow backend. Use it for scripts,
local automation, and terminal-first workflows.

Run it from `backend/` during local development:

```bash
uv sync
uv run bif --version
uv run bif --help
```

## Global Options

The main Typer callback supports:

```text
--base-url <url>
--project <project-id> / -p <project-id>
--output human|json
--no-color
--quiet / -q
--verbose / -v
--version / -V
--help / -h
```

Defaults from the current implementation:

- `--base-url`: `http://localhost:8000/api/v1`
- `--output`: `human`

`NO_COLOR` or `--no-color` disables Rich color output.

## Config Resolution

The CLI resolves values in this order:

1. CLI flag
2. environment variable
3. `~/.config/bioinfoflow/cli.toml`
4. built-in default

Environment variables:

- `BIOFLOW_API_URL`
- `BIOFLOW_PROJECT`
- `BIOFLOW_OUTPUT`

## Backend Target

`bif` is an HTTP client for a running Bioinfoflow backend. Start the backend
first, or point the CLI at another API with `--base-url` / `BIOFLOW_API_URL`.

## Registered Command Groups

The CLI includes these command groups:

- `config`
- `project`
- `workflow`
- `file`
- `system`
- `events`
- `open`
- `run`
- `run outputs`
- `run batch`
- `agent`
- `doctor`

The `agent` group includes interactive and scripting commands for AgentCore:

- `agent send`
- `agent chat`
- `agent events`
- `agent stream`
- `agent cancel`
- `agent interrupt`
- `agent toolsets`
- `agent session`
- `agent turn`
- `agent action`
- `agent artifacts`

Use command-specific help for exact parameters:

```bash
uv run bif run --help
uv run bif workflow --help
uv run bif agent --help
uv run bif agent action --help
```

## JSON Output

Use JSON mode for scripts and automation:

```bash
uv run bif --output json project list
uv run bif --output json run show <run-id>
```

The project conventions use the standard API envelope:

```json
{"success": true, "data": {}, "meta": {}}
```

Streaming commands may emit newline-delimited JSON.

## Common Commands

```bash
uv run bif doctor
uv run bif project list
uv run bif project create --name "RNA-seq" --external-root /data/projects/rnaseq
uv run bif config use-project <project-id>
uv run bif workflow list
uv run bif run list
uv run bif run show <run-id>
uv run bif run outputs list <run-id>
uv run bif run cancel <run-id> --force
uv run bif events stream
uv run bif open agent
uv run bif agent session list
uv run bif agent send --session <session-id> "Check the latest run logs"
```

# CLI Reference

The `bif` CLI is defined in `backend/app/cli/main.py` and registered as:

```toml
[project.scripts]
bif = "app.cli.main:app"
```

Run it from `backend/` during local development:

```bash
uv sync
uv run bif --version
uv run bif --help
```

## Global Options

The main Typer callback supports:

```text
--mode auto|remote|local
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

- `--mode`: `auto`
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

- `BIOFLOW_MODE`
- `BIOFLOW_API_URL`
- `BIOFLOW_PROJECT`
- `BIOFLOW_OUTPUT`

## Transport Modes

| Mode | Behavior |
| --- | --- |
| `remote` | Use HTTP against `--base-url`. |
| `local` | Use the FastAPI app in-process through the local transport. |
| `auto` | Try the configured remote URL, then fall back to local transport on connection failure. |

## Registered Command Groups

`backend/app/cli/main.py` currently registers:

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
- `agent approvals`
- `doctor`

Use command-specific help for exact parameters:

```bash
uv run bif run --help
uv run bif workflow --help
uv run bif agent --help
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
uv run bif config use-project <project-id>
uv run bif workflow list
uv run bif run list
uv run bif run show <run-id>
uv run bif run cancel <run-id> --force
```

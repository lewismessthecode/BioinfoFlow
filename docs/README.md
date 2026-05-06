# Bioinfoflow Docs

Source-of-truth documentation for the Bioinfoflow platform, written against the current codebase.

## Start Here

- [Docker Quick Start](getting-started/docker.md): shortest path to run the app with Docker Compose.
- [Runbook](../RUNBOOK.md): setup, troubleshooting, and operational checks.
- [Storage And Data Layout](concepts/storage.md): what `BIOINFOFLOW_HOME` means, where files live, and how asset URIs resolve.
- [CLI Reference](reference/cli.md): `bif` commands, transports, JSON output, and scripting behavior.

## Product And Workflows

- [Parabricks WGS Workflows](workflows/parabricks-wgs.md): included NVIDIA Parabricks v4.7.0 Nextflow and WDL examples.
- [Security Notes](security.md): Docker socket, auth, host allowlists, and deployment boundaries.

## Engineering Reference

- [Architecture Reference](reference/architecture.md): current backend, frontend, engine, scheduler, realtime, auth, and agent boundaries.
- [Operations Supplement](operations/runbook.md): deployment/runtime context after the base setup works.

## Archive

Historical design notes, old plans, mockups, and local research artifacts live under ignored `docs/_legacy/` paths in development workspaces. The tracked docs above are the current public docs set.

## Maintenance Rules

1. Update `getting-started/docker.md`, `../RUNBOOK.md`, and `.env.example` together when Docker/env startup changes.
2. Update `concepts/storage.md` when `backend/app/config.py` or `backend/app/path_layout.py` changes storage roots or asset URI resolution.
3. Update `reference/cli.md` when `backend/app/cli/` changes command names, transports, output modes, or config resolution.
4. Update `reference/architecture.md` when backend/frontend runtime boundaries, scheduler behavior, engine execution, auth behavior, or realtime delivery changes.
5. Keep `docs/plans/` for active work only.

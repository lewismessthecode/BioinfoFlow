# Bioinfoflow Docs

Source-of-truth documentation for the Bioinfoflow platform, written against the current codebase.

## Start Here

- [Docker Quick Start](getting-started/docker.md): shortest path to run the app with Docker Compose.
- [Runbook](../RUNBOOK.md): setup, troubleshooting, and operational checks.
- [Storage And Data Layout](concepts/storage.md): what `BIOINFOFLOW_HOME` means, where files live, and how asset URIs resolve.

## Guides

- [Remote Connections](guides/remote-connections.md): save SSH profiles, test backend SSH access, open remote project terminals, stream probes, and use selected hosts with AgentCore.
- [Storage And Data Layout](concepts/storage.md): use managed project storage, external project roots, shared references, and run outputs.
- [Parabricks WGS Workflows](workflows/parabricks-wgs.md): run the included NVIDIA Parabricks v4.7.0 Nextflow and WDL examples.

## Reference

- [CLI Reference](reference/cli.md): `bif` commands, backend target selection, JSON output, and scripting behavior.
- [Architecture Reference](reference/architecture.md): backend, frontend, engine, scheduler, realtime, auth, AgentCore, and remote connection boundaries.
- [Glossary](reference/glossary.md): Bioinfoflow-specific terms.
- [Security Notes](security.md): Docker socket, auth, host allowlists, and deployment boundaries.

## Operations And Development

- [Operations Supplement](operations/runbook.md): deployment/runtime context after the base setup works.
- [GitHub CI/CD](development/github-ci-cd.md): CI, container release, and automation notes for maintainers.

## Maintainer Notes

Historical design notes, old plans, mockups, and local research artifacts live under ignored `docs/_legacy/` paths in development workspaces. The tracked docs above are the current public docs set.

Keep docs in sync with implementation changes:

- Update `getting-started/docker.md`, `../RUNBOOK.md`, and `.env.example` together when Docker or environment startup changes.
- Update `concepts/storage.md` when storage roots, external project roots, or asset URI resolution changes.
- Update `guides/remote-connections.md` when SSH connection behavior, auth methods, or remote AgentCore tools change.
- Update `reference/cli.md` when `backend/app/cli/` changes command names, backend target selection, output modes, or config resolution.
- Update `reference/architecture.md` when backend/frontend runtime boundaries, scheduler behavior, engine execution, auth behavior, realtime delivery, AgentCore, or remote execution changes.
- Keep `docs/plans/` for active work only.

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
- [Release Maintainer SOP](development/releases.md): version policy, Release PR review, bootstrap, verification, and recovery.
- [GitHub CI/CD](development/github-ci-cd.md): CI, container release, and automation notes for maintainers.
- [Icon System](development/icon-system.md): frontend icon adapter and control-state conventions.

## Runnable Examples

- [nf-core/rnaseq](../demo/nfcore-rnaseq/README.md): onboarding smoke test for a real nf-core Nextflow pipeline; read its verification record before treating acceptance targets as proven.
- [Parabricks WGS](workflows/parabricks-wgs.md): guide to the included GPU-oriented Nextflow and WDL examples.
- Focused WDL fixtures under [`demo/`](../demo/) exercise retry boundaries, resource fanout, subworkflow imports, file fanout, and small RNA-seq-shaped flows. Their READMEs describe acceptance checks unless a `VERIFIED.md` file records an actual run.

## Contributor Maps

- [Backend README](../backend/README.md): backend setup, storage inputs, and test commands.
- [Codemaps](../codemaps/INDEX.md): current source-tree maps for architecture, backend, frontend, data, and dependencies.

## Document Classes

- Public user documentation: the root READMEs and current guides, concepts, workflows, references, and security pages linked above.
- Operator documentation: the root runbook, Docker quick start, storage model, security notes, and operations supplement.
- Contributor documentation: `AGENTS.md`, `CLAUDE.md`, `backend/README.md`, development pages, test READMEs, and codemaps.
- Historical records: existing files under `docs/plans/` and `backend/docs/refactor*`. They may describe proposed or superseded designs and are not evidence of shipped behavior.

## Maintainer Notes

Historical design notes and refactor records are retained for context but are not part of the current public product contract. The tracked pages listed above are the canonical current documentation set.

Keep docs in sync with implementation changes:

- Update `getting-started/docker.md`, `../RUNBOOK.md`, and `.env.example` together when Docker or environment startup changes.
- Update `concepts/storage.md` when storage roots, external project roots, or asset URI resolution changes.
- Update `guides/remote-connections.md` when SSH connection behavior, auth methods, or remote AgentCore tools change.
- Update `reference/cli.md` when `backend/app/cli/` changes command names, backend target selection, output modes, or config resolution.
- Update `reference/architecture.md` when backend/frontend runtime boundaries, scheduler behavior, engine execution, auth behavior, realtime delivery, AgentCore, or remote execution changes.
- Keep `docs/plans/` for active work only.

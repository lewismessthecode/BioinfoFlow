---
title: "Validate nf-core/rnaseq demo on Apple Silicon Docker"
labels: ["launch", "demo", "macos", "apple-silicon"]
---

## Context

Many launch readers will try the project on an Apple Silicon Mac with Docker
Desktop. We need an explicit verification record for that path.

## Scope

- Use a fresh clone on Apple Silicon.
- Run `docker compose up -d --build`.
- Run `demo/nfcore-rnaseq/run-direct.sh`.
- Submit the pinned `nf-core/rnaseq@3.24.0` workflow through Bioinfoflow.

## Acceptance Criteria

- [ ] Mac model, macOS version, and CPU architecture are recorded.
- [ ] Docker Desktop and Nextflow versions are recorded.
- [ ] Direct run exits `0` in under 30 minutes after Docker is installed.
- [ ] Bioinfoflow run page shows logs, DAG progress, and outputs.
- [ ] Any architecture-specific container issue is captured with logs.

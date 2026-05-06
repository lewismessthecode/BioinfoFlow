---
title: "Validate nf-core/rnaseq demo on Linux amd64 fresh clone"
labels: ["launch", "demo", "linux"]
---

## Context

The canonical launch demo needs one clean Linux amd64 verification run from a
fresh clone. This proves the documented path works outside the primary
development machine.

## Scope

- Start Bioinfoflow with `docker compose up -d --build`.
- Run `demo/nfcore-rnaseq/run-direct.sh`.
- Submit the same pinned workflow through Bioinfoflow.
- Record results in `demo/nfcore-rnaseq/VERIFIED.md`.

## Acceptance Criteria

- [ ] Fresh Linux amd64 machine and commit SHA are recorded.
- [ ] Docker and Nextflow versions are recorded.
- [ ] Direct Nextflow run exits `0` in under 30 minutes.
- [ ] Bioinfoflow run completes and shows logs, DAG, and outputs.
- [ ] Any setup friction is documented as a follow-up issue.

---
title: "Persist and surface Nextflow work/cache metadata for resume"
labels: ["enhancement", "backend", "nextflow"]
---

## Context

Users need to understand whether a failed or interrupted run can be resumed.
Bioinfoflow should make Nextflow work directories, run names, and resume tokens
easy to inspect.

## Scope

- Audit current run metadata for Nextflow work/cache paths.
- Surface resume-relevant metadata on run detail and CLI output.
- Document when resume is safe and when a clean rerun is better.

## Acceptance Criteria

- [ ] Run detail exposes Nextflow work directory and run name when available.
- [ ] `bif run show --output json` includes resume-relevant metadata.
- [ ] Resume docs explain cache invalidation risks.
- [ ] Tests cover metadata persistence for completed and failed runs.

---
title: "Document Apptainer/Singularity runner path for lab servers"
labels: ["docs", "workflow-engines", "launch"]
---

## Context

Lab servers often prefer Apptainer or Singularity over Docker. Bioinfoflow can
launch Nextflow pipelines, but the public docs should explain the supported
path and current limitations.

## Scope

- Add a short docs page for Nextflow container profiles on shared servers.
- Explain what is currently tested with Docker only.
- List environment variables and mounts that matter for Path Contract v3.

## Acceptance Criteria

- [ ] Docs describe when Docker is required and when Apptainer/Singularity is expected to work.
- [ ] Path Contract v3 implications are explicit.
- [ ] The nf-core/rnaseq demo docs link to the lab-server follow-up.
- [ ] Unsupported combinations are named honestly.

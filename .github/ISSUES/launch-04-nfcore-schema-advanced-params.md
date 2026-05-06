---
title: "Improve nf-core schema rendering for advanced parameters"
labels: ["enhancement", "frontend", "nf-core"]
---

## Context

nf-core workflows expose rich JSON schemas. The current form experience should
make common parameters easy while keeping advanced settings discoverable.

## Scope

- Review how `nextflow_schema.json` sections render today.
- Identify hidden, enum, minimum, maximum, file, directory, and boolean fields.
- Improve grouping or metadata display where the current UI loses context.

## Acceptance Criteria

- [ ] At least one real nf-core schema is used as a fixture.
- [ ] Advanced parameters remain searchable or expandable.
- [ ] Required fields and defaults are visibly distinct.
- [ ] Existing workflow form tests cover the improved behavior.

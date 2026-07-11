# Documentation Audit Design

**Goal:** Bring Bioinfoflow's current public, operator, contributor, demo, and codemap documentation into alignment with the shipped repository while preserving historical plans unchanged.

## Evidence policy

Claims are verified in this order: current code and configuration; CLI help, API routes, tests, and migrations; current demos and verified examples; existing public documentation; public references supplied by maintainers. Existing plans are discovery aids only and never evidence that a feature shipped.

## Scope

The audit covers `README.md`, `README.zh-CN.md`, `RUNBOOK.md`, current pages under `docs/`, demo README files, `backend/README.md`, and `codemaps/`. Existing files under `docs/plans/` and `backend/docs/refactor*` are historical records and will not be edited.

## Method

1. Classify documents by audience and identify the canonical page for each topic.
2. Compare user-facing commands, configuration, URLs, defaults, product behavior, and prerequisites with trusted implementation sources.
3. Repair incorrect or missing claims, inconsistent terminology, duplicate guidance, and broken internal links.
4. Keep the current documentation hierarchy unless a link or canonical-source correction requires a small structural adjustment.
5. Keep the English and Chinese root READMEs aligned where they describe the same behavior.
6. Exclude roadmap material, private details, credentials, incidents, and unsupported speculation from public pages.

## Output boundaries

Historical documents remain untouched. The audit may report that historical material exists, but current documentation will not present it as shipped behavior. Claims that cannot be proved will be removed, qualified, or reported rather than guessed.

## Verification

Verification includes Markdown whitespace checks, internal-link validation, CLI help checks, environment-variable comparison, relevant i18n checks, and focused implementation checks needed to substantiate changed claims.

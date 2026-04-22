# Run Contract Refactor Plan

## Goal

Replace the current schema-first run submission flow with a simpler and more stable model:

`workflow executable` + `user-defined run contract` + `run values`

The workflow registration step guarantees the workflow can be stored, versioned, and executed.
The run contract step defines how users should provide inputs for that workflow.
The submission step only fills values against that saved contract.

## Why change

The current flow has become hard to reason about because one screen is trying to do too many jobs at once:

1. Parse engine schema
2. Infer user-facing input semantics
3. Inspect workspace and prefill likely values
4. Decide layout sections
5. Build execution payload

This produces brittle behavior:

- fields appear or disappear depending on heuristics
- workflow card entry and step-1 entry can still diverge
- Nextflow params are often too ambiguous to become a good UI automatically
- the frontend owns too much guesswork

## New product model

### 1. Workflow

Stored exactly as today:

- source, engine, version, source_url
- schema_json remains optional support metadata

### 2. Run Contract

New saved per-workflow artifact.

Each row describes one user-facing input definition:

- `id`
- `workflow_id`
- `label`
- `engine_key`
- `section`
  - `input_data`
  - `run_parameters`
  - `expert_inputs`
- `value_shape`
  - `single_file`
  - `multi_file`
  - `path_pattern`
  - `table`
  - `text`
  - `number`
  - `boolean`
  - `select`
- `format_kind`
  - `csv`
  - `tsv`
  - `txt`
  - `json`
  - `fq_path`
  - `bam`
  - `vcf`
  - `fasta`
  - `any`
- `storage_mode`
  - `param`
  - `input`
  - `render_file_then_param`
  - `render_file_then_input`
- `required`
- `help_text`
- `default_value`
- `table_columns` for `table`
- `select_options` for `select`
- `sort_order`

### 3. Run Submission

The dialog no longer decides structure from schema.
It only:

1. loads the saved run contract
2. renders fields from the contract
3. collects values
4. materializes file outputs if needed
5. submits to `/runs` or `/runs/wizard`

## Recommended user flow

### Option A: Registration does not require contract

Recommended default.

Flow:

1. user registers workflow
2. workflow is immediately available in the project
3. first click on `Run` checks whether a run contract exists
4. if not, open `Create Run Contract`
5. save contract
6. continue into standard run submission

Why this is better:

- keeps registration lightweight
- avoids blocking users who only want to inspect or version workflows
- moves input design into the moment when the user actually understands what they need

### Option B: Ask during registration

Possible later, but not the first refactor.

This adds friction too early and will make workflow registration feel heavier.

## Role of automatic parsing after refactor

Automatic parsing should not disappear completely, but it should be demoted.

New role:

- provide optional starter suggestions
- never directly control final layout
- never be the source of truth for the submission UI

Examples:

- suggest rows from `schema_json.inputs`
- suggest `reads`, `reference`, `samplesheet`, `outdir`
- suggest likely value shapes and file formats

The user can accept, edit, or discard those suggestions.

## Frontend refactor plan

### Remove or simplify

- simplify `frontend/app/(app)/workflows/components/run-submission-wizard.tsx`
- remove schema-driven section partitioning from `frontend/lib/schema-resolver.ts`
- stop using schema as the primary render source in `step-configure-params.tsx`
- reduce `samplesheet-editor.tsx` from special-case workflow logic into a generic table field renderer

### Add

- `frontend/lib/run-contract.ts`
  - types for contract rows and render adapters
- `frontend/app/(app)/workflows/components/run-contract-builder.tsx`
  - Notion-like contract table editor
- `frontend/app/(app)/workflows/components/run-contract-empty-state.tsx`
  - shown when workflow has no contract yet
- `frontend/app/(app)/workflows/components/run-contract-submit-form.tsx`
  - renders saved contract into submission form
- `frontend/app/(app)/workflows/components/contract-fields/table-field.tsx`
  - generic table renderer for csv/tsv/txt/json-backed data
- `frontend/app/(app)/workflows/components/contract-fields/path-pattern-field.tsx`
  - for fq path and similar path-based inputs

### New dialog states

The single dialog can remain, but internally it becomes:

1. `no_contract`
2. `edit_contract`
3. `submit_run`

This is much easier to reason about than the current schema hydration path.

## Backend refactor plan

### Keep

- workflow registration pipeline
- schema extraction as optional metadata
- `/runs/profile-preview` only as optional prefill helper

### Add

- `workflow_run_contracts` table
- `workflow_run_contract_rows` table
- CRUD API:
  - `GET /workflows/{id}/run-contract`
  - `PUT /workflows/{id}/run-contract`
  - `POST /workflows/{id}/run-contract:suggest` optional

### Simplify run creation

The backend should accept a normalized payload:

- `workflow_id`
- `workspace`
- `params`
- `inputs`
- `materialized_files`
- `config_overrides`

Materialization rules come from the run contract, not from frontend schema heuristics.

## Migration strategy

### Phase 1

Add run contracts without removing current schema-based fallback.

- existing workflows still open old submit flow if no contract exists
- new UX available behind a feature flag or per-workflow opt-in

### Phase 2

Make run contract the default path.

- no contract => show empty state and contract builder
- old schema fallback only available as emergency fallback

### Phase 3

Delete most schema-to-UI heuristics.

- keep schema extraction for DAG, docs, and starter suggestions
- stop using schema directly as the primary submit renderer

## Biggest simplification wins

1. The UI becomes deterministic.
2. The frontend no longer has to infer business meaning from engine params.
3. The same workflow behaves consistently across different entry points.
4. Complex workflows become configurable without adding more special cases.
5. The codebase regains a clean separation:
   - engine metadata
   - user-facing contract
   - run values

## Risks

1. A fully freeform table without required structural columns will create invalid runs.
2. If contract editing is too hard, users will still feel friction.
3. If we keep both systems alive for too long, complexity will double temporarily.

## Recommendation

Proceed with:

- lightweight workflow registration
- first-run contract creation
- saved contract-driven submission
- schema parsing only as optional suggestion input

This is the cleanest path to simplify both UX and code structure.

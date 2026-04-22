# Submission Document Editor — Design Spec

**Date:** 2026-04-03
**Status:** Draft
**Supersedes:** `2026-04-02-run-submission-ux-design.md`, `docs/plans/2026-04-03-run-contract-refactor.md`

## Context

The current run submission wizard uses a 3-step flow where Step 2 auto-generates form fields from workflow schemas via ~250 lines of heuristic pattern matching in `schema-resolver.ts`. This approach is brittle: fields appear/disappear based on naming conventions, and the mental model ("fill in a complex form") doesn't match how bioinformaticians actually submit workflows.

In reality, workflow submission without a frontend involves preparing one of:
- **samplesheet.csv** — for multi-sample Nextflow workflows (especially nf-core)
- **params.json** — for complex Nextflow parameter sets
- **inputs.json** — for WDL workflows

The new design aligns the UI with these native submission modes instead of abstracting them behind auto-generated forms.

## Design Overview

### Two-Step Flow

Replace the 3-step wizard with a 2-step flow:

1. **Select Workflow** — search and pick a workflow (existing step, refined)
2. **Edit & Submit** — a single-page "submission document editor" with:
   - **Run Settings Strip** (top): workspace, outdir, profile, collapsible advanced options
   - **Mode Tabs**: Table | JSON — auto-detected, user can override
   - **Document Editor** (center): mode-specific editor area
   - **Submit Bar** (bottom): one-line summary + submit button (replaces the review step)

The editor IS the review. What you see is what gets submitted.

### Two Submission Modes

**Table Mode** — for samplesheet-based workflows:
- Spreadsheet-style editor for CSV/TSV data
- Paste from clipboard (TSV), import CSV file, add/remove rows
- Column definitions from `submission_hint` (name, required, suffixes)
- Path columns get file path suggestions
- Below the table: "Additional Parameters" section for non-samplesheet params (genome, aligner, etc.) — derived from `schema_json.inputs` by excluding the samplesheet param and outdir
- Outputs: samplesheet CSV + extra params

**JSON Mode** — for everything else:
- Raw code editor with syntax highlighting
- Upload JSON file or download template from schema
- Real-time JSON validation (valid/invalid indicator)
- Outputs: inputs.json (WDL) or params.json (Nextflow)

### Auto-Detection Logic

| Signal | Default Mode |
|--------|-------------|
| Schema has samplesheet-like param (nf-core patterns) | Table |
| Engine = WDL | JSON |
| Complex Nextflow params, no samplesheet | JSON |

User can always switch modes manually. A "why?" tooltip explains the auto-detection reasoning.

## Backend Changes

### 1. `submission_hint` field on Workflow model

Add a nullable JSON field to the existing `Workflow` model:

```python
# backend/app/models/workflow.py
submission_hint: Mapped[dict | None]  # New field
```

Structure:

```json
{
  "default_mode": "table",
  "table": {
    "filename": "samplesheet.csv",
    "columns": [
      { "name": "sample", "required": true },
      { "name": "fastq_1", "required": true, "suffixes": [".fastq.gz"] },
      { "name": "fastq_2", "required": false, "suffixes": [".fastq.gz"] }
    ]
  },
  "json": {
    "filename": "inputs.json",       // "inputs.json" for WDL, "params.json" for Nextflow
    "template": {                     // Pre-filled from schema, used for "Download Template"
      "VariantCalling.input_bam": "",
      "VariantCalling.reference_fasta": "",
      "VariantCalling.scatter_count": 6
    }
  }
}
```

Auto-populated by `SchemaExtractor` during workflow registration. The existing heuristics from `schema-resolver.ts` move server-side into a `build_submission_hint()` function.

**Files to modify:**
- `backend/app/models/workflow.py` — add field
- `backend/app/schemas/workflow.py` — add to WorkflowBase/WorkflowRead
- `backend/app/engine/schema_extractor.py` — add `build_submission_hint()` call
- New Alembic migration for the column addition

### 2. Unified `POST /runs` schema

Replace the dual-endpoint system (`/runs` + `/runs/wizard`) with a single unified endpoint:

```python
# backend/app/schemas/run.py
class RunCreate(BaseModel):
    project_id: UUID
    workflow_id: UUID
    workspace: str = "."
    outdir: str = "results"

    # Submission document
    submission_mode: Literal["table", "json"]

    # Table mode fields
    table_rows: list[dict[str, str]] | None = None
    table_filename: str | None = None  # e.g. "samplesheet.csv"

    # JSON mode fields
    json_inputs: dict | None = None

    # Additional params (table mode: non-samplesheet params)
    extra_params: dict | None = None

    # Run policy
    config_overrides: dict | None = None
    retry_policy: RetryPolicyCreate | None = None
    timeout_seconds: int | None = Field(default=None, ge=1)
```

**Processing in RunService:**
- **Table mode**: `table_rows` → write samplesheet CSV to workspace → build params with `--input <samplesheet>` + merge `extra_params`
- **JSON mode**: `json_inputs` → write to file → pass via `--params-file` (Nextflow) or `-i` (WDL)

Both modes produce a `RunConfigHelper.build_v1()` config — the downstream execution path is unchanged.

**Files to modify:**
- `backend/app/schemas/run.py` — update RunCreate, deprecate RunWizardCreate
- `backend/app/api/v1/runs.py` — update create_run handler, deprecate wizard endpoint
- `backend/app/services/run_service.py` — update create_run logic

### 3. Deprecate `/runs/wizard`

Keep the endpoint for backward compatibility but mark it deprecated. The new frontend exclusively uses the unified `POST /runs`.

## Frontend Changes

### Component Architecture

```
RunSubmissionDialog (dialog shell)
├── StepWorkflowSelect (step 1 — reuse existing)
└── SubmissionEditor (step 2 — NEW)
    ├── RunSettingsStrip
    │   └── AdvancedOptions (reuse existing)
    ├── ModeTabBar
    ├── TableEditor (mode = "table")
    │   ├── TableToolbar (paste TSV, import CSV, add row)
    │   ├── SamplesheetGrid
    │   │   └── CellInput (text or path suggest)
    │   └── ExtraParamsSection
    └── JsonEditor (mode = "json")
        ├── JsonToolbar (upload JSON, download template)
        └── CodeEditor (syntax-highlighted textarea)
```

### State

```typescript
type ColumnDef = {
  name: string
  required: boolean
  suffixes?: string[]   // file type hints for path suggestions
  type: "text" | "path" // path columns get PathSuggestInput
}

type EditorState = {
  mode: "table" | "json"
  workspace: string
  outdir: string
  profile: string | null
  advancedOptions: AdvancedOptionsState
  tableRows: Record<string, string>[]
  tableColumns: ColumnDef[]
  jsonContent: string
  extraParams: Record<string, unknown>
}
```

Local React state (useState hooks). No global store needed.

### Reused Components
- `StepWorkflowSelect` — step 1, as-is
- `AdvancedOptions` — retry/timeout UI
- `PathSuggestInput` — for table cell file paths
- `apiRequest` utility
- i18n pattern with `useTranslations("workflows.submission")`

### New Components
- `SubmissionEditor` — main step 2 orchestrator
- `ModeTabBar` — Table | JSON toggle with auto-detection display
- `TableEditor` — enhanced samplesheet spreadsheet
- `JsonEditor` — raw JSON code editor
- `RunSettingsStrip` — compact workspace/outdir/profile bar
- `SubmitBar` — summary line + submit button

### Removed Components
- `StepConfigureParams` — replaced by `SubmissionEditor`
- `StepReviewSubmit` — replaced by `SubmitBar` (inline review)
- `StepIndicator` — simplified for 2 steps
- `schema-form.tsx` — no longer needed (schema-driven forms removed)
- Most form field components (`form-fields/`) — only `PathSuggestInput` survives

### Simplified `schema-resolver.ts`

The file shrinks from ~250 lines to ~50 lines. Remaining functions:
- `readSubmissionHint(workflow)` — extract hint from workflow object
- `detectDefaultMode(workflow)` — fallback mode detection when no hint exists
- `buildTableColumns(hint)` — convert hint columns to editor column defs
- `buildJsonTemplate(hint)` — extract JSON template for download

The ~15 heuristic pattern-matching functions (`isSamplesheetParam`, `resolveWidget`, `inferSamplesheetColumns`, etc.) are removed from the frontend. Their logic moves to the backend's `build_submission_hint()`.

## Table Editor Capabilities

- **Paste TSV**: detect clipboard content, parse tab-separated rows, append to table
- **Import CSV/TSV**: file upload, parse, replace or append rows
- **Add/remove rows**: row-level operations
- **Column-aware input**: path columns use `PathSuggestInput` with suffix filtering; ID columns use plain text input
- **Row count badge**: "N samples" indicator
- **Max rows**: 500 (existing limit, preserved)
- **Empty row filtering**: skip rows with all empty values on submit

## JSON Editor Capabilities

- **Raw text editor**: monospace textarea with line numbers
- **Syntax highlighting**: basic JSON syntax coloring (keys, strings, numbers, booleans)
- **Real-time validation**: "Valid JSON · N fields" or "Invalid JSON: error message"
- **Upload JSON**: file picker, replaces editor content
- **Download template**: generates template from `submission_hint.json.template` or from `schema_json` inputs
- **No template view**: raw editing only (per user preference)

## Testing Plan

### Backend Tests

| Test File | Coverage |
|-----------|----------|
| `test_submission_hint.py` | Hint generation for nf-core, plain NF, WDL schemas |
| `test_unified_run_create.py` | Unified POST /runs with table and json modes |
| `test_run_service_submission.py` | Table rows → CSV, JSON → file, param merging |

### Frontend Tests

| Test File | Coverage |
|-----------|----------|
| `submission-editor.test.tsx` | Full editor integration: mode switching, submit payloads |
| `table-editor.test.tsx` | Paste TSV, import CSV, add/remove rows, validation |
| `json-editor.test.tsx` | Syntax validation, upload, template download |
| `schema-resolver.test.ts` | Updated for simplified hint-reading functions |

### Manual Verification

1. Register nf-core workflow → auto-detects Table mode with correct columns
2. Register WDL workflow → auto-detects JSON mode
3. Submit table-mode run → verify samplesheet CSV generated correctly
4. Submit JSON-mode run → verify inputs.json written correctly
5. Switch modes mid-submission → data isolation between modes
6. Paste TSV data into table → rows populate correctly
7. Upload JSON file → editor content replaces

## Migration Path

1. Add `submission_hint` field (Alembic migration)
2. Backfill existing workflows with auto-generated hints (one-time script)
3. Build new frontend components alongside existing wizard
4. Update `POST /runs` to accept new unified schema (backward compatible)
5. Switch frontend to new editor
6. Deprecate `/runs/wizard` endpoint and old wizard components
7. Remove deprecated code after verification

## Design Mockups

Visual mockups are saved in `.superpowers/brainstorm/` session files:
- `editor-v2.html` — final design with Table and JSON modes

## Open Questions

None — all design decisions resolved during brainstorming session.

# Run Submission UX Redesign — Design Spec

**Date:** 2026-04-02
**Status:** Approved
**Mockup:** `.superpowers/brainstorm/69668-1775133724/content/full-wizard-mockup.html`

## Problem

BioinfoFlow's run submission has high friction:

1. **Batch Submit dialog** — workspace + raw JSON params per row is confusing. "Workspace" vs project workspace is unclear.
2. **Run Wizard** — three raw JSON textareas (Params, Inputs WDL, Config Overrides) that even the creator finds hard to fill. Guided mode is hardcoded for viral-mini only and unavailable for other workflows.
3. **No progressive disclosure** — new users and power users see the same intimidating interface.

The backend already extracts and persists rich parameter metadata (`workflow.schema_json` with name, type, optional, default, description) but the frontend never uses it for form generation.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Target user | Both wet-lab + bioinformaticians via progressive disclosure | "Easy to learn, hard to master" |
| Overall pattern | **A+B hybrid** — stepper wizard shell + schema-driven smart form | Guided feel for beginners, efficient for experts |
| Samplesheet input | **Inline table editor** (Excel-like) | Zero learning curve, supports auto-detect/CSV import/paste/template download |
| Parameter input | **Dynamic schema-driven forms** | Auto-adapts to any workflow, no more hardcoded guided modes |
| Single vs batch | **Unified experience** — same wizard, batch mode adds rows | One mental model |

## Architecture

### 3-Step Wizard Flow

```
Step 1: Choose Workflow    →    Step 2: Configure Params    →    Step 3: Review & Submit
(card grid + search)            (schema form + sample table)      (summary + confirm)
```

### Step 1 — Choose Workflow

- **Card grid layout** showing all registered workflows in the current project
- Each card shows: icon, name, description, engine badge (Nextflow/WDL), estimated time, param count
- Search/filter bar at top
- Clicking a card selects it (blue border + checkmark)
- "下一步 →" advances to Step 2

### Step 2 — Configure Parameters

Two sections, both inside the same scrollable page:

#### Section A: Sample Data (if workflow has samplesheet-type inputs)

**Inline table editor** with toolbar:
- **🔍 自动检测** — calls existing `/files/scan` endpoint to find FASTQ/BAM files in workspace
- **📂 导入 CSV/TSV** — file upload that parses and populates the table
- **📋 粘贴** — paste from clipboard (Excel copy → paste)
- **📥 下载模板** — downloads a blank CSV with correct column headers from schema
- **Table columns** generated from schema (e.g., `sample_id`, `fastq_1`, `fastq_2` for paired-end)
- Row add/remove, row count indicator (N / 500)
- File path cells use existing `PathSuggestInput` for autocomplete

#### Section B: Run Parameters (schema-driven)

**Type → Widget mapping:**

| Schema Type | Widget | Example |
|-------------|--------|---------|
| `String` | Text input | genome name, output directory |
| `String` with `enum` | Select dropdown | aligner choice (bwa-mem2, minimap2) |
| `Int` / `Integer` | Number input with optional unit label | min read length (bp), thread count |
| `Float` / `Number` | Number input + range slider | variant calling threshold |
| `Boolean` | Toggle switch with label + description | skip trimming |
| `File` | File picker (select or PathSuggestInput) with suffix filter | reference genome (.fasta) |
| `Array[File]` | Multi-file drop zone | multiple BAM files |

**Builtin references** are presented as a select dropdown with curated options + "选择自定义文件..." fallback.

**Default values** from schema pre-populate all fields. Required fields show red asterisk.

#### Section C: Advanced Options (collapsed by default)

Expandable accordion containing:
- Timeout (seconds)
- Priority (normal/high/urgent/low)
- Retry policy toggle + config (max_retries, delay, backoff, retry_on)
- **JSON override textarea** for power users (Nextflow config overrides / WDL inputs)
- This is where the current raw JSON mode lives — still accessible but hidden from beginners

### Step 3 — Review & Submit

- Read-only summary of all configured values
- Organized by sections: Workflow info, Samples (chips), Parameters (key-value pairs), Run config
- "← 修改参数" goes back to Step 2
- "▶ 开始运行" submits

### Batch Mode Integration

The same wizard supports batch by extending Step 2:
- A "＋ 添加到批量" button in the wizard footer creates a batch queue (stored in local state as an array of run configs)
- Each batch item shares the workflow (selected in Step 1) but can have different workspace, samples, and params
- When batch mode is active, a banner shows "批量模式 · N 个运行" with the ability to switch between runs
- Step 3 in batch mode shows a table of all queued runs with status chips, instead of a single summary
- Submits via existing `POST /runs/batch` endpoint with the same payload format (array of `{workspace, params, inputs, config_overrides}`)
- Batch mode is entered from either: (a) the wizard footer button, or (b) opening the wizard from the Runs page "批量提交" action

## Schema-Driven Form Generation

### Data Source

The workflow's `schema_json` column (already persisted in DB) provides:
```json
{
  "inputs": [
    {
      "name": "reference",
      "type": "File",
      "optional": false,
      "default": null,
      "description": "Reference genome in FASTA format"
    }
  ]
}
```

For nf-core workflows, the full `nextflow_schema.json` provides additional metadata: `enum`, `minimum`/`maximum`, `help_text`, `hidden`, section grouping (`definitions`).

### Frontend Type Resolver

A `resolveWidget(param: WorkflowParameter)` function maps schema types to React components:

```
"String" + enum    → SelectField
"String"           → TextInput
"Integer" / "Int"  → NumberInput
"Float" / "Number" → NumberInput + RangeSlider
"Boolean"          → ToggleSwitch
"File"             → FilePickerInput (with suffix filter from description/name heuristics)
"Array[File]"      → MultiFilePicker
"File" (csv/tsv)   → SamplesheetTable (inline table editor)
unknown            → TextInput (fallback)
```

### Samplesheet Detection Heuristic

A parameter is treated as a samplesheet if:
- Name contains `samplesheet`, `samples`, `input_csv`, or `manifest`
- OR type is `File` and description mentions `csv`, `tsv`, `samplesheet`

When detected, the inline table editor replaces the file picker. Column headers come from:
1. nf-core schema's `properties` within the samplesheet definition (if available)
2. Existing `/files/scan` auto-detection (column structure inferred from detected files)
3. Fallback: generic `sample_id`, `file_1`, `file_2` columns

## Component Hierarchy

```
RunSubmissionWizard (new, replaces RunWizardDialog)
├── StepIndicator (1→2→3 progress)
├── Step1WorkflowSelect
│   ├── SearchBar
│   └── WorkflowCardGrid
│       └── WorkflowCard[]
├── Step2ConfigureParams
│   ├── WorkflowInfoBar
│   ├── SamplesheetEditor (conditional, if samplesheet param detected)
│   │   ├── SamplesheetToolbar (auto-detect, import, paste, download template)
│   │   └── EditableTable (dynamic columns from schema)
│   ├── SchemaForm (dynamic from workflow.schema_json)
│   │   └── FormField[] (resolved by resolveWidget)
│   │       ├── TextInput
│   │       ├── NumberInput
│   │       ├── SelectField
│   │       ├── ToggleSwitch
│   │       ├── FilePickerInput
│   │       └── RangeSlider
│   └── AdvancedOptions (collapsible)
│       ├── TimeoutInput
│       ├── PrioritySelect
│       ├── RetryPolicyConfig
│       └── JsonOverrideEditor
├── Step3ReviewSubmit
│   ├── SummarySection (workflow info)
│   ├── SummarySection (samples chips)
│   ├── SummarySection (params key-value)
│   └── SummarySection (run config)
└── WizardFooter (back/next/submit buttons)
```

## Files to Create/Modify

### New Files (frontend)

| File | Purpose |
|------|---------|
| `frontend/app/(app)/workflows/components/run-submission-wizard.tsx` | Main wizard container with step navigation |
| `frontend/app/(app)/workflows/components/wizard/step-indicator.tsx` | Progress indicator (1→2→3) |
| `frontend/app/(app)/workflows/components/wizard/step-workflow-select.tsx` | Step 1: workflow card grid |
| `frontend/app/(app)/workflows/components/wizard/step-configure-params.tsx` | Step 2: params + samples |
| `frontend/app/(app)/workflows/components/wizard/step-review-submit.tsx` | Step 3: summary + confirm |
| `frontend/app/(app)/workflows/components/wizard/schema-form.tsx` | Schema-driven dynamic form generator |
| `frontend/app/(app)/workflows/components/wizard/form-fields/index.ts` | Re-exports all field components |
| `frontend/app/(app)/workflows/components/wizard/form-fields/text-input.tsx` | String param widget |
| `frontend/app/(app)/workflows/components/wizard/form-fields/number-input.tsx` | Int/Float widget |
| `frontend/app/(app)/workflows/components/wizard/form-fields/select-field.tsx` | Enum widget |
| `frontend/app/(app)/workflows/components/wizard/form-fields/toggle-switch.tsx` | Boolean widget |
| `frontend/app/(app)/workflows/components/wizard/form-fields/file-picker.tsx` | File param widget |
| `frontend/app/(app)/workflows/components/wizard/form-fields/range-slider.tsx` | Float range widget |
| `frontend/app/(app)/workflows/components/wizard/samplesheet-editor.tsx` | Inline table editor |
| `frontend/app/(app)/workflows/components/wizard/samplesheet-toolbar.tsx` | Auto-detect/import/paste/template toolbar |
| `frontend/lib/schema-resolver.ts` | Type → Widget mapping logic |

### Modified Files

| File | Change |
|------|--------|
| `frontend/app/(app)/workflows/page.tsx` | Replace `RunWizardDialog` with `RunSubmissionWizard` |
| `frontend/app/(app)/runs/page.tsx` | Replace `BatchSubmitDialog` with unified wizard (batch mode) |
| `frontend/lib/types.ts` | Add `SchemaFormField`, `SamplesheetColumn` types |
| `frontend/lib/api.ts` | Add `getWorkflowSchema()` helper if needed |

### Files to Deprecate (later, not in initial PR)

| File | Reason |
|------|--------|
| `frontend/app/(app)/workflows/components/run-wizard-dialog.tsx` | Replaced by new wizard |
| `frontend/app/(app)/runs/components/batch-submit-dialog.tsx` | Replaced by unified wizard |

### Backend (minimal changes)

| File | Change |
|------|--------|
| `backend/app/api/v1/workflows.py` | Add `GET /workflows/{id}/schema` endpoint (returns `schema_json` directly) if not already exposed in `WorkflowRead` |

## Reuse Existing Code

- **`PathSuggestInput`** (`frontend/components/bioinfoflow/path-suggest-input.tsx`) — reuse in file picker fields and samplesheet cells
- **`RunAdvancedOptions`** (`frontend/app/(app)/workflows/components/run-advanced-options.tsx`) — reuse or refactor into the Advanced Options accordion
- **`/files/scan` endpoint** — reuse for auto-detect in samplesheet toolbar
- **`/runs`, `/runs/batch` API endpoints** — no changes needed, submit the same payloads
- **`WorkflowParametersTab`** (`frontend/app/(app)/workflows/[id]/components/workflow-parameters-tab.tsx`) — reference for schema field rendering patterns
- **Shadcn UI components** — Dialog, Tabs, Input, Select, Switch, Popover, Command all reused
- **i18n namespace `workflows`** — extend with new translation keys

## Verification Plan

1. **Unit tests**: Each form field widget renders correctly for its type, handles defaults, validates required
2. **Integration tests**: Full wizard flow (select workflow → fill params → review → submit) with mocked API
3. **Schema coverage**: Test with at least 3 different workflow schemas (Nextflow with nf-core schema, Nextflow with minimal params, WDL)
4. **Samplesheet**: Test auto-detect, CSV import, paste, manual entry, row add/remove
5. **Batch mode**: Test adding multiple runs and batch submission
6. **Visual regression**: Compare mockup HTML with implemented UI in browser
7. **Existing tests**: All current tests in `tests/integration/components/run-wizard-dialog-*.test.tsx` should be migrated to new wizard
8. **End-to-end**: Open browser → navigate to workflows → click Run → complete all 3 steps → verify run appears in runs list

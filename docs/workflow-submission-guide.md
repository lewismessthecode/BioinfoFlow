# Workflow Submission Guide

This guide describes the current submission contract after the run-envelope refactor.

## Source Of Truth

There are now two authoritative APIs for run setup:

1. `GET /workflows/{workflow_id}/form-spec`
2. `POST /runs`

The frontend wizard, batch submit, and agent `submit_run` should all converge on this model.

## End-To-End Flow

Typical happy path:

1. Resolve the active user and workspace via `get_current_user`
2. Get or create the default project with `GET /projects/default`, or choose an existing project from `GET /projects`
3. Register or validate a workflow:
   - `POST /workflows/validate` for preflight parsing
   - `POST /workflows` to persist remote refs or inline single-file local workflows
   - `POST /workflows/local-bundle` to persist a local workflow bundle chosen from a native directory picker
4. Bind the workflow to the project:
   - `POST /projects/{project_id}/workflows/{workflow_id}:bind`
5. Load the deterministic form spec:
   - `GET /workflows/{workflow_id}/form-spec`
6. If a file field is marked `materialize_to_run`, upload the runtime document first:
   - `POST /runs/uploads`
7. Submit a run:
   - `POST /runs`
8. Track execution:
   - `GET /runs/{run_id}`
   - `GET /runs/{run_id}/logs`
   - `GET /runs/{run_id}/dag`
   - `GET /events/stream`
9. Fetch outputs:
   - `GET /runs/{run_id}/outputs`
   - `GET /runs/{run_id}/outputs/download`

## Canonical Create Contract

`POST /runs` accepts only the canonical envelope:

```json
{
  "project_id": "uuid",
  "workflow_id": "uuid",
  "values": {
    "sample_id": "S1",
    "reads": "asset://project/reads/S1.fastq.gz"
  },
  "options": {
    "profile": "docker",
    "max_retries": 1,
    "timeout_seconds": 3600
  }
}
```

Rules:

- `values` must be a JSON object keyed by form field id
- field ids come from `GET /workflows/{workflow_id}/form-spec`
- `options` currently supports:
  - `profile`
  - `max_retries`
  - `timeout_seconds`
  - `resume_from_run_id`
- unknown top-level keys are rejected

Removed legacy create shapes:

- `params`
- `inputs`
- `config_overrides`
- `workspace`
- `submission_mode`
- `json_inputs`
- `table_rows`
- `/runs/wizard`

## Form Spec Contract

`GET /workflows/{workflow_id}/form-spec` returns the server-side description used by both the frontend and agents.

Important field properties:

- `id`: submission key used in `values`
- `kind`: one of `file`, `file_list`, `directory`, `table`, `string`, `int`, `float`, `bool`, `select`
- `section`: UI grouping only (`data`, `params`, `advanced`)
- `required`: user-facing requirement
- `platform_managed`: cannot be submitted by the client
- `allow_roots`: storage roots allowed for manual file paths
- `materialize_to_run`: top-level file/document input that should be uploaded or chosen per run, then snapshotted into that run's input area
- `columns`: schema for `table` rows
- `options`: allowed values for `select`

The frontend should render from `form-spec` directly, not infer business meaning from workflow engine params.

## Local Workflow Registration

There are now two supported local registration paths:

- Single-file quick import:
  - choose one `.nf` or `.wdl` file
  - frontend validates with `POST /workflows/validate`
  - frontend persists with `POST /workflows`
- Bundle import:
  - choose a workflow directory from the native file picker
  - choose the entrypoint file from the discovered `.nf` / `.wdl` files in that bundle
  - frontend persists with `POST /workflows/local-bundle` as multipart form data

`POST /workflows/local-bundle` expects:

- metadata fields such as `name`, `version`, `engine`, `description`
- `entrypoint_relpath`
- `bundle_paths`: JSON array of bundle-relative file paths
- repeated `bundle_files` uploads in the same order as `bundle_paths`

For local workflow bundles, the bundle may also declare explicit field overrides in:

- `inputs/form-spec.overrides.json`

That file is merged into the derived `form-spec` during workflow registration and form-spec reads. Use it when a bundle needs to declare concrete UI/input policy such as `allow_roots`, instead of relying on name-based inference.

Common local-bundle overrides now include:

- `allow_roots` for storage-backed browsing
- `materialize_to_run: true` for manifest-style runtime documents that should not inherit bundle fixture defaults

## Path And Asset Resolution

For path-like fields, the preferred representation is an asset URI returned by the storage APIs:

- `asset://project/...`
- `asset://deliveries/...`
- `asset://reference/...`
- `asset://run_upload/...`

The run compiler resolves those URIs to absolute runtime paths.

Manual relative/absolute paths are allowed only when they stay inside the field's allowed roots:

- `project_data`
- `shared_data` (mapped to Deliveries)
- `reference`
- `any_allowed_root`

Invalid or out-of-scope paths fail validation before the run is queued.

The frontend file browser must honor the same `allow_roots` contract. It should only show storage sources that map to the field's allowed roots; it should not expose extra tabs and rely on the backend to reject them later.

## Runtime Document Uploads

Some workflows need a per-run manifest or other small document rather than a large storage-backed asset. Those fields are exposed through `form-spec` as `materialize_to_run`.

Client flow:

1. upload the file with `POST /runs/uploads`
2. store the returned `asset://run_upload/...` URI in `values[field_id]`
3. submit `POST /runs`

At compile time the backend copies that uploaded document into the run snapshot area:

- `runs/<run_id>/input/materialized/attachments/<field_id>/<filename>`

The engine receives the snapshotted run-local path, not the temporary upload staging path.

## Table Materialization

`table` fields submit structured JSON, not pre-rendered CSV strings:

```json
{
  "samplesheet": {
    "filename": "samplesheet.csv",
    "rows": [
      {
        "sample": "S1",
        "fastq_1": "asset://project/reads/S1_R1.fastq.gz",
        "fastq_2": "asset://project/reads/S1_R2.fastq.gz"
      }
    ]
  }
}
```

At compile time the backend:

- resolves any path cells
- writes the attachment under the run input area
- stores engine-ready references in `run.config`

Clients should not precompute legacy `params.input`, `samplesheet_path`, or raw CSV payloads anymore.

## Nextflow And WDL Translation

The client submits `values`; the server translates them into engine-specific config.

Nextflow:

- field ids usually map directly to `params.<field>`
- table fields are materialized to CSV and referenced from params
- runtime document uploads are snapshotted before launch, and Nextflow receives the run-local absolute path
- launch metadata is written to `audit/launch.sh`

WDL:

- values are mapped onto qualified workflow input keys
- resolved inputs are materialized to `inputs.json`
- platform-managed directory values such as `outdir` are injected server-side as the absolute public run results directory (`runs/<run_id>/results`)

This translation step lives in `RunCompiler`; frontend code should stay engine-agnostic.

## Validation Model

Canonical validation path:

1. project exists and is visible to the current user/workspace
2. workflow exists
3. workflow is bound to the project
4. submitted `values` satisfy the form spec
5. path-like values resolve to allowed storage roots

Agent note:

- Agents should inspect `workflow_schema` / `preview_run_profile` and submit the canonical `workflow_id + values + options` envelope.
- Do not introduce a separate validate-only payload shape alongside `POST /runs`.

## Batch Submission

`POST /runs/batch` uses the same per-run envelope shape:

```json
{
  "project_id": "uuid",
  "runs": [
    {
      "workflow_id": "uuid",
      "values": {
        "sample_id": "A"
      }
    },
    {
      "workflow_id": "uuid",
      "values": {
        "sample_id": "B"
      },
      "options": {
        "profile": "docker"
      }
    }
  ]
}
```

## Agent And UX Expectations

- The run workbench should stay thin: load form spec, collect `values`, submit canonical envelope.
- Agent workflow discovery may still involve richer tool flows, but actual validation and submission should align with the same run envelope.
- Approval policy belongs to the conversation / agent layer; run payload shape belongs to the run compiler layer.

## Debugging Checklist

If a run submit path behaves oddly, check these in order:

1. Is the workflow bound to the project?
2. Does `GET /workflows/{workflow_id}/form-spec` match what the client renders?
3. Is the client submitting `values`, not legacy `params/inputs`?
4. Are file values valid `asset://...` URIs or allowed manual paths?
5. Does `RunCompiler.validate(...)` accept the payload?
6. Does the created run contain the expected compiled config and launch audit files?

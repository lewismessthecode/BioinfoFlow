# Storage Abstraction V2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Bioinfoflow's path-centric project and run submission model with a storage-centric asset reference model so users never need to understand host paths, container paths, mount mappings, or relative-path bases.

**Architecture:** The implementation introduces a storage registry and canonical asset URIs (`asset://...`) as the only public way to represent file-like workflow inputs. Projects become managed storage roots by default, shared data and references become platform-configured sources, and run submission switches from path strings to typed input values that the backend resolves server-side at compile time. The rollout is staged so backend storage primitives land first, then project/storage APIs, then run submission and frontend UX, then legacy path cleanup.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Next.js 16, React 19, Vitest, pytest, Alembic, Docker Compose.

## Final target state

- Users create projects without manually setting `workspace_path`.
- Users choose files from `Project Data`, `Shared Data`, `Reference Library`, or `Upload`.
- Frontend stores file-like values as `asset://<source_id>/<relative_path>` references, not raw path strings.
- Backend resolves asset refs to container-visible absolute paths during run compilation only.
- `outdir` is system-managed and no longer user-editable.
- Output fields are rendered as produced artifacts, never as required inputs.
- Compose deployments mount host storage only to canonical internal roots under `/data`.

## Task 1: Introduce storage registry, asset refs, and source resolution

**Files:**
- Create: `backend/app/schemas/storage.py`
- Create: `backend/app/services/storage_service.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/utils/paths.py`
- Test: `backend/tests/test_services/test_storage_service.py`
- Test: `backend/tests/test_api/test_storage_api.py`

**Step 1: Write failing backend tests for source registration and asset URI parsing**

- Add tests for:
  - loading configured sources from settings
  - parsing `asset://project/foo/bar.fastq.gz`
  - parsing `asset://shared-seq/run42/sample.bam`
  - rejecting malformed URIs and path traversal
  - resolving a source-relative file to an absolute container path without leaking it publicly

**Step 2: Run the new backend tests to verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_services/test_storage_service.py tests/test_api/test_storage_api.py -v
```

Expected: failures because storage schemas/services/routes do not exist yet.

**Step 3: Implement the storage core**

- Add a `StorageSourceRead` schema with `id`, `label`, `kind`, `read_only`, `upload_allowed`, and `scan_allowed`.
- Add an `AssetRef` schema with `kind="asset_ref"` and `uri`.
- Add settings for canonical storage roots and platform sources, for example:
  - `managed_projects_root=/data/projects`
  - `storage_sources=[...]`
- Implement a storage service that:
  - lists configured sources
  - resolves `asset://...` to canonical absolute paths
  - validates source-relative traversal boundaries
  - distinguishes public metadata from private resolved paths

**Step 4: Add the storage browsing API surface**

- Add `backend/app/api/v1/storage.py` with:
  - `GET /storage/sources`
  - `GET /storage/browse`
  - `GET /storage/read`
  - `POST /storage/upload`
  - `POST /storage/scan`
- Keep responses source-relative plus `asset://...`; never return host or container absolute paths.

**Step 5: Run backend tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_services/test_storage_service.py tests/test_api/test_storage_api.py -v
```

Expected: PASS.

Commit:

```bash
git add backend/app/config.py backend/app/utils/paths.py backend/app/schemas/storage.py backend/app/services/storage_service.py backend/app/api/v1/storage.py backend/tests/test_services/test_storage_service.py backend/tests/test_api/test_storage_api.py
git commit -m "feat: add storage registry and asset refs"
```

## Task 2: Refactor project storage ownership to managed project roots

**Files:**
- Modify: `backend/app/models/project.py`
- Modify: `backend/app/schemas/project.py`
- Modify: `backend/app/services/project_service.py`
- Modify: `backend/app/api/v1/projects.py`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/hooks/use-sidebar-data.ts`
- Modify: `frontend/components/bioinfoflow/create-project-dialog.tsx`
- Test: `backend/tests/test_services/test_project_service.py`
- Test: `backend/tests/test_api/test_projects.py`
- Test: `frontend/tests/unit/hooks/use-sidebar-data.test.tsx`

**Step 1: Write failing tests for the new project contract**

- Add tests that:
  - creating a project without `workspace_path` provisions a managed root automatically
  - normal project reads return `storage_mode` and read-only `project_root`
  - `data_roots` is no longer part of normal project responses
  - the create-project dialog no longer requires a workspace field in the common flow

**Step 2: Run project tests to verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_services/test_project_service.py tests/test_api/test_projects.py -v
cd frontend && bun run test frontend/tests/unit/hooks/use-sidebar-data.test.tsx
```

Expected: failures because the API and frontend still use `workspace_path`.

**Step 3: Implement managed project storage**

- Replace the public project contract with:
  - `storage_mode`
  - `project_root` (read-only)
  - optional admin-only `storage_override_path`
- Auto-provision managed projects under `/data/projects/<project-id>` or the configured managed root.
- Remove `workspace_path` and `data_roots` from the default project create/update UX.
- Keep one advanced admin-only override path flow, but do not expose it in the normal dialog.

**Step 4: Update frontend project creation**

- Remove the required workspace-path field from the default create flow.
- Show an informational preview like “Storage managed by Bioinfoflow”.
- Ensure sidebar data creation no longer POSTs `workspace_path` in the normal path.

**Step 5: Run tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_services/test_project_service.py tests/test_api/test_projects.py -v
cd frontend && bun run test frontend/tests/unit/hooks/use-sidebar-data.test.tsx
```

Expected: PASS.

Commit:

```bash
git add backend/app/models/project.py backend/app/schemas/project.py backend/app/services/project_service.py backend/app/api/v1/projects.py frontend/lib/types.ts frontend/hooks/use-sidebar-data.ts frontend/components/bioinfoflow/create-project-dialog.tsx backend/tests/test_services/test_project_service.py backend/tests/test_api/test_projects.py frontend/tests/unit/hooks/use-sidebar-data.test.tsx
git commit -m "feat: make project storage managed by default"
```

## Task 3: Add workflow input metadata for typed storage-aware forms

**Files:**
- Modify: `backend/app/services/validators/types.py`
- Modify: `backend/app/services/validators/wdl_validator.py`
- Modify: `backend/app/engine/adapters/wdl.py`
- Modify: `backend/app/engine/schema_extractor.py`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/app/(app)/workflows/[id]/components/workflow-parameters-tab.tsx`
- Test: `backend/tests/test_services/test_workflow_validator.py`
- Test: `backend/tests/test_api/test_submission_hint.py`
- Test: `frontend/tests/integration/pages/workflow-detail-page.test.tsx`

**Step 1: Write failing tests for enriched parameter metadata**

- Add tests that assert:
  - WDL `File sequence_list` becomes `value_kind="file"`
  - WDL `String outdir` becomes `is_internal=true`
  - Nextflow samplesheet/file-like params get `value_kind` and `source_hint`
  - workflow detail pages hide internal inputs from the “fill this in” mindset
  - outputs are described as artifacts, not required inputs

**Step 2: Run metadata tests to verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_services/test_workflow_validator.py tests/test_api/test_submission_hint.py -v
cd frontend && bun run test frontend/tests/integration/pages/workflow-detail-page.test.tsx
```

Expected: failures because current schema has only `name/type/optional/default/description`.

**Step 3: Implement schema enrichment**

- Extend `WorkflowParameter` with:
  - `value_kind`
  - `source_hint`
  - `is_internal`
- Update WDL and fallback extraction to mark `outdir` as internal.
- Update submission hint generation to skip internal inputs rather than using only `reserved_keys`.

**Step 4: Update workflow detail rendering**

- Replace “Required” output badges with artifact-oriented wording.
- Mark internal inputs as platform-managed and do not surface them in run form generation.

**Step 5: Run tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_services/test_workflow_validator.py tests/test_api/test_submission_hint.py -v
cd frontend && bun run test frontend/tests/integration/pages/workflow-detail-page.test.tsx
```

Expected: PASS.

Commit:

```bash
git add backend/app/services/validators/types.py backend/app/services/validators/wdl_validator.py backend/app/engine/adapters/wdl.py backend/app/engine/schema_extractor.py frontend/lib/types.ts frontend/app/'(app)'/workflows/[id]/components/workflow-parameters-tab.tsx backend/tests/test_services/test_workflow_validator.py backend/tests/test_api/test_submission_hint.py frontend/tests/integration/pages/workflow-detail-page.test.tsx
git commit -m "feat: add storage-aware workflow parameter metadata"
```

## Task 4: Replace path-string file APIs in the frontend with storage browsing

**Files:**
- Modify: `frontend/lib/types.ts`
- Create: `frontend/components/bioinfoflow/storage-browser-dialog.tsx`
- Modify: `frontend/components/bioinfoflow/path-suggest-input.tsx`
- Modify: `frontend/components/bioinfoflow/file-browser-dialog.tsx`
- Modify: `frontend/app/(app)/workflows/components/samplesheet-editor.tsx`
- Modify: `frontend/app/(app)/workflows/page.tsx`
- Test: `frontend/tests/integration/components/run-submission-wizard.test.tsx`
- Test: `frontend/tests/unit/lib/schema-resolver.test.ts`

**Step 1: Write failing frontend tests for source-based browsing**

- Add tests that:
  - file pickers show logical source tabs (`Project Data`, `Shared Data`, `Reference Library`, `Upload`)
  - choosing a file stores an `asset://...` reference
  - data sources no longer inject absolute paths into form state

**Step 2: Run the targeted frontend tests to verify they fail**

Run:

```bash
cd frontend && bun run test frontend/tests/integration/components/run-submission-wizard.test.tsx frontend/tests/unit/lib/schema-resolver.test.ts
```

Expected: failures because current pickers are still path-string based.

**Step 3: Implement storage-aware browser components**

- Create a storage browser dialog backed by `/storage/sources` and `/storage/browse`.
- Convert existing path suggestion/browser flows to operate on `source_id + relative_path`.
- Limit uploads to the project source and scans to project/shared sources.

**Step 4: Remove raw path leakage from the form layer**

- Stop returning absolute shared-root paths into the JSON editor and samplesheet cells.
- Ensure form state only stores typed scalar values and asset refs.

**Step 5: Run tests and commit**

Run:

```bash
cd frontend && bun run test frontend/tests/integration/components/run-submission-wizard.test.tsx frontend/tests/unit/lib/schema-resolver.test.ts
```

Expected: PASS.

Commit:

```bash
git add frontend/lib/types.ts frontend/components/bioinfoflow/storage-browser-dialog.tsx frontend/components/bioinfoflow/path-suggest-input.tsx frontend/components/bioinfoflow/file-browser-dialog.tsx frontend/app/'(app)'/workflows/components/samplesheet-editor.tsx frontend/app/'(app)'/workflows/page.tsx frontend/tests/integration/components/run-submission-wizard.test.tsx frontend/tests/unit/lib/schema-resolver.test.ts
git commit -m "feat: switch frontend file picking to storage sources"
```

## Task 5: Replace run submission V1 path payloads with V2 typed input values

**Files:**
- Modify: `backend/app/schemas/run.py`
- Modify: `backend/app/api/v1/runs.py`
- Modify: `backend/app/services/run_submission_service.py`
- Modify: `backend/app/services/run_helpers.py`
- Modify: `backend/app/services/run_lifecycle_service.py`
- Modify: `backend/app/models/run.py`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/app/(app)/workflows/components/run-submission-workbench.tsx`
- Modify: `frontend/app/(app)/workflows/components/run-shared-settings.tsx`
- Test: `backend/tests/test_api/test_run_wizard.py`
- Test: `backend/tests/test_api/test_unified_run_create.py`
- Test: `backend/tests/test_services/test_run_service.py`

**Step 1: Write failing tests for the V2 run contract**

- Add tests that assert:
  - `POST /runs` accepts `input_values` instead of `workspace + submission.json`
  - file-like values use `asset://...`
  - generated samplesheets are snapshotted and rewritten to internal project asset refs
  - `outdir` is omitted from the public request and always becomes `runs/<run_id>/results`
  - WDL `sequence_list` resolves from an asset ref

**Step 2: Run backend run-submission tests to verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_api/test_run_wizard.py tests/test_api/test_unified_run_create.py tests/test_services/test_run_service.py -v
```

Expected: failures because the current payload shape is path-oriented.

**Step 3: Implement the V2 run compiler**

- Add typed input models:
  - scalar JSON values
  - `AssetRef`
  - `TableInput`
- Build a compilation step that:
  - resolves asset refs to absolute runtime paths
  - snapshots generated table inputs into the run archive
  - rewrites workflow params/inputs to engine-ready values
  - auto-sets `outdir`
- Remove user-editable `workspace` and `outdir` from the primary frontend workbench.

**Step 4: Update run submission frontend**

- Render file-like fields as picker controls, not raw JSON path fields.
- Keep a limited advanced JSON fallback only for unknown non-file shapes.
- Preserve profile/retry/timeout as advanced execution settings.

**Step 5: Run tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_api/test_run_wizard.py tests/test_api/test_unified_run_create.py tests/test_services/test_run_service.py -v
cd frontend && bun run test frontend/tests/integration/components/run-submission-wizard.test.tsx
```

Expected: PASS.

Commit:

```bash
git add backend/app/schemas/run.py backend/app/api/v1/runs.py backend/app/services/run_submission_service.py backend/app/services/run_helpers.py backend/app/services/run_lifecycle_service.py backend/app/models/run.py frontend/lib/types.ts frontend/app/'(app)'/workflows/components/run-submission-workbench.tsx frontend/app/'(app)'/workflows/components/run-shared-settings.tsx backend/tests/test_api/test_run_wizard.py backend/tests/test_api/test_unified_run_create.py backend/tests/test_services/test_run_service.py frontend/tests/integration/components/run-submission-wizard.test.tsx
git commit -m "feat: adopt typed storage-aware run submission"
```

## Task 6: Wire Docker Compose and admin configuration to canonical storage roots

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Modify: `backend/scripts/docker-entrypoint.sh`
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `docs/operations/runbook.md`
- Test: `backend/tests/test_api/test_system.py`

**Step 1: Write failing checks for storage-source health reporting**

- Add tests that:
  - system status exposes configured storage sources and their availability
  - startup validation fails clearly when a configured source is missing

**Step 2: Run the health tests to verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_api/test_system.py -v
```

Expected: failures because storage-source health is not reported yet.

**Step 3: Update deployment defaults**

- Change compose examples and docs to mount host storage only to canonical internal roots:
  - `/data/projects`
  - `/data/sources/<source-id>`
- Update the backend entrypoint to create canonical directories.
- Document the admin-only step of registering shared/reference sources by logical name.

**Step 4: Add system health visibility**

- Expose storage-source status in system health/status responses so mount mistakes surface before run submission.

**Step 5: Run tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_api/test_system.py -v
```

Expected: PASS.

Commit:

```bash
git add docker-compose.yml docker-compose.prod.yml backend/scripts/docker-entrypoint.sh README.md backend/README.md docs/operations/runbook.md backend/tests/test_api/test_system.py
git commit -m "docs: align compose deployment with storage abstraction v2"
```

## Task 7: Remove legacy path-first behavior and close out regressions

**Files:**
- Modify: `backend/app/api/v1/files.py`
- Modify: `backend/app/services/file_service.py`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Modify: `frontend/components/bioinfoflow/file-browser-dialog.tsx`
- Modify: `frontend/components/bioinfoflow/path-suggest-input.tsx`
- Test: `backend/tests/test_services/test_file_service.py`
- Test: `frontend/tests/integration/pages/workflow-detail-page.test.tsx`
- Test: `frontend/tests/integration/components/run-submission-wizard.test.tsx`

**Step 1: Write failing regression tests for legacy path removal**

- Add tests that assert:
  - old file APIs are either removed or clearly scoped to internal-only project writes
  - user-facing copy no longer mentions “relative to backend root” or asks users to understand workspace path math
  - output tables no longer display “Required” for workflow outputs

**Step 2: Run the regression tests to verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_services/test_file_service.py -v
cd frontend && bun run test frontend/tests/integration/pages/workflow-detail-page.test.tsx frontend/tests/integration/components/run-submission-wizard.test.tsx
```

Expected: failures because old terminology and code paths still exist.

**Step 3: Remove or quarantine legacy behavior**

- Delete or internally quarantine `/files` usage from end-user flows.
- Remove legacy path-copy from i18n strings.
- Ensure any remaining path-based helpers are private implementation details only.

**Step 4: Run full verification**

Run:

```bash
cd backend && uv run pytest
cd frontend && bun run test
cd frontend && bun run lint
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/api/v1/files.py backend/app/services/file_service.py frontend/messages/en.json frontend/messages/zh-CN.json frontend/components/bioinfoflow/file-browser-dialog.tsx frontend/components/bioinfoflow/path-suggest-input.tsx backend/tests/test_services/test_file_service.py frontend/tests/integration/pages/workflow-detail-page.test.tsx frontend/tests/integration/components/run-submission-wizard.test.tsx
git commit -m "refactor: remove legacy path-first UX"
```

## Acceptance checklist

- A user can create a project without choosing a filesystem path.
- A user can submit Deaf_20 by selecting `sequence_list` from Project Data, Shared Data, Reference Library, or Upload without seeing any host/container paths.
- A user can submit personal FASTQ/BAM/VCF files either by uploading to project storage or by selecting from a configured shared source.
- The backend stores logical asset refs publicly and resolves absolute runtime paths privately.
- Compose admins configure mounts once; end users never need mount knowledge.
- The workflow detail page distinguishes internal inputs, user inputs, and outputs correctly.

## Notes for implementation

- Because the user explicitly allowed reset/rebuild, do not spend time on backward-compatible migration of live project data. Add the schema migration needed for the new tables/columns, update tests/seed data, and optimize for the clean V2 contract.
- Keep commits per task small and reviewable; do not batch Tasks 1-7 into one rollout.
- Before claiming completion on each task, use `superpowers:verification-before-completion`.

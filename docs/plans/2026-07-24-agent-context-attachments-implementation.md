# Agent Context Attachments And Mentions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure file/folder uploads, clipboard-image multimodal input, scalable structured `@` references, previews, and bounded context assembly to the Agent workbench.

**Architecture:** Persist uploads as session-owned `AgentAttachment` records and private files, keep the transcript canonical with typed references, and resolve image bytes only while assembling a model invocation. Use a CodeMirror-backed structured composer for accessible inline mention ranges, while a dedicated context-picker service performs quota-balanced file/workflow/run search without loading all runs into the browser.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, Pillow, pypdf, LiteLLM codecs, Next.js 16, React 19, CodeMirror 6, Radix primitives, Vitest, pytest.

---

## File Structure

### Backend additions

- `backend/app/models/agent_core.py`: persist attachment ownership and metadata.
- `backend/app/repositories/agent_core_repo.py`: attachment queries and cleanup.
- `backend/alembic/versions/0054_agent_attachments.py`: schema migration.
- `backend/app/path_layout.py`: session attachment roots and safe joins.
- `backend/app/schemas/agent_core.py`: typed input parts, attachment responses, and context-search responses.
- `backend/app/services/agent_core/attachments.py`: streaming ingestion, type detection, image processing, PDF/text extraction, folder manifests, cleanup, preview resolution.
- `backend/app/services/agent_core/input_resolver.py`: validate structured references and create canonical transcript parts.
- `backend/app/services/agent_core/context_picker.py`: balanced file/folder/workflow/run search.
- `backend/app/services/agent_core/tools/attachments/`: target-neutral attachment search/read tools.
- `backend/app/services/model_runtime/contracts.py`: canonical `ImagePart`.
- `backend/app/services/model_runtime/codecs/chat_completions.py`: Chat multimodal encoding.
- `backend/app/services/model_runtime/codecs/responses.py`: Responses multimodal encoding.
- `backend/app/services/agent_core/transcript/messages.py`: preserve image references and asynchronously resolve them for model input.
- `backend/app/services/agent_core/context/assembler.py`: attachment-aware context assembly.
- `backend/app/api/v1/agent.py`: upload, preview, delete, and context-search routes.
- `backend/app/config.py`: explicit attachment limits.
- `backend/pyproject.toml` and `backend/uv.lock`: Pillow and pypdf.

### Frontend additions

- `frontend/lib/agent-runtime/types.ts`: typed attachments, references, search results, and composer mentions.
- `frontend/lib/agent-runtime/client.ts`: attachment and context-search API calls.
- `frontend/lib/agent-runtime/composer-document.ts`: pure document/mention conversion helpers.
- `frontend/components/bioinfoflow/agent-runtime/structured-composer-editor.tsx`: CodeMirror editor and atomic inline mentions.
- `frontend/components/bioinfoflow/agent-runtime/context-picker-menu.tsx`: balanced async result menu.
- `frontend/components/bioinfoflow/agent-runtime/attachment-strip.tsx`: upload states and thumbnails.
- `frontend/components/bioinfoflow/agent-runtime/attachment-preview-dialog.tsx`: image preview, close, and pending deletion.
- `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`: integrate editor, secondary file/folder chooser, paste, and vision barrier.
- `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`: draft session creation, upload state, submission snapshots, and retry restoration.
- `frontend/hooks/use-agent-runtime.ts`: expose session creation for pre-turn uploads and allow attachment-only turns.
- `frontend/hooks/use-llm-settings.ts`: expose `supports_vision` on selectable models.
- `frontend/messages/en.json` and `frontend/messages/zh-CN.json`: all user-visible states.

---

### Task 1: Add canonical model image input

**Files:**
- Modify: `backend/app/services/model_runtime/contracts.py`
- Modify: `backend/app/services/model_runtime/__init__.py`
- Modify: `backend/app/services/model_runtime/codecs/chat_completions.py`
- Modify: `backend/app/services/model_runtime/codecs/responses.py`
- Test: `backend/tests/test_model_runtime/test_chat_completions_codec.py`
- Test: `backend/tests/test_model_runtime/test_responses_codec.py`
- Test: `backend/tests/test_model_runtime/test_contracts.py`

- [ ] **Step 1: Write failing contract and codec tests**

Add tests that construct:

```python
ImagePart(
    mime_type="image/png",
    data="cG5nLWJ5dGVz",
    sha256="a" * 64,
    detail="high",
)
```

Assert Chat encodes adjacent user text and image into one user message:

```python
assert request["messages"][1] == {
    "role": "user",
    "content": [
        {"type": "text", "text": "Inspect this screenshot."},
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,cG5nLWJ5dGVz",
                "detail": "high",
            },
        },
    ],
}
```

Assert Responses encodes the same pair as `input_text` plus `input_image`, and
assert canonical digests use `sha256` rather than embedding `data`.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
rtk uv run pytest tests/test_model_runtime/test_contracts.py tests/test_model_runtime/test_chat_completions_codec.py tests/test_model_runtime/test_responses_codec.py -q
```

Expected: failures because `ImagePart` and image encoding do not exist.

- [ ] **Step 3: Implement the minimal canonical type and encoders**

Add:

```python
ImageDetail = Literal["auto", "low", "high", "original"]

@dataclass(frozen=True)
class ImagePart:
    mime_type: str
    data: str
    sha256: str
    detail: ImageDetail | None = None
```

Extend `InputPart`, `_canonical_input_payload`, exports, and both codecs. Group
consecutive phase-less `TextPart` and `ImagePart` values into one user message.
Assistant text and tool grouping must remain unchanged.

- [ ] **Step 4: Run focused and existing codec tests GREEN**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/model_runtime backend/tests/test_model_runtime
rtk git commit -m "feat: add multimodal model input parts"
```

### Task 2: Persist session-owned attachments

**Files:**
- Modify: `backend/app/models/agent_core.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/repositories/agent_core_repo.py`
- Modify: `backend/app/repositories/__init__.py`
- Modify: `backend/app/path_layout.py`
- Modify: `backend/app/config.py`
- Create: `backend/alembic/versions/0054_agent_attachments.py`
- Test: `backend/tests/test_agent_core/test_attachment_repository.py`
- Test: `backend/tests/test_path_layout.py`

- [ ] **Step 1: Write failing persistence and path tests**

Test that `agent_session_attachments_root(session_id)` returns:

```text
<state_root>/agent_core/attachments/<safe-session-id>
```

Test repository creation, ownership lookup, per-session listing, pending delete,
and deletion of records older than a supplied cutoff.

- [ ] **Step 2: Verify RED**

```bash
rtk uv run pytest tests/test_agent_core/test_attachment_repository.py tests/test_path_layout.py -q
```

Expected: missing model, repository, and path helpers.

- [ ] **Step 3: Add the model and migration**

Create `AgentAttachment` with:

```python
session_id, workspace_id, user_id, kind, source, filename, storage_path,
mime_type, size_bytes, file_count, image_width, image_height, status,
attachment_metadata, error_message, created_at, updated_at
```

Use `ondelete="CASCADE"` for session ownership and indexes on session,
workspace, user, status, and created time. Add the session relationship and a
repository with explicit ownership filters.

- [ ] **Step 4: Add settings and path helpers**

Defaults:

```python
agent_attachment_file_max_bytes = 25 * 1024 * 1024
agent_attachment_image_max_bytes = 20 * 1024 * 1024
agent_attachment_folder_max_bytes = 100 * 1024 * 1024
agent_attachment_folder_max_files = 1000
agent_attachment_turn_max_images = 10
agent_attachment_text_max_bytes = 64 * 1024
agent_attachment_pdf_max_pages = 200
agent_attachment_orphan_ttl_seconds = 24 * 60 * 60
```

- [ ] **Step 5: Apply migration and run tests GREEN**

```bash
rtk uv run alembic upgrade head
rtk uv run pytest tests/test_agent_core/test_attachment_repository.py tests/test_path_layout.py -q
```

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/models backend/app/repositories backend/app/path_layout.py backend/app/config.py backend/alembic/versions/0054_agent_attachments.py backend/tests/test_agent_core/test_attachment_repository.py backend/tests/test_path_layout.py
rtk git commit -m "feat: persist agent session attachments"
```

### Task 3: Implement atomic ingestion and preview

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Create: `backend/app/services/agent_core/attachments.py`
- Modify: `backend/app/schemas/agent_core.py`
- Modify: `backend/app/api/v1/agent.py`
- Test: `backend/tests/test_agent_core/test_attachments.py`
- Test: `backend/tests/test_api/test_agent_attachments_api.py`

- [ ] **Step 1: Add failing service tests**

Cover these independent behaviors:

```python
await service.ingest_files(...)
await service.ingest_folder(files=[...], relative_paths=[...])
await service.ingest_image(...)
```

Assertions:

- image signatures override misleading extensions;
- PNG/JPEG/WebP derivatives are orientation-correct and at most 2048 px;
- unsupported binaries fail with `BadRequestError`;
- folder traversal and duplicate normalized paths fail;
- ignored cache and credential files are omitted;
- a failed folder leaves neither a final directory nor committed record;
- preview returns a validated file and accurate media type;
- deleting a pending attachment removes its directory and row.

- [ ] **Step 2: Verify service tests RED**

```bash
rtk uv run pytest tests/test_agent_core/test_attachments.py -q
```

- [ ] **Step 3: Add dependencies and minimal ingestion service**

```bash
rtk uv add pillow pypdf
```

Implement streamed writes to a private staging directory, content-based type
detection, Pillow image verification/derivative generation, deterministic
folder manifests, atomic rename, and safe public errors. Keep archive and Office
formats unsupported.

- [ ] **Step 4: Add failing API tests**

Test authenticated routes:

```text
POST   /api/v1/agent/sessions/{session_id}/attachments
GET    /api/v1/agent/attachments/{attachment_id}/preview
DELETE /api/v1/agent/attachments/{attachment_id}
```

The POST accepts multipart `kind`, repeated `files`, and repeated
`relative_paths`. Verify cross-user/session access returns 404 or 403 without
leaking existence.

- [ ] **Step 5: Implement schemas and routes, then run GREEN**

```bash
rtk uv run pytest tests/test_agent_core/test_attachments.py tests/test_api/test_agent_attachments_api.py -q
```

- [ ] **Step 6: Commit**

```bash
rtk git add backend/pyproject.toml backend/uv.lock backend/app/services/agent_core/attachments.py backend/app/schemas/agent_core.py backend/app/api/v1/agent.py backend/tests/test_agent_core/test_attachments.py backend/tests/test_api/test_agent_attachments_api.py
rtk git commit -m "feat: ingest agent files folders and images"
```

### Task 4: Resolve typed references into canonical transcript context

**Files:**
- Create: `backend/app/services/agent_core/input_resolver.py`
- Modify: `backend/app/services/agent_core/service.py`
- Modify: `backend/app/services/agent_core/transcript/messages.py`
- Modify: `backend/app/services/agent_core/context/assembler.py`
- Modify: `backend/app/schemas/agent_core.py`
- Test: `backend/tests/test_agent_core/test_input_resolver.py`
- Test: `backend/tests/test_agent_core/test_transcript_model_context.py`
- Test: `backend/tests/test_agent_core/test_context_compaction.py`

- [ ] **Step 1: Write failing typed-reference tests**

Use Pydantic discriminated input models and assert unknown fields are rejected.
Test:

- uploaded text becomes bounded user text with a truncation marker;
- PDF text retains `[Page N]` markers;
- `image_ref` becomes a transcript image reference, not base64;
- `directory_ref` emits only a bounded manifest and read-tool guidance;
- `run_ref` resolves trusted run ID, status, workflow, timestamps, and errors;
- project `file_ref`/`directory_ref` revalidate project ownership and relative
  path;
- a stale reference fails before the turn record is created;
- attachment content remains user-role content;
- compaction does not orphan committed image references.

- [ ] **Step 2: Verify RED**

```bash
rtk uv run pytest tests/test_agent_core/test_input_resolver.py tests/test_agent_core/test_transcript_model_context.py tests/test_agent_core/test_context_compaction.py -q
```

- [ ] **Step 3: Implement `AgentInputResolver`**

The public method is:

```python
async def resolve(
    self,
    *,
    agent_session: AgentSession,
    input_text: str,
    input_parts: list[dict] | None,
) -> list[dict[str, Any]]:
    ...
```

Move legacy file/workflow validation behind this service. Add server-trusted
run/workflow/project resolution. Store image transcript parts as:

```python
{
    "type": "image_ref",
    "attachment_id": str(attachment.id),
    "mime_type": attachment.mime_type,
    "sha256": attachment.attachment_metadata["sha256"],
    "detail": "high",
}
```

- [ ] **Step 4: Resolve image references during context assembly**

Make user-message model-part assembly attachment-aware and asynchronous. Read
the validated derivative immediately before model invocation and create
`ImagePart`. Preserve text/tool behavior and ensure transcript display helpers
ignore binary data.

- [ ] **Step 5: Run GREEN and regression tests**

```bash
rtk uv run pytest tests/test_agent_core/test_input_resolver.py tests/test_agent_core/test_context_file_refs.py tests/test_agent_core/test_transcript_model_context.py tests/test_agent_core/test_context_compaction.py -q
```

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/services/agent_core backend/app/schemas/agent_core.py backend/tests/test_agent_core
rtk git commit -m "feat: resolve structured agent context references"
```

### Task 5: Add target-neutral attachment read tools

**Files:**
- Create: `backend/app/services/agent_core/tools/attachments/__init__.py`
- Create: `backend/app/services/agent_core/tools/attachments/resources.py`
- Modify: `backend/app/services/agent_core/tools/providers.py`
- Modify: `backend/app/services/agent_core/tools/toolsets.py`
- Test: `backend/tests/test_agent_core/test_attachment_tools.py`
- Test: `backend/tests/test_agent_core/test_toolsets.py`

- [ ] **Step 1: Write failing tool tests**

Test `attachments.search` with empty and non-empty queries, ignored files,
bounded results, ownership, and folder-only scope. Test `attachments.read` with
offset/limit, UTF-8 errors, directory rejection, and attachment escape attempts.
Assert both tools remain exposed for a `remote_ssh` execution target.

- [ ] **Step 2: Verify RED**

```bash
rtk uv run pytest tests/test_agent_core/test_attachment_tools.py tests/test_agent_core/test_toolsets.py -q
```

- [ ] **Step 3: Implement and register the two read-only tools**

Use `context.session_id`, `context.workspace_id`, and `context.user_id` for every
lookup. Mark tools `risk_level="read"`, `parallel_safe=True`, and add the
`attachments.` prefix to remote-target-compatible tools.

- [ ] **Step 4: Run GREEN and commit**

```bash
rtk uv run pytest tests/test_agent_core/test_attachment_tools.py tests/test_agent_core/test_toolsets.py -q
rtk git add backend/app/services/agent_core/tools backend/tests/test_agent_core/test_attachment_tools.py backend/tests/test_agent_core/test_toolsets.py
rtk git commit -m "feat: add session attachment read tools"
```

### Task 6: Add scalable context-picker search

**Files:**
- Create: `backend/app/services/agent_core/context_picker.py`
- Modify: `backend/app/repositories/run_repo.py`
- Modify: `backend/app/schemas/agent_core.py`
- Modify: `backend/app/api/v1/agent.py`
- Test: `backend/tests/test_agent_core/test_context_picker.py`
- Test: `backend/tests/test_repositories/test_run_repo.py`
- Test: `backend/tests/test_api/test_agent_context_search_api.py`

- [ ] **Step 1: Write failing search tests**

Seed more than 1,000 runs plus matching files, folders, and workflows. Assert:

```python
mixed.counts == {"file": 4, "workflow": 2, "run": 2}
```

Assert `scope=run` returns only paginated runs, current-project matches precede
other workspace matches, status and workflow names are searchable, and no query
loads every run into Python.

- [ ] **Step 2: Verify RED**

```bash
rtk uv run pytest tests/test_agent_core/test_context_picker.py tests/test_repositories/test_run_repo.py tests/test_api/test_agent_context_search_api.py -q
```

- [ ] **Step 3: Add repository-level run search**

Build a SQL query using `LIKE`/`ilike`-compatible normalized matching across run
ID, run name/config label when present, workflow name, and status. Preserve
workspace ownership, cursor pagination, and deterministic recent ordering.

- [ ] **Step 4: Add bounded file/workflow search and route**

Expose:

```text
GET /api/v1/agent/context/search?q=&scope=mixed|file|run|workflow&project_id=&cursor=
```

Return grouped results and per-scope pagination metadata. Mixed scope never
accepts a run cursor and never returns more than the fixed quotas.

- [ ] **Step 5: Run GREEN and commit**

```bash
rtk uv run pytest tests/test_agent_core/test_context_picker.py tests/test_repositories/test_run_repo.py tests/test_api/test_agent_context_search_api.py -q
rtk git add backend/app/services/agent_core/context_picker.py backend/app/repositories/run_repo.py backend/app/schemas/agent_core.py backend/app/api/v1/agent.py backend/tests
rtk git commit -m "feat: add balanced agent context search"
```

### Task 7: Add frontend attachment and context client contracts

**Files:**
- Modify: `frontend/lib/agent-runtime/types.ts`
- Modify: `frontend/lib/agent-runtime/client.ts`
- Modify: `frontend/hooks/use-agent-runtime.ts`
- Modify: `frontend/hooks/use-llm-settings.ts`
- Test: `frontend/tests/unit/lib/agent-runtime-client.test.ts`
- Test: `frontend/tests/unit/hooks/use-agent-runtime.test.tsx`
- Test: `frontend/tests/unit/hooks/use-llm-settings.test.tsx`

- [ ] **Step 1: Write failing client and hook tests**

Assert multipart upload preserves folder-relative paths, preview URLs include
attachment IDs, delete uses `DELETE`, context search encodes scope/query/cursor,
and `ensureSession()` can be called before a turn. Assert selected models expose
`supports_vision`.

- [ ] **Step 2: Verify RED**

```bash
rtk bun run test -- frontend/tests/unit/lib/agent-runtime-client.test.ts frontend/tests/unit/hooks/use-agent-runtime.test.tsx frontend/tests/unit/hooks/use-llm-settings.test.tsx
```

- [ ] **Step 3: Implement minimal typed APIs**

Add `AgentRuntimeAttachment`, structured reference unions, context-search result
types, `uploadAgentRuntimeAttachment`, `deleteAgentRuntimeAttachment`,
`agentRuntimeAttachmentPreviewUrl`, and `searchAgentRuntimeContext`. Expose a
stable `ensureSession` callback from the runtime hook and permit non-text sends
when input parts contain sendable context.

- [ ] **Step 4: Run GREEN and commit**

```bash
rtk bun run test -- frontend/tests/unit/lib/agent-runtime-client.test.ts frontend/tests/unit/hooks/use-agent-runtime.test.tsx frontend/tests/unit/hooks/use-llm-settings.test.tsx
rtk git add frontend/lib/agent-runtime frontend/hooks frontend/tests/unit
rtk git commit -m "feat: add agent attachment client contracts"
```

### Task 8: Build the structured composer document and inline mentions

**Files:**
- Create: `frontend/lib/agent-runtime/composer-document.ts`
- Create: `frontend/components/bioinfoflow/agent-runtime/structured-composer-editor.tsx`
- Create: `frontend/components/bioinfoflow/agent-runtime/context-picker-menu.tsx`
- Test: `frontend/tests/unit/lib/composer-document.test.ts`
- Test: `frontend/tests/unit/components/structured-composer-editor.test.tsx`
- Test: `frontend/tests/unit/components/context-picker-menu.test.tsx`

- [ ] **Step 1: Write failing pure document tests**

Test ordered text and mention ranges, duplicate prevention, readable clipboard
serialization, input-part conversion, whole-token deletion, and mapping after
text insertion before a token.

Use this public shape:

```typescript
type ComposerMention = {
  id: string
  kind: "file" | "directory" | "run" | "workflow"
  label: string
  detail?: string | null
  inputPart: AgentRuntimeInputPart
}

type ComposerDocument = {
  text: string
  mentions: Array<ComposerMention & { from: number; to: number }>
}
```

- [ ] **Step 2: Verify pure tests RED, implement helpers, and run GREEN**

```bash
rtk bun run test -- frontend/tests/unit/lib/composer-document.test.ts
```

- [ ] **Step 3: Write failing editor interaction tests**

Cover typing `@com`, async option display, selecting at the cursor, Arrow keys,
Enter, Tab, Escape, Backspace next to a token, multiline submit, IME composition,
and copying a token as readable text.

- [ ] **Step 4: Verify editor tests RED**

```bash
rtk bun run test -- frontend/tests/unit/components/structured-composer-editor.test.tsx frontend/tests/unit/components/context-picker-menu.test.tsx
```

- [ ] **Step 5: Implement CodeMirror atomic mention ranges**

Use existing `@codemirror/state` and `@codemirror/view` dependencies. Keep
mention display text in the document, track structured metadata in a state
field, decorate ranges with the existing semantic colors, and expose atomic
ranges so the caret cannot enter a token. Do not introduce a rich-text editor
dependency or global state.

The picker debounces by 150 ms, aborts stale requests, fixes mixed quotas,
supports scoped paging only, and renders loading/empty/error rows without
perpetual animation.

- [ ] **Step 6: Run GREEN and commit**

```bash
rtk bun run test -- frontend/tests/unit/lib/composer-document.test.ts frontend/tests/unit/components/structured-composer-editor.test.tsx frontend/tests/unit/components/context-picker-menu.test.tsx
rtk git add frontend/lib/agent-runtime/composer-document.ts frontend/components/bioinfoflow/agent-runtime/structured-composer-editor.tsx frontend/components/bioinfoflow/agent-runtime/context-picker-menu.tsx frontend/tests/unit
rtk git commit -m "feat: add structured agent context mentions"
```

### Task 9: Build attachment strip, image preview, and clipboard paste

**Files:**
- Create: `frontend/components/bioinfoflow/agent-runtime/attachment-strip.tsx`
- Create: `frontend/components/bioinfoflow/agent-runtime/attachment-preview-dialog.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`
- Test: `frontend/tests/unit/components/attachment-strip.test.tsx`
- Test: `frontend/tests/unit/components/attachment-preview-dialog.test.tsx`
- Modify: `frontend/tests/unit/components/agent-composer.test.tsx`

- [ ] **Step 1: Write failing visual-behavior tests**

Test the one top-level `Add file/folder` entry and secondary `Add files` / `Add
folder` actions. Test image thumbnail preview, close button, Escape, backdrop,
pending deletion, preview focus restoration, uploading/error/retry states, and
send barriers.

Simulate a paste event with both `image/png` and `text/plain`; assert the image
upload callback and text insertion both occur. Keyboard labels must mention
`Cmd+V` on macOS and `Ctrl+V` on Windows without implementing keydown-based
paste interception.

- [ ] **Step 2: Verify RED**

```bash
rtk bun run test -- frontend/tests/unit/components/attachment-strip.test.tsx frontend/tests/unit/components/attachment-preview-dialog.test.tsx frontend/tests/unit/components/agent-composer.test.tsx
```

- [ ] **Step 3: Implement minimal attachment UI**

Use existing theme tokens, Radix Dialog, and the repository icon facade. Keep
8 px radii, one-pixel borders, restrained shadows, and local status rendering.
Do not add gradients, glass, magnetic controls, or continuous motion.

- [ ] **Step 4: Run GREEN and commit**

```bash
rtk bun run test -- frontend/tests/unit/components/attachment-strip.test.tsx frontend/tests/unit/components/attachment-preview-dialog.test.tsx frontend/tests/unit/components/agent-composer.test.tsx
rtk git add frontend/components/bioinfoflow/agent-runtime frontend/tests/unit/components
rtk git commit -m "feat: add agent attachment composer UI"
```

### Task 10: Integrate drafts, submissions, history, and vision gating

**Files:**
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-transcript.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/context-attachments.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Modify: `frontend/tests/unit/components/agent-workbench.test.tsx`
- Modify: `frontend/tests/unit/components/agent-transcript.test.tsx`

- [ ] **Step 1: Write failing integration tests**

Cover:

- pasting before the first message creates a session, then uploads;
- image-only submission works with a vision model;
- a non-vision model preserves the image and opens model selection instead of
  sending;
- unresolved uploads disable send;
- queued and interrupting submissions snapshot their own mentions/attachments;
- successful send clears only the submitted draft;
- retry reconstructs structured parts;
- sent image preview remains available but has no delete action;
- existing skill and workflow mention behavior still works.

- [ ] **Step 2: Verify RED**

```bash
rtk bun run test -- frontend/tests/unit/components/agent-workbench.test.tsx frontend/tests/unit/components/agent-transcript.test.tsx
```

- [ ] **Step 3: Integrate the new draft model**

Replace the single `input` string plus detached workflow arrays with one
`ComposerDocument`, while preserving separate active skill names. Snapshot
document-derived input parts and attachments into `PendingSubmission`. Reset the
draft only after submission is accepted locally.

- [ ] **Step 4: Add bilingual copy and run GREEN**

```bash
rtk bun run test -- frontend/tests/unit/components/agent-workbench.test.tsx frontend/tests/unit/components/agent-transcript.test.tsx frontend/tests/unit/components/agent-composer.test.tsx
rtk bun run lint:i18n
```

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/components/bioinfoflow/agent-runtime frontend/messages frontend/tests/unit/components
rtk git commit -m "feat: integrate agent context attachments"
```

### Task 11: Add cleanup and full regression coverage

**Files:**
- Modify: `backend/app/services/agent_core/attachments.py`
- Modify: `backend/app/services/agent_core/service.py`
- Modify: `backend/app/api/v1/agent.py`
- Test: `backend/tests/test_agent_core/test_attachment_cleanup.py`
- Test: `backend/tests/test_agent_core/test_model_runtime_integration.py`
- Test: `frontend/tests/integration/pages/agent-page-flow.test.tsx`

- [ ] **Step 1: Write failing cleanup and end-to-end contract tests**

Test orphan cleanup at the configured cutoff, immediate filesystem cleanup on
session deletion, persisted preview after archive/reload, actual image parts in
the captured provider request, and non-vision submission rejection before a
turn is committed.

- [ ] **Step 2: Verify RED**

```bash
rtk uv run pytest tests/test_agent_core/test_attachment_cleanup.py tests/test_agent_core/test_model_runtime_integration.py -q
rtk bun run test -- frontend/tests/integration/pages/agent-page-flow.test.tsx
```

- [ ] **Step 3: Implement minimal lifecycle hooks and run GREEN**

Invoke bounded orphan cleanup opportunistically before new uploads and remove
the session attachment root during hard session deletion. Preserve archived
sessions. Do not add a scheduler solely for cleanup.

- [ ] **Step 4: Commit**

```bash
rtk git add backend/app/services/agent_core backend/app/api/v1/agent.py backend/tests frontend/tests/integration/pages/agent-page-flow.test.tsx
rtk git commit -m "test: cover agent attachment lifecycle"
```

### Task 12: Verify, review, rebase, and publish

**Files:**
- Review all changed files.

- [ ] **Step 1: Run focused full suites**

```bash
rtk uv run pytest tests/test_model_runtime tests/test_agent_core tests/test_api/test_agent_attachments_api.py tests/test_api/test_agent_context_search_api.py
rtk uv run ruff check .
rtk bun run test
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk git diff --check
```

- [ ] **Step 2: Run migration and build checks**

```bash
rtk uv run alembic upgrade head
rtk bun run build
```

- [ ] **Step 3: Perform a complete code review**

Review security boundaries, stale-reference transactions, image/provider
payloads, continuation digests, cleanup, async search races, IME behavior,
accessibility, mobile layout, queued-turn snapshots, and unrelated regressions.
Every discovered defect receives a failing regression test before its fix.

- [ ] **Step 4: Re-run all affected checks after review fixes**

Repeat Steps 1 and 2 until clean.

- [ ] **Step 5: Sync the remote default branch**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

Resolve any conflict without discarding user changes, then repeat affected
verification.

- [ ] **Step 6: Push and create the PR**

```bash
rtk git push -u origin codex/agent-context-attachments
rtk gh pr create --base main --head codex/agent-context-attachments --title "feat: add agent context attachments" --body-file /tmp/agent-context-attachments-pr.md
```

The PR body must summarize behavior, architecture, security limits, tests, and
any verification command that could not run.

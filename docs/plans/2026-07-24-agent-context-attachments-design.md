# Agent Context Attachments And Mentions Design

## Status

Approved for implementation on 2026-07-24.

## Problem

The Agent composer currently exposes five placeholder actions under the `+`
menu, but none of them are connected. Project files can already be added to
context from the sidecar as `file_ref` input parts, and the backend expands a
referenced UTF-8 file into at most 64 KiB of transcript text. The model runtime,
however, only supports text and tool parts. It cannot preserve images as typed
multimodal input, upload files into a session-owned location, represent folders
as bounded scopes, or search files and runs from the composer.

The user needs one coherent way to add context from four sources:

- files and folders uploaded from the browser;
- images pasted with `Cmd+V` on macOS or `Ctrl+V` on Windows;
- existing files and folders referenced with `@`;
- existing runs and workflows referenced with `@`.

The design must stay useful when a project contains thousands of runs, must not
silently overflow the model context window, and must preserve the existing
permission and remote-execution boundaries.

## First-Principles Decision

The composer `+` menu adds external context. It does not launch agent tasks.
Preflight and diagnosis remain user intents, prompts, skills, or actions on run
pages rather than attachment-menu items.

The final `+` menu contains one item:

```text
Add file/folder  >
```

Its secondary menu contains `Add files` and `Add folder`. A standard browser
cannot open one native chooser that accepts both files and folders, unlike a
native macOS application. The secondary choice is the smallest consistent Web
implementation.

Pasting an image and selecting context with `@` are direct input gestures, not
additional menu items.

## Product Scope

### Included

- multi-file upload;
- folder upload with relative paths and ignore rules;
- PNG, JPEG, and WebP clipboard-image paste;
- image thumbnail, preview, close, pending deletion, retry, and error states;
- typed file, directory, image, run, and workflow references;
- true inline mention tokens in the composer;
- balanced `@` search plus explicit `@file`, `@run`, and `@workflow` scopes;
- server-side run search and pagination;
- bounded text and PDF extraction;
- native model image parts and provider-specific encoding;
- session-owned attachment storage, cleanup, and authorization;
- target-independent read-only access to uploaded attachment folders.

### Explicitly excluded

- OCR;
- Word, Excel, PowerPoint, archive, BAM, or CRAM content parsing;
- vector search, embeddings, or folder RAG;
- LLM-generated attachment summaries;
- automatic model switching;
- automatic upload to remote SSH nodes;
- URL, browser-page, or cloud-drive attachment sources;
- a global attachment-management screen;
- deleting one attachment from an already committed user turn;
- image annotation or a general image editor;
- resumable or chunked uploads;
- a client-side index of all runs;
- drag-and-drop as a separate first-release requirement.

## Canonical Context Parts

The client and backend exchange structured parts. Display text is never parsed
to recover trusted identifiers.

```text
text             user-authored text
file_ref         project file or uploaded file
directory_ref    project directory or uploaded folder
image_ref        uploaded or pasted image
run_ref          run identifier
workflow_ref     workflow identifier and scope
```

Project references carry a project ID and normalized relative path. Uploaded
references carry an attachment ID. Run and workflow references carry server
identifiers. Labels, paths shown in the UI, statuses, and timestamps are display
metadata only.

Committed turns retain immutable reference snapshots. The canonical transcript
stores typed reference metadata and text/model parts; it never stores image
base64 data.

## Storage And Ownership

Uploaded content is stored under:

```text
BIOINFOFLOW_HOME/state/agent_core/attachments/<session-id>/<attachment-id>/
```

The database stores attachment ownership and metadata:

- attachment ID and session ID;
- workspace ID and user ID;
- kind and source;
- safe relative storage path;
- original display name;
- detected MIME type;
- byte size and optional image dimensions;
- file count for folders;
- processing state and safe public error;
- created and updated timestamps.

The backend accepts only server-issued attachment IDs from the client. It
resolves the on-disk target, verifies session/workspace/user ownership, and
revalidates the file before building model context.

Uploading before the first message lazily creates a draft agent session. A
removed pending attachment is deleted immediately. Draft sessions and orphaned
attachments that never produce a turn are removed after 24 hours. Archiving a
session retains its attachments; deleting a session removes them.

## Ingestion Pipeline

### Files

The browser uploads one or more files to a session attachment endpoint. The
server streams each file into a private staging directory, enforces limits,
detects type from content plus extension, creates metadata, and atomically
promotes the attachment after validation.

### Folders

The browser sends each file with its folder-relative path. The server rejects
absolute paths, parent traversal, empty path segments, and duplicate normalized
paths. Ignored files are omitted. The complete folder is promoted atomically;
validation failure leaves no partial attachment.

Default ignored paths include version-control data, dependency directories,
virtual environments, caches, build output, and known credential or key files.
Symlinks are not accepted from browser uploads. Existing project-directory
references never follow a symlink outside the authorized project root.

### Clipboard images

The composer listens to the browser `paste` event. Valid `image/*` clipboard
files are uploaded as image attachments while meaningful plain text from the
same paste is preserved. The input retains focus. Pasting closes an open mention
menu so the two overlays cannot compete.

## Parsing And Context Budget

### Text and bioinformatics text

- default per-file upload maximum: 25 MiB;
- direct transcript expansion maximum: 64 KiB per file;
- all attachment-derived text together uses at most 20 percent of the target
  model's available input budget;
- excess content remains accessible through bounded read tools;
- truncation is explicitly marked in both metadata and model context.

Large FASTA, FASTQ, VCF, GTF, logs, and similar text files receive deterministic
metadata and bounded samples rather than whole-file injection. Safe metadata
may include byte size, line or record count, detected format, and header sample.

### PDF

- default maximum: 25 MiB and 200 parsed pages;
- extracted text retains page markers;
- encrypted, damaged, or textless scanned PDFs report a clear unsupported
  state;
- PDF text shares the same aggregate context budget.

### Images

- accepted formats: PNG, JPEG, and WebP;
- default maximum: 20 MiB per image and ten images per turn;
- the original is retained for preview;
- a model derivative corrects orientation and fits within a 2048 px longest
  edge while preserving useful screenshot detail;
- file signatures and decodability are verified;
- no OCR or generated description is substituted for the image.

The composer may submit an image-only turn. If the selected model has
`supports_vision=false`, the image remains in the draft, the send action is
disabled, and the UI offers a direct model-selection action. Bioinfoflow never
switches models or performs OCR silently.

### Directories

- default maximum: 1,000 accepted files and 100 MiB total per upload;
- the model receives a bounded manifest, not recursive file content;
- directories are read through `attachments.search` and `attachments.read`;
- `attachments.search` with an empty query provides bounded listing behavior.

These limits are backend settings. The values above are defaults, not client
security controls.

## Model Runtime

Add a canonical image input type to the protocol-neutral model runtime:

```python
@dataclass(frozen=True)
class ImagePart:
    mime_type: str
    data: str
    detail: Literal["auto", "low", "high", "original"] | None = None
```

The model context assembler resolves `image_ref` records only when invoking the
model, reads the validated derivative, and creates `ImagePart`. Provider codecs
map that part to their wire formats:

- Responses: `input_image`;
- Chat Completions: `image_url` data URI;
- Anthropic-compatible requests: base64 image source through LiteLLM;
- Gemini-compatible requests: inline image data through LiteLLM.

Image data is excluded from transcript text conversion and continuation digests
must include stable image identity without persisting raw base64 in database
rows. Compaction retains committed image references so resumed sessions can
rebuild multimodal input while the session exists.

## `@` Mention UX

### Sources

The unified selector contains:

- project and uploaded files;
- project and uploaded directories;
- runs;
- workflows.

Files and directories use `@file`. Runs use `@run`. Workflows use
`@workflow`. Plain `@query` performs a balanced mixed search.

### Scalability rule

Mixed search ranks within each source and applies fixed quotas:

```text
files and directories  4
workflows              2
runs                   2
```

Runs can never consume file or workflow slots. Only explicit `@run` search can
fill the menu with run results and load later pages. Run search is server-side,
debounced by roughly 150 ms, cancellable, scoped to the current project first,
and ordered by match quality, recent use, and update time.

Bare `@` shows a small balanced recent section plus discoverable scope rows for
`@file`, `@run`, and `@workflow`. The mixed menu remains bounded to roughly
eight to ten rows. It never infinite-scrolls.

### Inline tokens

Selecting a result inserts a true structured token at the cursor. Text and
tokens preserve order so the user can express relationships such as comparing
two runs and checking one folder.

Tokens support keyboard navigation, whole-token Backspace deletion, pointer
preview, readable clipboard serialization, duplicate prevention, and accessible
labels. The editor remains compatible with IME composition, multiline text,
skills, and queued submissions. It is a purpose-built structured composer, not
a general document editor.

## Attachment UX

Uploaded attachments render above the structured text flow:

- image attachments use a compact thumbnail;
- files show name and detected type;
- folders show name, accepted file count, and ignored count;
- uploading, error, retry, and vision-incompatible states are local to the
  attachment item;
- sending is disabled while an attachment is unresolved.

Clicking an image thumbnail opens a contained preview. The preview closes with
its close button, Escape, or backdrop click and returns focus to the composer.
Pending images can be removed from either the thumbnail or preview. Removing the
currently previewed image closes the preview first. Sent images remain
previewable but immutable in the first release.

The visual treatment follows the existing Bioinfoflow theme plus the approved
minimalist direction: warm neutral surfaces, one-pixel borders, compact 8 px
radii, nearly absent shadows, restrained semantic colors, no gradients, no
glass effects, and no perpetual animation.

## Remote Execution

Uploaded attachments remain on the Bioinfoflow control plane. The read-only
`attachments.search` and `attachments.read` tools operate on the current
session attachment root regardless of local or remote execution target.

Selecting or mentioning an uploaded file does not copy it to an SSH target. If
an operation requires the file remotely, the agent must request a separate,
audited transfer under the existing approval policy. Remote-project file
mentions preserve their remote origin and use the existing remote read boundary.

## Validation And Failure Semantics

References are revalidated immediately before a turn is committed. A deleted or
newly unauthorized file, directory, run, workflow, or attachment rejects the
submission without creating a partial turn. The client retains the draft and
marks the affected token unavailable.

Folder uploads are atomic. Upload retry reuses the existing draft position.
Queued turns snapshot their own attachments and mentions. Attachment contents
remain user-role context and never enter system instructions.

## Testing And Acceptance

Frontend coverage must verify:

- secondary file/folder choice;
- macOS/Windows clipboard-image paste behavior;
- simultaneous image and text paste;
- thumbnail preview, close, deletion, retry, and focus restoration;
- vision incompatibility and pending-upload send barriers;
- fixed mixed-search quotas and explicit scopes;
- stale async search cancellation;
- keyboard, copy, Backspace, and IME behavior for inline tokens.

Backend coverage must verify:

- ownership, path traversal, symlink, sensitive-file, MIME, and size checks;
- atomic folder ingestion and ignore rules;
- bounded text, PDF, image, and directory context building;
- canonical image-part encoding in both supported wire protocols;
- orphan and session cleanup;
- stale-reference rejection without a committed turn;
- remote-target attachment reads without implicit remote copy.

High-value end-to-end paths are:

- paste a screenshot, preview it, and send it to a vision model;
- upload a text file and folder, then read folder contents on demand;
- find a target through `@run` when the database contains thousands of runs;
- reopen a session and preview a previously sent image;
- block image submission with a non-vision model.

Completion requires matching backend and frontend checks from `AGENTS.md`, plus
targeted regression coverage for existing workflow mentions, skills, queued
turns, transcript compaction, and provider request compilation.

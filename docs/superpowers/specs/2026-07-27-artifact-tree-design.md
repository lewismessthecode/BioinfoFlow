# Artifact tree design

## Goal

Replace the Artifact panel's absolute-path rows with a compact, collapsible file tree that shows only files produced during the current agent session. The visual treatment should follow the approved reference: a quiet file-browser hierarchy, filename-first labels, muted metadata, and no exposed machine-specific path prefix.

## Scope

- Change only the Artifact panel list and its derived presentation data.
- Keep the existing Artifact preview, loading, error, retry, empty, download, and selection behavior.
- Do not load or mirror the full project filesystem; the Files tab remains the complete workspace browser.
- Do not change artifact API payloads or backend persistence.

## Path model

For each deliverable artifact, derive a candidate path from `file_path`, then `payload.path`, then `title`.

1. Normalize separators and remove empty path segments.
2. For absolute paths, find the longest shared parent directory across all path-backed artifacts.
3. Use the shared parent's basename as the visible root label and omit all preceding machine-specific segments.
4. Build nested directory nodes from the remaining relative segments.
5. Artifacts without a usable path appear directly under the root using their title.
6. When multiple artifact records point to the same normalized path, keep one file node and use the newest record for its preview and secondary metadata.

The header count reflects unique visible file nodes rather than raw artifact events.

## Interface

- The root directory is expanded initially and shows its unique file count.
- Nested directories are expanded initially so newly produced files are immediately visible.
- Directory rows use chevrons and folder icons and can be collapsed independently.
- File rows show only the basename as the primary label.
- The latest artifact summary remains as muted secondary text when present.
- Clicking a file opens the existing Artifact viewer for the associated newest artifact record.
- Selected files use the existing quiet neutral active surface.
- Full normalized paths remain available as a native tooltip for disambiguation and diagnostics.
- Keyboard activation and visible focus states remain available for directory and file controls.

## Component boundaries

- Add a focused artifact-tree utility that converts `AgentRuntimeArtifact[]` into directory and file nodes.
- Add a focused tree view component responsible only for expansion state, hierarchy, accessibility, and selection callbacks.
- Keep `ArtifactPreviewDrawer` responsible for loading states and selected artifact preview; it supplies tree data and receives the selected artifact id.

## Edge cases

- A single path-backed file uses its parent directory as the root and its basename as the file node.
- Mixed absolute and relative paths remain grouped beneath a stable session root without exposing an absolute prefix.
- Duplicate paths collapse into one node using the newest artifact record.
- Duplicate basenames in different directories remain distinct.
- Non-file deliverables without paths remain selectable at the root.
- Empty and failed loads continue to use the existing panel states.

## Verification

- Unit-test path normalization, common-root trimming, nesting, duplicate-path handling, and pathless artifacts.
- Component-test directory expansion, visible filenames, hidden absolute prefixes, unique count, selection, and existing preview behavior.
- Run frontend lint, focused Artifact panel tests, the complete frontend test suite, and a production build.
- Visually verify the populated tree in light and dark themes at desktop panel width, including directory collapse and file preview selection.

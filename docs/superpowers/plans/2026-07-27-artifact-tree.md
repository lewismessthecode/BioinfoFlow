# Artifact Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace absolute-path Artifact rows with an accessible, collapsible tree of unique session-produced files using relative paths.

**Architecture:** Derive a pure tree model from deliverable artifacts, keeping path normalization and duplicate resolution outside React. Render that model with a focused tree component that owns expansion state, while `ArtifactPreviewDrawer` continues to own loading states and selected preview state.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS, next-intl, Vitest, Testing Library.

---

## File structure

- Create `frontend/components/bioinfoflow/agent-runtime/artifact-tree.ts`: normalize artifact paths, deduplicate repeated file records, trim shared absolute prefixes, and build typed directory/file nodes.
- Create `frontend/components/bioinfoflow/agent-runtime/artifact-tree-view.tsx`: render accessible directory and file rows, own expanded directory ids, and report file selection.
- Modify `frontend/components/bioinfoflow/agent-runtime/artifact-preview-drawer.tsx`: replace the flat list with the tree model/view while preserving existing loading, error, empty, and preview branches.
- Create `frontend/tests/unit/components/artifact-tree.test.ts`: unit coverage for path and tree derivation.
- Modify `frontend/tests/unit/components/agent-runtime-panel.test.tsx`: component coverage for visual labels, hidden absolute prefixes, expansion, unique count, and preview selection.

### Task 1: Build the artifact tree model

**Files:**
- Create: `frontend/components/bioinfoflow/agent-runtime/artifact-tree.ts`
- Create: `frontend/tests/unit/components/artifact-tree.test.ts`

- [ ] **Step 1: Write failing model tests**

Create fixtures that prove common-prefix trimming, nesting, duplicate-path replacement, and pathless fallback:

```ts
import { describe, expect, it } from "vitest"

import { buildArtifactTree } from "@/components/bioinfoflow/agent-runtime/artifact-tree"
import type { AgentRuntimeArtifact } from "@/lib/agent-runtime"

function artifact(id: string, path: string | null, updatedAt = id): AgentRuntimeArtifact {
  return {
    id,
    session_id: "session-1",
    turn_id: "turn-1",
    type: "file",
    title: path ?? id,
    summary: `${id} summary`,
    payload: null,
    file_path: path,
    resource_ref: null,
    created_at: updatedAt,
    updated_at: updatedAt,
  }
}

describe("buildArtifactTree", () => {
  it("trims the shared absolute prefix and nests relative directories", () => {
    const tree = buildArtifactTree([
      artifact("workflow", "/Users/lewisliu/Dev/ACTIVE/BioinfoFlow/data/projects/run-1/fasta-analysis/workflow.json"),
      artifact("report", "/Users/lewisliu/Dev/ACTIVE/BioinfoFlow/data/projects/run-1/fasta-analysis/results/report.md"),
    ])

    expect(tree.root.name).toBe("fasta-analysis")
    expect(tree.root.children.map((node) => node.name)).toEqual(["results", "workflow.json"])
    expect(tree.fileCount).toBe(2)
    expect(JSON.stringify(tree)).not.toContain("/Users/lewisliu")
  })

  it("keeps the newest record when the same file is produced repeatedly", () => {
    const tree = buildArtifactTree([
      artifact("old", "/workspace/results/report.md", "2026-07-27T01:00:00Z"),
      artifact("new", "/workspace/results/report.md", "2026-07-27T02:00:00Z"),
    ])

    expect(tree.fileCount).toBe(1)
    expect(tree.root.children[0]).toMatchObject({ kind: "file", artifactId: "new" })
  })

  it("places a pathless deliverable at the root using its title", () => {
    const tree = buildArtifactTree([
      { ...artifact("sheet", null), type: "spreadsheet", title: "summary.xlsx" },
    ])

    expect(tree.root.children[0]).toMatchObject({ kind: "file", name: "summary.xlsx" })
  })
})
```

- [ ] **Step 2: Run the model test and verify it fails**

Run:

```bash
rtk bun run test -- tests/unit/components/artifact-tree.test.ts
```

Expected: FAIL because `artifact-tree.ts` does not exist.

- [ ] **Step 3: Implement typed normalization and tree construction**

Create the pure model with these exported shapes and entry point:

```ts
import type { AgentRuntimeArtifact } from "@/lib/agent-runtime"

export type ArtifactTreeFile = {
  kind: "file"
  id: string
  name: string
  path: string
  artifactId: string
  artifact: AgentRuntimeArtifact
}

export type ArtifactTreeDirectory = {
  kind: "directory"
  id: string
  name: string
  path: string
  children: ArtifactTreeNode[]
}

export type ArtifactTreeNode = ArtifactTreeDirectory | ArtifactTreeFile

export type ArtifactTree = {
  root: ArtifactTreeDirectory
  fileCount: number
}

export function buildArtifactTree(
  artifacts: AgentRuntimeArtifact[],
  fallbackRootName = "Artifacts",
): ArtifactTree {
  const records = deduplicateArtifacts(artifacts)
  const sharedSegments = commonParentSegments(records.filter((record) => record.absolute))
  const rootName = sharedSegments.at(-1) ?? fallbackRootName
  const root: ArtifactTreeDirectory = {
    kind: "directory",
    id: "artifact-root",
    name: rootName,
    path: sharedSegments.join("/"),
    children: [],
  }

  for (const record of records) {
    const relative = record.absolute
      ? record.segments.slice(sharedSegments.length)
      : record.segments
    insertArtifact(root, relative.length ? relative : [record.artifact.title], record)
  }

  sortTree(root)
  return { root, fileCount: records.length }
}
```

Implement the private helpers in the same file:

- `artifactPath()` reads `file_path`, string `payload.path`, then `title`.
- `normalizePath()` converts backslashes, collapses repeated slashes, removes `.` segments, and records whether the path was absolute.
- `deduplicateArtifacts()` keys path-backed artifacts by normalized path and uses `updated_at`, then input order, to retain the newest record. Pathless artifacts use `id` as their unique key.
- `commonParentSegments()` compares directory segments only, excluding each record's basename.
- `insertArtifact()` creates stable directory ids from joined relative segments and file ids from normalized path plus artifact id.
- `sortTree()` orders directories before files and compares names with `localeCompare(undefined, { numeric: true, sensitivity: "base" })`.

- [ ] **Step 4: Run the model test and verify it passes**

Run:

```bash
rtk bun run test -- tests/unit/components/artifact-tree.test.ts
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit the model**

```bash
rtk git add frontend/components/bioinfoflow/agent-runtime/artifact-tree.ts frontend/tests/unit/components/artifact-tree.test.ts
rtk git commit -m "feat: derive artifact file trees"
```

### Task 2: Render the accessible tree

**Files:**
- Create: `frontend/components/bioinfoflow/agent-runtime/artifact-tree-view.tsx`
- Modify: `frontend/tests/unit/components/agent-runtime-panel.test.tsx`

- [ ] **Step 1: Write failing tree interaction assertions**

Replace the flat-list assertion with a populated hierarchy:

```tsx
it("renders session artifacts as a relative collapsible file tree", () => {
  render(
    <ArtifactPreviewDrawer
      artifacts={[
        artifact({
          id: "workflow",
          type: "file",
          title: "/Users/lewisliu/project/fasta-analysis/workflow.json",
          file_path: "/Users/lewisliu/project/fasta-analysis/workflow.json",
        }),
        artifact({
          id: "report",
          type: "file",
          title: "/Users/lewisliu/project/fasta-analysis/results/report.md",
          file_path: "/Users/lewisliu/project/fasta-analysis/results/report.md",
        }),
      ]}
    />,
  )

  expect(screen.getByRole("tree", { name: "artifacts.title" })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "fasta-analysis" })).toHaveAttribute(
    "aria-expanded",
    "true",
  )
  expect(screen.getByRole("button", { name: "results" })).toHaveAttribute(
    "aria-expanded",
    "true",
  )
  expect(screen.getByRole("button", { name: /workflow.json/ })).toBeInTheDocument()
  expect(screen.queryByText(/Users\/lewisliu/)).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole("button", { name: "results" }))
  expect(screen.queryByRole("button", { name: /report.md/ })).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the component test and verify it fails**

Run:

```bash
rtk bun run test -- tests/unit/components/agent-runtime-panel.test.tsx
```

Expected: FAIL because the drawer still renders a flat list.

- [ ] **Step 3: Implement `ArtifactTreeView`**

Create a client component with the following public interface:

```tsx
"use client"

import { useState } from "react"
import { ChevronDown, ChevronRight, Folder } from "@/lib/icons"

import { cn } from "@/lib/utils"
import { ArtifactIcon } from "./artifact-viewers"
import type { ArtifactTree, ArtifactTreeDirectory, ArtifactTreeNode } from "./artifact-tree"

export function ArtifactTreeView({
  tree,
  selectedArtifactId,
  label,
  typeLabel,
  onSelectArtifact,
}: {
  tree: ArtifactTree
  selectedArtifactId: string | null
  label: string
  typeLabel: (type: string) => string
  onSelectArtifact: (artifactId: string) => void
}) {
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(() => new Set())

  return (
    <div role="tree" aria-label={label} className="grid min-w-0 gap-0.5">
      <TreeNodeRow
        node={tree.root}
        depth={0}
        collapsedIds={collapsedIds}
        selectedArtifactId={selectedArtifactId}
        typeLabel={typeLabel}
        onToggle={(id) => setCollapsedIds((current) => toggleSet(current, id))}
        onSelectArtifact={onSelectArtifact}
      />
    </div>
  )
}
```

Implement recursive `TreeNodeRow` behavior:

- Directory rows are buttons with `aria-expanded`, `ChevronDown`/`ChevronRight`, `Folder`, filename-first typography, and a root-only file count.
- File rows are buttons with `ArtifactIcon`, basename, muted summary or type label, selected neutral background, native `title={node.path}`, and `onSelectArtifact(node.artifactId)`.
- Use `paddingLeft: depth * 16 + 8` for hierarchy.
- Use `min-h-10`, `rounded-[7px]`, `hover:bg-muted/40`, and existing focus ring tokens; do not add card borders or shadows.
- Render children only while the directory id is not collapsed.

- [ ] **Step 4: Run the component test and verify it passes**

Run:

```bash
rtk bun run test -- tests/unit/components/agent-runtime-panel.test.tsx
```

Expected: Artifact panel tests pass.

- [ ] **Step 5: Commit the tree view**

```bash
rtk git add frontend/components/bioinfoflow/agent-runtime/artifact-tree-view.tsx frontend/tests/unit/components/agent-runtime-panel.test.tsx
rtk git commit -m "feat: render artifact file trees"
```

### Task 3: Integrate the tree into the drawer

**Files:**
- Modify: `frontend/components/bioinfoflow/agent-runtime/artifact-preview-drawer.tsx`
- Modify: `frontend/tests/unit/components/agent-runtime-panel.test.tsx`

- [ ] **Step 1: Add failing duplicate-count and preview assertions**

```tsx
it("counts unique files and previews the newest artifact record", async () => {
  render(
    <ArtifactPreviewDrawer
      artifacts={[
        artifact({
          id: "old-report",
          type: "file",
          title: "/workspace/results/report.md",
          file_path: "/workspace/results/report.md",
          payload: { content: "# Old report" },
          updated_at: "2026-07-27T01:00:00Z",
        }),
        artifact({
          id: "new-report",
          type: "file",
          title: "/workspace/results/report.md",
          file_path: "/workspace/results/report.md",
          payload: { content: "# New report" },
          updated_at: "2026-07-27T02:00:00Z",
        }),
      ]}
    />,
  )

  expect(screen.getByTestId("artifact-count")).toHaveTextContent("1")
  fireEvent.click(screen.getByRole("button", { name: /report.md/ }))
  expect(screen.getByRole("heading", { name: "New report" })).toBeInTheDocument()
  await waitFor(() => {
    expect(screen.getByRole("button", { name: "artifacts.back" })).toHaveFocus()
  })
})
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
rtk bun run test -- tests/unit/components/agent-runtime-panel.test.tsx
```

Expected: FAIL because the header counts raw artifacts and selection uses the old flat list.

- [ ] **Step 3: Replace the flat list integration**

In `ArtifactPreviewDrawer`:

```tsx
const previewArtifacts = useMemo(() => deliverableArtifacts(artifacts), [artifacts])
const artifactTree = useMemo(
  () => buildArtifactTree(previewArtifacts, t("artifacts.title")),
  [previewArtifacts, t],
)
const selected = previewArtifacts.find((artifact) => artifact.id === selectedId) ?? null
```

Use `artifactTree.fileCount` in `data-testid="artifact-count"`. Replace `data-testid="artifact-list"` and the `.map()` rows with:

```tsx
<div className="min-h-0 overflow-y-auto px-1.5 py-2" data-testid="artifact-tree-scroll">
  <ArtifactTreeView
    tree={artifactTree}
    selectedArtifactId={selectedId}
    label={t("artifacts.title")}
    typeLabel={(type) => artifactTypeLabel(t, type)}
    onSelectArtifact={setSelectedId}
  />
</div>
```

Keep the current selected-preview branch and back-button focus effect unchanged. Remove flat-list-only imports such as `ChevronRight` from the drawer.

- [ ] **Step 4: Run all focused Artifact tests**

Run:

```bash
rtk bun run test -- tests/unit/components/artifact-tree.test.ts tests/unit/components/agent-runtime-panel.test.tsx
```

Expected: all focused tests pass.

- [ ] **Step 5: Run lint and i18n coverage**

Run:

```bash
rtk bun run lint
rtk bun run lint:i18n
```

Expected: both commands exit 0 without new warnings.

- [ ] **Step 6: Commit the integration**

```bash
rtk git add frontend/components/bioinfoflow/agent-runtime/artifact-preview-drawer.tsx frontend/tests/unit/components/agent-runtime-panel.test.tsx
rtk git commit -m "feat: show relative artifact paths"
```

### Task 4: Visual verification and release checks

**Files:**
- Modify only if visual verification exposes a defect in the files listed above.

- [ ] **Step 1: Start the frontend in development auth mode**

Use the worktree's repo-root `.env` with `AUTH_MODE=dev`, restart the local frontend, and open `/agent` at desktop width. Do not commit `.env`.

Run from `frontend/`:

```bash
rtk bun run dev
```

Expected: the Agent page returns HTTP 200.

- [ ] **Step 2: Verify the populated Artifact panel visually**

Use a session with multiple nested file artifacts and verify:

- no `/Users/...`, project UUID, or other absolute prefix is visible;
- the root and nested folders match the approved reference hierarchy;
- directories expand and collapse without shifting the header;
- duplicate file events appear once and open the newest preview;
- light and dark themes both retain readable hierarchy and selected state;
- browser console has no application errors.

- [ ] **Step 3: Run complete verification**

Run from `frontend/`:

```bash
rtk bun run test
rtk bun run build
```

Run from the repo root:

```bash
rtk git diff --check
rtk git status --short
```

Expected: all frontend tests and the production build pass; only intended source, test, spec, and plan changes are present.

- [ ] **Step 4: Sync, push, and open the PR**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
rtk git push -u origin codex/artifact-tree-relative-paths
rtk gh pr create --base main --head codex/artifact-tree-relative-paths --title "feat: add artifact file tree" --body $'## Summary\n- replace absolute Artifact paths with a collapsible relative file tree\n- group only session-produced files and keep the newest record for duplicate paths\n- preserve Artifact previews while matching the approved file-browser hierarchy\n\n## Validation\n- bun run lint\n- bun run lint:i18n\n- bun run test\n- bun run build\n- visual verification in light and dark themes'
```

The PR body must summarize relative path trimming, collapsible Artifact-only hierarchy, duplicate-path handling, visual verification, and all validation commands.

- [ ] **Step 5: Merge after required checks pass**

```bash
rtk gh pr checks codex/artifact-tree-relative-paths --watch
rtk gh pr merge codex/artifact-tree-relative-paths --squash --delete-branch
```

Expected: required checks pass and the PR reaches `MERGED`. Preserve the harness-owned worktree.

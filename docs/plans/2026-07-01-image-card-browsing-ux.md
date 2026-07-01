# Image Card Browsing UX Implementation Plan

**Goal:** Redesign the Images page around elegant browsing cards while preserving existing pull, copy, detail, delete, table, and empty-state behavior.

**Architecture:** Introduce a shared resource-card shell for workflow and image cards, then keep image-specific content in image components. Complete the image details sheet as the expanded card state, and add a lightweight card-first selection mode for batch local deletion.

**Tech Stack:** Next.js 16, React 19, Tailwind CSS v4, Radix UI primitives, Vitest, Testing Library.

---

## Phase 1: Shared Resource Card Shell

**Files:**
- Create `frontend/components/ui/resource-card.tsx`
- Modify `frontend/app/(app)/workflows/components/workflow-card-base.tsx`
- Modify `frontend/app/(app)/images/components/image-views.tsx`

**Steps:**
- Create `ResourceCard`, `ResourceCardHeader`, and `ResourceCardActions` primitives that preserve the current card interaction model: low border, low shadow, hover menu reveal, bottom-aligned actions.
- Refactor `WorkflowCardBase` to use the shell without changing workflow behavior.
- Refactor image cards to use the shell and move to a longer browsing ratio: desktop grid defaults to 3 columns, very wide screens can still use 4 columns if space allows.
- Allow image names to wrap to two lines in cards, keeping full references available via tooltip and details.
- Verify with focused card tests and frontend lint.
- Commit: `refactor: unify resource card shell`

## Phase 2: Image Details Action Panel

**Files:**
- Modify `frontend/app/(app)/images/components/image-details.tsx`
- Modify `frontend/app/(app)/images/page.tsx`
- Modify `frontend/messages/en.json`
- Modify `frontend/messages/zh-CN.json`
- Update image page tests as needed.

**Steps:**
- Pass image actions into `ImageDetailsSheet`: copy name, copy pull command, pull/repull, and optional delete local copy.
- Add a concise details layout: full image name, status/size/tag metadata, a `docker pull ...` command block with copy action, and metadata sections for labels, environment, entrypoint, and recent error.
- Keep destructive delete gated by the existing `canDeleteImages` capability and existing delete handler.
- Update i18n in both locales.
- Verify with image page tests and i18n lint.
- Commit: `feat: complete image details actions`

## Phase 3: Browsing-First Batch Selection

**Files:**
- Modify `frontend/app/(app)/images/use-images-page.ts`
- Modify `frontend/app/(app)/images/page.tsx`
- Modify `frontend/app/(app)/images/components/image-views.tsx`
- Modify `frontend/messages/en.json`
- Modify `frontend/messages/zh-CN.json`
- Update image tests.

**Steps:**
- Add selected image id state and derived selected images to the images page hook.
- Add a subtle selection mode: cards reveal checkboxes on hover/focus, selected cards remain visibly selected, and a compact selected-count toolbar appears above the grid.
- Add batch delete that calls the existing delete endpoint for selected local images only, skips non-local or pulling images, refreshes local state, and reports failures without blocking unrelated deletions.
- Keep table and existing single-image actions working.
- Verify with focused integration tests and lint.
- Commit: `feat: add image batch selection`

## Phase 4: Visual Verification, Review, and PR

**Files:**
- No planned source files unless review finds issues.

**Steps:**
- Run `rtk bun run lint`, `rtk bun run lint:i18n`, and focused image tests from `frontend/`.
- Run visual review in dev auth mode if services can be started in this worktree.
- Dispatch parallel review agents for UI behavior, regression risk, and tests/i18n.
- Fix valid review findings and rerun verification.
- Sync `origin/main`, resolve conflicts if any, push branch, and open a draft PR.
- Commit fixes if needed using Conventional Commits.

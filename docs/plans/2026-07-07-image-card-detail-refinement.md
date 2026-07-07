# Image card and detail refinement plan

**Goal:** Turn image management into a quieter, registry-oriented asset browser: compact cards, clearer status and version hierarchy, a more structured details sheet, and reliable cleanup for failed pull records.

**Diagnosis:** The current image cards read like oversized marketing cards. Border, badge, icon, version selector, size row, and two primary-looking actions all compete for attention. Failed status uses too much red and interrupts scanning. Version, status, and size are spatially disconnected, so comparing images requires extra eye movement. The details sheet repeats card-like containers, gives the header and hero block similar weight, and makes the pull command, metadata, labels, environment, and errors feel equally important.

## Phase 1: Failed image cleanup

**Files:**
- `frontend/app/(app)/images/use-images-page.ts`
- `frontend/app/(app)/images/components/image-views.tsx`
- `frontend/app/(app)/images/components/image-details.tsx`
- `backend/app/services/image_service.py`
- Focused frontend/backend tests

**Steps:**
- Introduce a shared frontend deletable rule for `local` or `failed` images.
- Show single-image delete actions for failed cards, table rows, and details sheets.
- Keep batch selection limited to local images for now, because the current copy and size summary describe local-copy deletion.
- Add a backend `FAILED` fast path that deletes the stale DB record without asking Docker for image usage or removal.
- Verify with focused hook/component/service tests, frontend lint, and backend ruff.
- Commit: `fix: allow failed image cleanup`.

## Phase 2: Image card refinement

**Files:**
- `frontend/app/(app)/images/components/image-views.tsx`
- `frontend/components/bioinfoflow/card/browse-card.tsx` if needed
- `frontend/tests/unit/components/image-card-grid.test.tsx`

**Steps:**
- Tighten card padding, radius, grid gap, and metadata rhythm so cards feel like registry assets, not feature cards.
- Make image name, status, selected version, version count, and size the primary readable hierarchy.
- Use muted registry and size text, reserve semantic color for status, and soften failed color treatment.
- Reduce CTA noise: keep pull/repull as the main visible action and move details/copy/delete into the menu.
- Verify with focused card tests and frontend lint.
- Commit: `refactor: refine image cards`.

## Phase 3: Image detail sheet refinement

**Files:**
- `frontend/app/(app)/images/components/image-details.tsx`
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`
- Relevant integration/unit tests

**Steps:**
- Rework the sheet to a 560-640px document-style panel with a sticky summary top area.
- Use one copyable command row, a two-column definition-list metadata section, and lower-emphasis secondary sections.
- Surface failure errors near the summary when present, but keep the styling restrained.
- Keep actions accessible and consistent with card behavior.
- Verify with focused image page/details tests, i18n lint, frontend lint, and a browser smoke check.
- Commit: `refactor: polish image details sheet`.

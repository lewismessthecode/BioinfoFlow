# Frontend i18n Completion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure all user-facing frontend strings (pages, subpages, dialogs, toasts, aria-label/title/placeholder, and selected metadata) are fully driven by `next-intl` messages for `en` and `zh-CN`.

**Architecture:** Continue using `next-intl` (cookie/header locale detection + `NextIntlClientProvider` in `frontend/app/layout.tsx`). Replace hard-coded strings with `useTranslations` / `getTranslations` lookups and add missing message keys to `frontend/messages/en.json` + `frontend/messages/zh-CN.json`, keeping both locales in sync.

**Tech Stack:** Next.js App Router (React client/server components), `next-intl`, TypeScript.

---

## Task 1: Add a lightweight i18n coverage check (TDD harness)

**Files:**
- Create: `frontend/scripts/check-i18n-coverage.mjs`

**Step 1: Write a failing check script**

- Implement a Node script that scans a curated list of known-problem files and fails if any known hard-coded English UI substrings remain (e.g. “Recent Activity”, “Filter”, “Upload Image”, “View Details”, “Copy workflow ID”, etc.).
- Also ensure the script exits non-zero and prints matched file/line snippets to make fixes fast.

**Step 2: Run the script to verify it fails**

Run:
```bash
node frontend/scripts/check-i18n-coverage.mjs
```

Expected: FAIL with matches in current subpages/components.

---

## Task 2: Localize root layout accessibility string + metadata

**Files:**
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Step 1: Add failing coverage entries (if needed)**

- Ensure the coverage check includes `frontend/app/layout.tsx` and flags `Skip to content` and current hard-coded metadata text.

**Step 2: Implement**

- Replace the skip link with `getTranslations("accessibility")` → `t("skipToContent")`.
- Keep `metadata` fixed in English for now (since locale is cookie-based and we are not using language-prefixed URLs yet).
- (Later, if we add language-prefixed URLs, we can revisit localized metadata + `alternates`/`hreflang`.)

**Step 3: Add message keys**

- Add `metadata.appTitle`, `metadata.appDescription`, and `metadata.keywords` (or equivalent) to both message files.

**Step 4: Re-run coverage script**

Expected: layout-related strings no longer flagged.

---

## Task 3: Dashboard page i18n completion

**Files:**
- Modify: `frontend/app/(app)/dashboard/page.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Steps:**
- Replace hard-coded section title/table headers and system status badge texts with `tDashboard`, `tRuns`, `tStatus`, and new keys where needed.
- Localize fallback/error toast messages.
- Re-run coverage script; ensure dashboard is clean.

---

## Task 4: Runs page + run detail sheet i18n completion

**Files:**
- Modify: `frontend/app/(app)/runs/page.tsx`
- Modify: `frontend/app/(app)/runs/components/runs-table-skeleton.tsx`
- Modify: `frontend/app/(app)/runs/components/run-detail-sheet.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Steps:**
- Localize filter button label, table headers, aria-label/title strings, pagination text, and toast content.
- Add missing `runs.*` keys for “Samples”, pagination copy, and run detail sheet sections (“Outputs”, “No logs available…”, etc.).
- Re-run coverage script; ensure runs area is clean.

---

## Task 5: Workflows pages + dialogs + detail tabs i18n completion

**Files:**
- Modify: `frontend/app/(app)/workflows/page.tsx`
- Modify: `frontend/app/(app)/workflows/components/workflow-register-dialog.tsx`
- Modify: `frontend/app/(app)/workflows/components/run-wizard-dialog.tsx`
- Modify: `frontend/app/(app)/workflows/[id]/page.tsx`
- Modify: `frontend/app/(app)/workflows/[id]/components/workflow-overview-tab.tsx`
- Modify: `frontend/app/(app)/workflows/[id]/components/workflow-parameters-tab.tsx`
- Modify: `frontend/app/(app)/workflows/[id]/components/workflow-tasks-tab.tsx`
- Modify: `frontend/app/(app)/workflows/[id]/components/workflow-source-tab.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Steps:**
- Localize “Hub/Project” scope labels and related actions.
- Localize all dialog labels, tips, validation errors, and toasts.
- Localize workflow detail metadata labels and tab titles.
- Re-run coverage script; ensure workflows area is clean.

---

## Task 6: Images page + upload dialog i18n completion

**Files:**
- Modify: `frontend/app/(app)/images/page.tsx`
- Modify: `frontend/app/(app)/images/components/image-upload-dialog.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Steps:**
- Localize status labels, badges, “Shared”, “Used by this project”, action menus, table headers, toasts, and aria-labels.
- Re-run coverage script; ensure images area is clean.

---

## Task 7: Shared components and hooks (toasts + accessibility labels)

**Files (likely):**
- Modify: `frontend/components/bioinfoflow/navbar.tsx`
- Modify: `frontend/components/bioinfoflow/user-menu.tsx`
- Modify: `frontend/components/bioinfoflow/live-deck.tsx`
- Modify: `frontend/components/bioinfoflow/workspace-panel.tsx`
- Modify: `frontend/components/bioinfoflow/command-palette.tsx`
- Modify: `frontend/components/bioinfoflow/chat/chat-input.tsx`
- Modify: `frontend/hooks/use-chat-stream.ts`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Steps:**
- Move remaining hard-coded toasts and accessibility labels into `next-intl` messages.
- Prefer existing namespaces (`common`, `chat`, `accessibility`, etc.) to avoid proliferation.
- Re-run coverage script; ensure overall scan is clean.

---

## Task 8: Final verification

**Step 1: Re-run coverage script**
```bash
node frontend/scripts/check-i18n-coverage.mjs
```

Expected: PASS.

**Step 2: Quick manual sanity checks (if deps available)**
- Optional: `cd frontend && bun run lint`
- Optional: `cd frontend && bun run build`

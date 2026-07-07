# Minimalist app shell redesign implementation plan

**Goal:** Move the protected Bioinfoflow frontend toward a quiet, warm-monochrome app shell with a sparse left sidebar, centered agent composer, and low-noise right-side tool panels inspired by the provided screenshots.

**Architecture:** Keep the current Next.js 16 / React 19 / Tailwind v4 stack and existing runtime behavior. Apply the redesign in narrow phases: global design tokens, app shell/sidebar chrome, then agent composer/right panel polish. Avoid new dependencies and preserve existing tests.

**Tech stack:** Next.js 16, React 19, Tailwind CSS v4, next-intl, Vitest, existing lucide-react icons.

---

## Phase 1: Warm minimalist design tokens

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/lib/appearance/presets.ts`
- Modify: `frontend/tests/unit/styles/globals-light-theme.test.ts`
- Modify: `frontend/tests/unit/lib/appearance-presets.test.ts`

**Steps:**
- [x] Replace cold blue-tinted light tokens with warm white, warm gray, and low-contrast border variables.
- [x] Update the default `codex` light appearance preset so hydration keeps the same palette.
- [x] Update token anchor tests from the old Gemini-inspired palette to the new warm app shell palette.
- [x] Reduce composer/global shadow tokens to ultra-diffuse shadows.
- [x] Change `--font-sans` to prefer `Geist Sans`, `SF Pro Display`, and system UI before falling back.
- [x] Keep dark mode compatible without re-theming the full dark surface.
- [x] Verify with `rtk bun run lint` from `frontend/`.
- [x] Commit as `style: warm minimalist shell tokens`.

## Phase 2: App shell and left sidebar chrome

**Files:**
- Modify: `frontend/app/(app)/app-layout.tsx`
- Modify: `frontend/components/bioinfoflow/navbar.tsx`
- Modify: `frontend/components/bioinfoflow/sidebar/sidebar.tsx`
- Modify: `frontend/components/bioinfoflow/sidebar/sidebar-nav.tsx`
- Modify tests if selectors/classes need updating.

**Steps:**
- [x] Replace `h-screen` shell sizing with `min-h-[100dvh]` and keep the main area overflow-safe.
- [x] Make the top navbar look like a thin desktop-app toolbar with warm background and subtle divider.
- [x] Make expanded and collapsed sidebar items squared-rounded instead of oversized pills.
- [x] Lower sidebar contrast and remove elevated/blur-heavy effects.
- [x] Preserve all existing navigation, keyboard, project, user-menu, and command-palette behavior.
- [x] Verify targeted tests: `rtk bun run test tests/unit/components/sidebar.test.tsx tests/unit/components/sidebar-nav.test.tsx tests/unit/components/navbar.test.tsx tests/integration/components/app-layout-coordination.test.tsx tests/unit/styles/sidebar-header-style.test.ts tests/unit/styles/language-switcher-style.test.ts`.
- [x] Commit as `style: refine app shell sidebar chrome`.

## Phase 3: Agent composer and right panel polish

**Files:**
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-tabbed-panel.tsx`
- Modify: `frontend/components/bioinfoflow/live-deck.tsx`
- Modify: `frontend/components/bioinfoflow/chat/model-selector.tsx`
- Modify tests if stable class expectations change.

**Steps:**
- [x] Give the new-chat agent page the screenshot-like empty canvas and centered command composer.
- [x] Make the composer larger, flatter, and more command-palette-like with bottom-row chips.
- [x] Keep compact side-panel controls accessible at constrained widths.
- [x] Restyle agent sidecar and LiveDeck as right-side tool panels with thin dividers and compact tab chrome.
- [x] Preserve submit, stop, mode toggle, permission mode, model selector, remote target, token usage, attachments, and sidecar behavior.
- [x] Verify targeted tests: `rtk bun run test tests/unit/components/agent-composer.test.tsx tests/unit/components/agent-workbench.test.tsx tests/integration/pages/agent-page.test.tsx`.
- [x] Commit as `style: center agent composer workspace`.

## Phase 4: Full validation and visual check

**Files:**
- Modify `.env` only if local visual verification needs `AUTH_MODE=dev`; do not commit unrelated environment changes.

**Steps:**
- [x] Run `rtk bun run lint` from `frontend/`.
- [x] Run `rtk bun run test` from `frontend/`.
- [x] Run `rtk bun run lint:i18n` if any messages change.
- [x] If feasible, start dev services with `AUTH_MODE=dev`, capture desktop and mobile views of `/agent`, and fix obvious layout overlap.
- [x] Spawn parallel review agents for code, tests, and visual/design risks.
- [x] Fix actionable findings and rerun affected checks.
- [x] Commit review fixes if any.
- [ ] Push branch and open a draft PR.

**Review fix notes:**
- Added composer accessibility and context-title truncation coverage.
- Added workbench coverage for project context handoff into the centered composer.
- Tightened sidebar second-level item and agent overlay styling to match the warm minimalist shell.
- Fixed mobile hydration mismatch caused by reading `matchMedia` during the first client render.

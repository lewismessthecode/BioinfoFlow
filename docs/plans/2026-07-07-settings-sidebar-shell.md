# Settings sidebar shell

## Goal

Give `/settings` its own dedicated left sidebar so the app shell behaves like
Codex / Cursor desktop: entering settings swaps the workspace sidebar for a
settings sidebar (Back to app, section list, account footer), and leaving
settings restores the workspace sidebar. This supersedes the
"single navigation plane" direction from
[2026-07-07-settings-cursor-redesign.md](2026-07-07-settings-cursor-redesign.md).

## Why change direction

- User reviewed side-by-side screenshots of Codex and Cursor and asked for the
  two-mode sidebar model rather than the flat, single-plane page.
- The current settings page uses a top-of-page horizontal `SettingsSectionNav`,
  which is fine on wide screens but does not scale as more settings sections
  land and does not read as a dedicated settings surface.
- Users deep-link into individual settings sections; a sidebar list is the
  natural home for that navigation.

## Design

- The app shell keeps its column layout and window chrome. Only the left
  sidebar contents change based on the current path.
- Trigger: any pathname starting with `/settings`. Route-driven so refresh,
  deep links, and browser Back behave.
- Settings sidebar contains:
  - Return-to-app row (arrow + label). Clicking it navigates to the previous
    workspace route (fallback `/agent`).
  - Search settings input (kept quiet; filters the section list client-side).
  - Grouped section list (Personal / Integration / Coding / Archived etc.).
    Section groups are configuration in a small module, not hardcoded twice.
  - Account footer reusing the existing `UserMenu`.
- The right-side content becomes the current settings section only; the top
  horizontal `SettingsSectionNav` is retired.
- URL contract: each section owns a stable slug. During this phase we keep the
  existing `/settings?section=…` URL because rewiring nested routes is out of
  scope, but we render the section from a shared module so we can upgrade to
  nested routes (`/settings/appearance`) later without breaking links.

## Return navigation

- On entering `/settings`, the settings shell records `document.referrer` from
  inside the SPA via `sessionStorage.setItem("settings-return-path", …)` using
  the pathname captured from the app layout right before navigation.
- The Back button reads that value on click and calls `router.push(returnTo)`.
- If nothing was recorded (direct load / hard refresh), fall back to `/agent`.
- The browser's back button naturally returns to the previous URL because the
  navigation to `/settings` is a real route push, not a state flip.

## Phases

1. Plan and layout skeleton
   - Land this plan document.
   - Add the "settings mode" seam in `frontend/app/(app)/app-layout.tsx` so the
     app shell renders either the workspace `Sidebar` or a new
     `SettingsSidebar` component based on pathname.
   - Ship a minimal `SettingsSidebar` (Back to app, static section list,
     account footer) that navigates using the existing query-string contract.
   - Retire the horizontal `SettingsSectionNav` inside
     `settings-page-client.tsx` and rely on the new sidebar for navigation.
2. Copy and locale wiring
   - Add `settings.sidebar.*` keys to both English and Chinese locale files
     (Back to app, Search settings, group headings, item labels reused from
     `settings.nav.*`).
   - Update `SettingsSidebar` and `SettingsPageClient` to use the new keys.
   - Run `bun run lint:i18n`.
3. Behavior polish and tests
   - Persist the previous workspace pathname across the client transition into
     settings.
   - Add / update integration tests:
     - Settings route renders `SettingsSidebar`, not `WorkspaceSidebar`.
     - Non-settings route still renders `WorkspaceSidebar`.
     - Back button routes to the previously captured workspace path.
   - Run frontend lint + relevant test files. Verify manually in the browser
     with `AUTH_MODE=dev`.

## Validation matrix

- Phase 1: `bun run lint`, targeted `bun test settings-page-flow`.
- Phase 2: `bun run lint`, `bun run lint:i18n`.
- Phase 3: `bun run lint`, `bun run lint:dead-code`, targeted tests for the
  new sidebar switch plus browser smoke test.

## Out of scope

- Renaming routes to `/settings/<section>` (planned as a follow-up).
- Redesigning individual settings section content beyond removing the
  horizontal in-page nav.
- Changing the workspace sidebar visual language.

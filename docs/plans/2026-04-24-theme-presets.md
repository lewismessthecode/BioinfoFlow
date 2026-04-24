# Bioinfoflow Theme Presets Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Codex-style appearance settings section to Bioinfoflow with light/dark/system mode controls, light and dark theme preset selectors, live previews, and app-shell token overrides persisted in browser storage.

**Architecture:** Keep `next-themes` responsible for mode switching and layer a new frontend-only appearance provider on top to apply preset token maps to `document.documentElement`. The provider owns the preset registry, localStorage persistence, and a small hook API consumed by settings, theme toggles, and token-driven shell surfaces.

**Tech Stack:** Next.js App Router, React 19, `next-themes`, Tailwind CSS 4 token variables, Vitest, Testing Library.

## Summary

- Add an `Appearance / 外观` section inside `/settings` with:
  - `light / dark / system` mode switch
  - `light preset` selector
  - `dark preset` selector
  - dual live preview cards
- Ship preset ids:
  - `codex`
  - `linear`
  - `github`
  - `notion`
  - `catppuccin`
  - `everforest`
  - `gruvbox`
  - `one`
  - `proof`
  - `raycast`
- Persist `{ lightPreset, darkPreset }` in localStorage and keep mode persistence under `next-themes`.
- Retokenize the main application shell only. Do not change auth, landing, or demo pages in this pass.

## Key implementation changes

### 1. Appearance infrastructure

**Files:**
- Create: `frontend/lib/appearance/presets.ts`
- Create: `frontend/lib/appearance/provider.tsx`
- Create: `frontend/lib/appearance/use-appearance.ts`
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/app/globals.css`

**Work:**
- Define `ThemePresetId`, `AppearanceTokens`, `AppearancePreset`, and the preset registry.
- Cover the shell tokens actually used today:
  - background / foreground
  - card / popover / secondary / muted
  - border / input / ring
  - sidebar surface tokens
  - shell-only helper tokens such as `--surface-elevated`, `--surface-subtle`, `--announcement-*`, `--bg-*`, `--fg-*`
- Build `AppearanceProvider` that:
  - reads the current theme mode from `next-themes`
  - reads preset config from localStorage
  - resolves the active preset from `resolvedTheme`
  - writes token overrides to `document.documentElement.style`
  - sets `data-appearance-mode` and `data-appearance-preset`
  - updates `meta[name="theme-color"]`
- Expose `useAppearance()` with:
  - `mode`
  - `resolvedMode`
  - `lightPreset`
  - `darkPreset`
  - `activePreset`
  - `setMode`
  - `setLightPreset`
  - `setDarkPreset`

### 2. Settings page appearance UI

**Files:**
- Modify: `frontend/components/bioinfoflow/settings/settings-page-client.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Work:**
- Add `appearance` to the settings nav between `account` and `providers`.
- Add an appearance section with:
  - mode tabs or segmented controls
  - light preset select
  - dark preset select
  - two preview cards for the chosen light and dark presets
- Keep the UI preset-only:
  - no import/export
  - no font selection
  - no free-form color editing

### 3. Main shell retokenization

**Files:**
- Modify: `frontend/components/bioinfoflow/navbar.tsx`
- Modify: `frontend/components/bioinfoflow/user-menu.tsx`
- Modify: `frontend/components/bioinfoflow/sidebar/sidebar.tsx`
- Modify: `frontend/components/bioinfoflow/settings/members-panel.tsx`
- Modify: `frontend/components/bioinfoflow/welcome-card.tsx`
- Modify: `frontend/components/bioinfoflow/terminal/terminal-dock.tsx`
- Modify: `frontend/app/(app)/scheduler/components/advanced-drawer.tsx`

**Work:**
- Replace hard-coded white/slate shell backgrounds with token-driven surfaces.
- Route navbar and user-menu theme toggles through `useAppearance().setMode()`.
- Make terminal themes derive from CSS variables instead of fixed hex pairs.
- Keep semantic success/warning/error colors stable rather than preset-specific.

### 4. Testing

**Files:**
- Create: `frontend/tests/unit/lib/appearance-presets.test.ts`
- Create: `frontend/tests/unit/lib/use-appearance.test.tsx`
- Modify: `frontend/tests/unit/components/navbar.test.tsx`
- Modify: `frontend/tests/unit/components/user-menu.test.tsx`
- Modify: `frontend/tests/unit/components/settings-page.test.tsx`
- Modify: `frontend/tests/integration/pages/settings-page-flow.test.tsx`
- Modify: `frontend/tests/integration/components/terminal-dock.test.tsx`
- Modify: `frontend/tests/unit/styles/sidebar-header-style.test.ts`

**Work:**
- Assert every preset has light and dark token sets with required keys.
- Assert invalid or corrupt localStorage falls back to `codex`.
- Assert navbar and user-menu toggles call `setMode()` instead of `setTheme()`.
- Assert settings page renders the appearance section and persists preset selection.
- Assert terminal theme updates in place from appearance tokens.

## Verification

- `cd frontend && bun run lint`
- `cd frontend && bun run test`
- If needed while iterating, run focused Vitest targets for appearance, settings, navbar, user-menu, and terminal first.

## Assumptions

- Default preset is `codex` for both light and dark.
- Theme presets are frontend-only in v1 and do not touch `/user-settings`.
- Syntax highlighting theme remains light/dark only in v1.
- Auth, landing, and demo pages stay visually unchanged in this pass.

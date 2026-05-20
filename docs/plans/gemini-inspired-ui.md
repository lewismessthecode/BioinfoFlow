# Gemini-Inspired Bioinfoflow Redesign

## Gemini Design Read

Gemini's new "Neural Expressive" direction is airy, centered, and very soft: a mostly white canvas, pale blue gradient glow behind the main prompt, a large friendly greeting, a pill-shaped composer, thin rounded outline icons, sparse chrome, and a left navigation drawer that can collapse into an icon rail.

## Summary

Redesign Bioinfoflow's protected app shell and agent experience to feel Gemini-like while keeping Bioinfoflow identity, routes, auth, projects, and agent behavior intact. The result should look like a faithful Bioinfoflow adaptation, not a Google impersonation: Bioinfoflow logo/name stay, no Gemini branding or copied Google assets.

## Key Changes

- Update global light theme tokens and the default `codex` appearance preset to a Gemini-like palette: white/off-white shell, very light neutral sidebar, restrained text grays, soft borders, elevated white composer, and pale blue radial halo tokens for the agent home.
- Keep dark mode supported, but make the redesign light-first because all supplied references are light-mode Gemini.
- Restyle the app shell with a thinner top navbar, icon-only right actions, softer borders, relaxed spacing, and a main background that can show the central blue glow on agent home.
- Restyle the left sidebar in both states:
  - Collapsed: wider Gemini-like icon rail, black rounded tooltips, large circular active icon target, bottom settings/user area.
  - Expanded: Bioinfoflow logo/name header, pill active row, simple sections for primary nav, workspaces, recents/conversations.
  - Add a Search action that opens the existing command palette.
- Update `ChatInput` with `variant?: "home" | "thread"` while preserving existing `centered` behavior for compatibility.
- Rebuild the empty agent state around a Gemini-like prompt capsule: central greeting, large soft halo, rounded pill composer, left plus/upload button, placeholder, model/execution controls on the right, and send/stop button.
- Add a real hidden file input behind the plus/upload button when `onFileDrop` is available; drag-and-drop behavior remains.
- Restyle quick-start suggestions into subtle rounded pills under the composer and keep the existing localized copy.
- Restyle conversation mode to use the same capsule composer docked at the bottom, with centered message width and lighter assistant/user message treatment.
- Update affected i18n keys in both locale files.

## Public Interfaces

- `ChatInputProps` gains `variant?: "home" | "thread"` and keeps `centered?: boolean` as a backward-compatible alias.
- `Sidebar` gains an optional `onCommandOpen?: () => void` callback so sidebar search can open the existing command palette.
- No backend API, database schema, agent runtime, or CLI behavior changes.

## Test Plan

- `cd frontend && bun run lint`
- `cd frontend && bun run lint:i18n`
- `cd frontend && bun run test -- tests/unit/styles/globals-light-theme.test.ts tests/unit/lib/appearance-presets.test.ts tests/unit/components/chat-input.test.tsx tests/integration/pages/agent-capabilities.test.tsx tests/integration/components/workspace-shell-sidebar.test.tsx tests/integration/components/app-layout-coordination.test.tsx tests/integration/pages/agent-page.test.tsx`
- `cd frontend && bun run build`
- Start `bun run dev` and verify with Browser screenshots at desktop and mobile sizes for `/agent`: empty state, expanded sidebar, collapsed sidebar, conversation composer, no text overlap, no blank/unstyled state.

## Assumptions

- "Gemini-inspired" means matching the visual language and interaction feel, not renaming Bioinfoflow to Gemini.
- Existing product functionality remains in scope; new voice/Gemini Live behavior is out of scope.
- Fresh desktop sessions may default to the Gemini-like collapsed rail only if tests and project creation remain ergonomic; persisted sidebar state continues to win.

# Cursor/Codex Workbench Redesign

Date: 2026-07-07
Branch: `codex/minimalist-app-shell-redesign`

## Decisions

- Keep the product direction as a Codex-like near-black, warm-white workbench.
- Use orange only as a small action accent for send or primary execution moments.
- Rename the default appearance preset from Codex to Workbench.
- Keep a curated theme set in settings: Workbench, Notion, GitHub, Linear, One,
  and Vercel. Each preset keeps its light and dark modes.
- Preserve the dashboard as a system monitoring overview rather than turning it
  into a composer-first launcher.
- Redesign composer selectors into one compact chip grammar, with small muted
  color accents for mode distinctions.

## Scope

### Phase 1: Themes

- Curate the visible theme selector list to the approved presets.
- Keep the underlying light/dark pairing model intact.
- Update default saved appearance fallback to Workbench.
- Adjust tests and settings copy for the renamed default preset.

### Phase 2: Sidebar and Project List

- Make sidebar rows smaller and more refined, closer to Cursor/Codex system
  list rows.
- Reduce heavy branding and container treatment in the left rail.
- Remove dashed empty project cards and large project containers.
- Fix the bottom workspace gap by making empty workspace content feel intentional
  rather than like missing layout.

### Phase 3: Composer Controls

- Unify runtime, model, permission, token, and mode selectors under compact chip
  sizing and state styles.
- Add small, muted color distinction for mode chips.
- Keep safety-critical permission/runtime context visible.
- Keep orange confined to enabled send or primary action affordances.

### Phase 4: Dashboard and Page Consistency

- Preserve dashboard as the system monitoring overview.
- Reduce generic dashboard card weight with flatter hairline sections,
  tighter metrics, and calmer empty states.
- Sweep protected pages for obvious mismatches with the workbench language:
  toolbar density, card radius, border strength, and low-shadow surfaces.

## Verification

- Run focused tests after each phase where practical.
- Before final completion, run frontend lint, tests, i18n lint, and a diff check.
- Use `AUTH_MODE=dev` for local visual review of protected routes.
- Spawn parallel review agents after implementation and fix actionable findings.
- Commit each validated phase separately and update the existing PR.

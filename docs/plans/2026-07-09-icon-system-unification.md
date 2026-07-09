# Icon System Unification Plan

## Goal

Unify Bioinfoflow frontend icon usage behind a replaceable icon system with
consistent sizing, stroke weight, hover affordances, focus states, and restrained
motion.

## Design Read

Bioinfoflow is a dense technical control plane, so the icon language should stay
quiet and precise. Keep Lucide as the current implementation because it already
matches the product, but route app icons through a local adapter so another icon
family can replace it later.

## Architecture

- `frontend/lib/icons.ts` becomes the only public app icon library entrypoint.
  It re-exports Lucide today and owns the `AppIcon` type.
- `frontend/components/ui/icon.tsx` owns icon presentation primitives:
  `Icon`, `IconButton`, `IconSurface`, shared size tokens, and motion tokens.
- `frontend/components/ui/icon-box.tsx` delegates to the shared icon tokens
  instead of carrying private size maps.
- `@lobehub/icons` remains isolated to provider brand icons because brand marks
  are not interchangeable with product glyphs.
- Existing imports from `lucide-react` migrate to `@/lib/icons`, which makes the
  future replacement surface explicit.

## Visual Rules

- Inline/menu icons: `16px`, stroke `1.75`.
- Dense metadata/status icons: `14px`, stroke `1.75`.
- Navigation/sidebar glyphs: `16px` in a `28-32px` control.
- Icon-only buttons: `32px` compact, `36px` default, `40px` large.
- Hover surfaces use semantic tokens only: `bg-accent`, `bg-sidebar-accent`, or
  `bg-foreground/[0.055]` in existing sidebar chrome.
- Motion is functional and brief: color/background `150ms`, icon transform
  `150ms`, active press `scale(0.98)`. Spinners keep existing `animate-spin`.
- Do not animate SVG paths directly; animate the control wrapper or use simple
  transform classes on the icon.

## Phases

1. Add the adapter, primitives, and regression tests that prevent new direct
   `lucide-react` imports outside the adapter.
2. Migrate core shell, sidebar, chat, and agent runtime imports/usages to the
   adapter and shared primitives where the controls are icon-only.
3. Migrate remaining app routes/shared components to the adapter, update docs,
   and run full frontend verification plus visual checks with `AUTH_MODE=dev`
   when local services are available.

## Validation

- `rtk bun run test -- tests/unit/styles/icon-system.test.ts`
- `rtk bun run lint`
- `rtk bun run test`
- `rtk bun run lint:i18n` if any user-facing copy changes
- Visual smoke check for `/agent`, `/dashboard`, and `/workflows` after setting
  `AUTH_MODE=dev` in the worktree `.env` if servers are started.

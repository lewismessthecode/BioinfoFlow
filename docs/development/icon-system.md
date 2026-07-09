# Icon System

Bioinfoflow uses a quiet, dense line-icon system for product UI.

## Imports

Import app glyphs from the local adapter:

```tsx
import { Search } from "@/lib/icons"
```

Do not import `lucide-react` directly from feature files. The adapter in
`frontend/lib/icons.ts` is the only place that should know which open-source
icon family backs the product glyphs.

Provider and model brand marks are separate. Use
`frontend/components/bioinfoflow/chat/provider-icons.tsx` for OpenAI,
Anthropic, Gemini, and other provider identities.

## Primitives

Use `frontend/components/ui/icon.tsx` for new product UI:

- `Icon` for decorative or inline glyphs.
- `IconButton` for icon-only actions with labels, focus rings, hover surfaces,
  and active press feedback.
- `IconSurface` for non-interactive icon containers in cards and empty states.

Existing `Button` also normalizes nested SVG stroke weight and default sizing.

## Sizes

- `xs`: 12px, dense metadata.
- `sm`: 14px, compact sidebar and table glyphs.
- `md`: 16px, default toolbar/menu/action glyphs.
- `lg`: 20px, larger empty-state or card glyphs.
- `xl`: 24px, rare hero-scale product glyphs.

Icon-only controls use fixed containers:

- `sm`: 32px.
- `md`: 36px.
- `lg`: 40px.

## Motion And States

Lucide SVGs inherit the global `.lucide` rule: stroke `1.75`, fast color/opacity
transitions, and no path-level animation. Interactive motion belongs on the
button/control wrapper. Use semantic hover backgrounds:

- App chrome: `hover:bg-accent`.
- Runtime tabs: `hover:bg-muted/45`.
- Sidebar: `hover:bg-sidebar-foreground/[0.055]`.
- Destructive actions: `hover:bg-destructive/10`.

Every icon-only action must have an accessible label and a visible focus state.

## Replacing The Library

To try another library such as Phosphor or Iconoir:

1. Change exports and `AppIcon` in `frontend/lib/icons.ts`.
2. Keep `Icon`, `IconButton`, and `IconSurface` props stable.
3. Update only glyph names that do not exist in the new library.
4. Run `rtk bun run test -- tests/unit/styles/icon-system.test.ts
   tests/unit/components/icon-primitives.test.tsx` from `frontend/`.

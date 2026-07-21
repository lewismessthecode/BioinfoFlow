# Semantic Highlight Colors Design

## Goal

Unify success and failure/destructive colors across the frontend so status
highlights remain clear on light and dark surfaces without becoming saturated
or visually dominant. The selected direction is **A: balanced tonal scale**.

## Scope

- Shared semantic CSS variables for success and failure/destructive states.
- Run status badges, DAG nodes and edges, Composer controls, notifications,
  connection indicators, destructive actions, alerts, toasts, and other
  frontend status treatments.
- Existing hard-coded green and red utilities or hexadecimal values when they
  express success, failure, online, completed, addition, removal, or a
  destructive action.
- Light and dark themes, calibrated independently.

Brand-owned colors such as the Google sign-in logo are excluded. Colors whose
meaning is not success or failure, including warning, information, workflow
engine identity, and plan mode, remain unchanged.

## Palette

Semantic colors use four roles instead of deriving every treatment from one
opaque color:

| Role | Light success | Dark success | Light failure | Dark failure |
| --- | --- | --- | --- | --- |
| Graphic/base | `#3F8A5D` | `#5DBB7C` | `#C0575C` | `#D96C72` |
| Foreground | `#2F744A` | `#78C991` | `#984248` | `#E58A8E` |
| Muted surface | `#E9F3EC` | `#17271D` | `#F9EAEC` | `#2D1B1D` |
| Border | `#C6DEC9` | `#31563D` | `#E9C5C8` | `#60383C` |

The light palette is brighter than the current `#346538` success color but
more restrained than the current Composer execution green. The failure palette
replaces the saturated default red with a muted rose-red of comparable visual
weight.

## Token Model

The global theme exposes explicit semantic roles:

- `--success` and `--error` for icons, dots, DAG edges, and compact graphics.
- `--success-foreground` and `--error-foreground` for text on pale semantic
  surfaces.
- `--success-muted` and `--error-muted` for badges, alerts, and hover surfaces.
- `--success-border` and `--error-border` for outlines and separators.
- `--destructive` maps to the failure base color for existing shadcn-style
  destructive variants.

Components should consume semantic variables through the existing Tailwind
theme mappings. New hard-coded success or failure colors are not introduced.

## Component Treatment

- Status badges use muted surface, foreground, and border roles.
- DAG nodes use the graphic/base color for borders and icons. Completed and
  failed nodes do not use colored outer glows; state is communicated through
  border, icon, and edge color.
- Composer execution controls use the same success roles as the rest of the
  application, including hover states.
- Destructive buttons and icons use the failure base color; soft error panels
  use the muted, foreground, and border roles.
- Dark mode uses opaque low-luminance semantic surfaces and separately chosen
  brighter foregrounds. It does not invert or alpha-mix the light palette.

## Audit Rules

Search the frontend for semantic uses of `emerald-*`, `green-*`, `red-*`,
`rose-*`, `text-destructive`, `bg-destructive`, `text-success`, `bg-success`,
and related hexadecimal values. Each hard-coded occurrence is classified before
replacement:

- Replace when it communicates success, completion, connectivity, failure,
  deletion, or destructive intent.
- Preserve when it belongs to a third-party brand or a non-semantic asset.
- Preserve warning and information treatments.

## Accessibility

- Text and status labels must remain readable against their semantic surfaces
  in both themes.
- Color is not the only status signal; existing labels, icons, and shapes stay
  intact.
- Focus rings remain neutral and are not replaced with semantic colors.
- Motion-reduction behavior remains unchanged.

## Verification

Run from `frontend/`:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run test
```

Also run `rtk git diff --check` from the repository root and visually inspect
representative light and dark states for runs, DAG, Composer, destructive
actions, alerts, toasts, and connection indicators. Any pre-existing or
environmental failure is reported with its exact command and output summary.

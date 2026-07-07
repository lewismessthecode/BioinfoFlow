# Settings Cursor-style redesign

## Goal

Refactor Bioinfoflow settings into a Cursor-inspired, single-navigation-plane page: keep the app sidebar as the only sidebar, remove the nested settings sidebar, and present settings as a quiet centered surface with grouped rows, restrained controls, and warm monochrome spacing.

## Cursor design notes

- One clear navigation plane; settings does not stack a second heavy sidebar beside the main app shell.
- Large warm-white canvas with generous whitespace and a narrow, centered settings column.
- Section headings are small and direct; configuration lives in rounded grouped cards.
- Each row uses title and helper copy on the left, with controls or actions aligned on the right.
- Borders and active states are low-contrast; color is reserved for semantic state or primary actions.

## Phases

1. Map the current settings route, i18n keys, and tests, then land this plan.
   - Validate with a lightweight diff check.
2. Replace the nested settings sidebar with the new focused settings layout.
   - Validate with frontend lint, targeted tests, i18n lint if copy changes, and browser inspection.
3. Polish responsive behavior, spacing, and any test/copy fallout.
   - Validate with the full relevant frontend checks and browser verification.

## Constraints

- Work with the existing Next.js and styling stack.
- Preserve existing settings functionality and form behavior.
- Update both English and Chinese locale files for any changed user-facing copy.
- Keep surfaces flat: light borders, minimal shadows, no loud gradients, no extra icon libraries.

# Simplify Appearance Preview Design

## Goal

Make the light and dark theme previews easier to scan by replacing the detailed
application skeleton with compact theme thumbnails.

## Design

- Keep the existing two-card light and dark comparison.
- Keep each card's title, preset name, logo, and mode badge.
- Reduce the preview card height from roughly 420px to roughly 220-240px.
- Represent the application with a small sidebar rail and a few content blocks.
- Remove the terminal mockup, window controls, button pills, and nested secondary
  cards.
- Continue using the selected preset's appearance tokens so each thumbnail
  accurately communicates its palette.
- Preserve the existing single-column mobile and two-column desktop layout.

## Verification

- Update focused source-level tests to describe the compact skeleton.
- Run the appearance preview unit test, settings page tests, frontend lint, and
  frontend test suite.
- Visually inspect the appearance settings page in both desktop and narrow
  viewport layouts.

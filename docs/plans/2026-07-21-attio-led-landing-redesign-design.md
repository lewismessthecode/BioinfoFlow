# Attio-led Landing Page Redesign

## Status

Visual direction approved in conversation on 2026-07-21. This written design is
awaiting the user's final review before implementation begins.

## Goal

Redesign the BioinfoFlow demo landing page around a high-fidelity product tour.
The page should use Attio's product-led pacing and scroll choreography while
preserving BioinfoFlow's existing neutral application design, explicit light /
dark theme switch, bilingual content, routes, and product behavior.

The landing page must feel like the same product as the application. It must not
invent a separate visual identity, redraw fake dashboards, or use decorative
effects that compete with the real interface.

## Approved Direction

- Primary reference: Attio's spacious hero, product-first composition, and
  scroll-driven product storytelling.
- Secondary reference: Linear's restraint in typography, borders, information
  density, and motion. The page does not adopt Linear's dark visual environment.
- Macrostructure: Workbench. Real product surfaces are the primary evidence.
- Light mode remains light for the whole page. Dark mode is entered only through
  the existing theme control and switches the whole page at once.
- Typography: preserve Geist Sans and Geist Mono.
- Brand colour: Precision Mineral Blue, derived from the existing logo.
  `#4F7894` is the working light-mode accent. It occupies less than roughly 2%
  of a viewport and is limited to active navigation, focus rings, progress,
  selected paths, and other precise interaction signals.
- Primary buttons remain charcoal in light mode and light neutral in dark mode.
  The brand blue does not become a large button fill or a decorative gradient.
- No production file or component directory is deleted as part of the initial
  redesign. Existing landing components may stop rendering but remain available
  until visual approval and cleanup authorization.

## Applied Design Skills

Implementation and review must continue applying the four user-selected skills:

- `design-taste-frontend-v1`: dependency verification, Tailwind 4 correctness,
  isolated client-side motion, stable mobile layouts, transform/opacity-only
  animation, tactile controls, and performance restraint.
- `gpt-taste`: AIDA completeness, wide two-line desktop hero, GSAP
  ScrollTrigger product storytelling, image scale/fade, and layered product
  screens.
- `minimalist-ui`: Geist typography, warm-neutral surfaces, crisp hairline
  borders, minimal diffuse shadows, restrained radii, and scarce muted colour.
- `hallmark redesign`: preserve implementation boundaries and content intent,
  use a Workbench macrostructure, avoid generic SaaS card rhythms, prohibit
  fabricated facts and redrawn UI chrome, and verify mobile and accessibility
  gates.

When skill defaults conflict, the user's approved direction wins. In
particular, the Attio-style centred hero is intentional; the real-product
capture requirement overrides any skill example that permits faux window
chrome; and the existing application theme system overrides any proposal for a
scroll-triggered light-to-dark transition.

## Page Structure

### Announcement and navigation

Keep one compact announcement strip above a canonical three-part SaaS
navigation:

- BioinfoFlow logo and wordmark on the left.
- Product, Workflows, Security, and Docs in the centre.
- GitHub, locale, theme, sign-in, and start actions on the right.

The navigation remains sticky. It uses a neutral surface and hairline divider.
The active section may use a 2 px Precision Mineral Blue underline. Mobile
collapses to a menu without wrapping navigation or CTA labels.

### Hero and continuous product entry

The hero uses a wide, centred Attio-style composition because that direction was
explicitly selected by the user. The headline stays within two lines on standard
desktop widths and uses concrete product language.

The real Dashboard begins at the bottom of the first viewport. It is not a
separate illustration. The same Dashboard element continues into the product
story:

1. The initial screen is rendered close to its final full-size dimensions but
   begins with a transform scale around `0.78–0.84` and a downward translation.
2. Scrolling fades the hero copy, moves the Dashboard upward, and scales it to
   `1` without animating width, height, top, or left.
3. The Dashboard pins below the sticky navigation and becomes the full product
   stage.
4. There is no duplicate Dashboard and no prose-only bridge between the hero
   screenshot and the product stage.

This directly fixes the discontinuity identified in the approved prototype.

### Scroll-driven product story

Use one isolated client component powered by GSAP and `@gsap/react` with
ScrollTrigger. It owns the full pinned sequence and contains no Framer Motion
components.

The sequence uses real BioinfoFlow captures in this order:

1. Dashboard: readiness, system state, and recent activity.
2. Agent: describe the biological objective and prepare a plan.
3. Workflows: select or register an inspectable pipeline.
4. Runs: inspect status, logs, history, and recovery actions.

Each transition is driven by scroll progress. Screens use transform and opacity
only. A small Precision Mineral Blue progress path identifies the current stage.
Copy changes with the active screen but remains secondary to the product.

Desktop uses a pinned product stage. Mobile uses a shorter, non-overlapping
sequence with reduced scale travel. `prefers-reduced-motion` removes pinning and
renders the product captures as a readable static stack with opacity-only entry.

### Supported workflows band

Retain the real workflow categories already present in the locale files:
RNA-seq, ChIP-seq, variant calling, single-cell, and metagenomics. Present them
as a restrained hairline-separated band rather than logos or animated marquee
content.

### Capability index

Replace generic equal feature cards with a tabular capability index. Each row
maps a concrete job to a real product surface:

- Describe the analysis — Agent.
- Select a validated workflow — Workflows.
- Execute where the data lives — Runtime / scheduler.
- Recover from recorded evidence — Runs.
- Preserve artifacts and provenance — run history and workspace files.

Existing product-tab, bento, how-it-works, results, and security copy remains the
content source. It may be condensed and reorganized, but factual intent is
preserved and both locale files stay complete.

### Local compute and security

Preserve the hardware-check functionality and local-first security claims.
Redesign them as two spacious, asymmetric sections using hairline rows and real
product/runtime details rather than three equal cards.

Hardware loading, compatible, partial, and incompatible states remain
functional and accessible. Security content continues to state that data stays
on user-controlled infrastructure and that runs retain provenance.

### Final CTA and footer

Use one primary CTA and a short reassurance line. The footer is a statement-led
close with only the necessary product, documentation, GitHub, privacy, and terms
links. Avoid the existing multi-column link farm.

## Theme and Colour

The landing consumes the application's existing semantic tokens. Add only the
minimum marketing-specific tokens required for the Precision Mineral Blue
system, for example:

```css
:root {
  --brand-accent: #4f7894;
  --brand-accent-muted: #e5edf1;
  --landing-product-stage: #f7f8f8;
}

.dark {
  --brand-accent: #8fb9d2;
  --brand-accent-muted: #1c2a32;
  --landing-product-stage: #11171b;
}
```

Final implementation should express these through the project's Tailwind v4
theme/token conventions rather than spreading raw colour values through JSX.
Semantic success, warning, error, and info colours remain separate from the
brand accent.

## Product Capture Standard

Landing visuals must be captured from the real BioinfoFlow application. Fake
HTML browser chrome and hand-redrawn dashboard replicas are prohibited.

Create a repeatable Playwright-based capture workflow that:

- Runs the real protected application UI in `AUTH_MODE=dev`.
- Uses prepared demo data or deterministic API interception so the visible
  content is complete and repeatable.
- Waits for loading and skeleton states to finish.
- Hides development-only overlays such as Agentation and Next.js dev tools.
- Captures light and dark variants for Dashboard, Agent, Workflows, and Runs.
- Uses a 2x device scale factor and a desktop viewport suitable for at least
  2560 px-wide source output.
- Exports optimized WebP or AVIF assets with PNG retained only when required for
  visual fidelity.
- Preserves readable text at the largest landing presentation size.
- Avoids Docker errors, incomplete skeletons, empty accidental states, and
  invented metrics in primary marketing captures.

If a functional empty or error state is intentionally discussed, it appears in
a later explanatory section and is labelled honestly. It is not the hero asset.

## Motion Architecture

- Add `gsap` and `@gsap/react` to the frontend dependencies.
- Isolate the scroll story in one leaf client component.
- Register ScrollTrigger inside the client component.
- Use `useGSAP()` context cleanup so navigation and hot reload do not leave
  orphaned triggers.
- Use `gsap.matchMedia()` for desktop, mobile, and reduced-motion variants.
- Animate only transform and opacity.
- Keep the sticky navigation above the pinned product stage with an explicit
  offset and named z-index tokens.
- Do not mix Framer Motion inside the GSAP scroll-story component tree.
- Ordinary buttons and non-story UI use existing CSS transitions or current UI
  primitives; they do not gain decorative perpetual motion.

## Internationalisation and Copy

- Update `frontend/messages/en.json` and `frontend/messages/zh-CN.json`
  together.
- Preserve the `Bioinfoflow` product-name headline requirement covered by the
  existing SEO metadata test, either in the hero copy or through an adjusted
  test that still verifies the product name is prominent and indexable.
- Use concrete, active language. Avoid invented customer logos, testimonials,
  adoption counts, performance numbers, or compliance claims.
- The existing supplied WGS claim may be retained only with its existing scope
  and wording; do not generalize it into an unsupported platform-wide metric.

## Accessibility and Responsive Behaviour

- Maintain the existing skip link and semantic heading order.
- All controls have visible `:focus-visible`, hover, active, disabled, and
  pending states where applicable.
- Theme, locale, mobile menu, hardware checker, and navigation remain keyboard
  operable.
- Product captures have meaningful alt text; decorative layers are hidden from
  assistive technology.
- No horizontal scrolling at 320, 375, 414, 768, 1280, 1440, or 1920 px.
- CTA and navigation labels remain single-line affordances.
- The desktop headline remains at most two lines at the selected reference
  widths. Mobile may wrap further without overflow.
- Reduced motion produces a complete static reading experience rather than
  hiding product content.

## Expected Implementation Scope

Expected modifications:

- `frontend/package.json`
- `frontend/bun.lock`
- `frontend/app/globals.css`
- `frontend/components/landing/demo-landing-page.tsx`
- `frontend/components/landing/announcement-bar.tsx`
- `frontend/components/landing/navigation.tsx`
- `frontend/components/landing/final-cta.tsx`
- `frontend/components/landing/footer.tsx`
- `frontend/components/landing/hardware-section.tsx`
- `frontend/components/landing/security-section.tsx`
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`

Expected additions:

- A landing hero / product-scroll-story client component under
  `frontend/components/landing/`.
- A tabular capability-index component under `frontend/components/landing/`.
- A repeatable capture script under `frontend/scripts/`.
- High-resolution light and dark product assets under
  `frontend/public/landing/`.
- Focused unit tests for landing composition, theme-aware assets, copy, and
  reduced-motion behavior.

Expected deletions: none before user visual approval.

The final file list may be narrower after implementation planning and code
inspection. Any deletion or broad cleanup remains a separate approval step.

## Verification and Acceptance

### Automated verification

From `frontend/`:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run test
rtk bun run build
```

Run focused tests while iterating, then the broader frontend commands above.
Run `rtk bun run lint:dead-code` if the composition change creates unused
landing exports.

### Visual verification

Verify the running page in both English and Chinese at:

- 1440 × 900 light and dark.
- 1280 × 800 light and dark.
- 768 px tablet.
- 414 px and 375 px mobile.

The visual review must confirm:

- The first Dashboard is high-resolution, complete, and not a skeleton.
- The Dashboard continuously enlarges from the hero into the pinned product
  story without duplication or a prose-only gap.
- Dashboard, Agent, Workflows, and Runs transition in the approved order.
- Product text remains readable at the largest screenshot size.
- Precision Mineral Blue remains a small interaction signal, not a large colour
  fill.
- Theme switching swaps the landing palette and the real product assets
  together.
- The sticky navigation does not overlap the pinned stage.
- The transition identified as discontinuous in the prototype is visually
  continuous.
- Reduced-motion mode remains complete and usable.

### User gate

After automated and visual verification, provide the user with screenshots or a
local preview for approval. Do not create the pull request until the user
confirms the implemented result.

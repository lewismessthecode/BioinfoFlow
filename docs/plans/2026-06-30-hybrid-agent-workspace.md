# Hybrid agent workspace

## Goal

Implement the approved Bioinfoflow workspace direction:

- Keep the current Bioinfoflow product sidebar and center agent workspace.
- Replace the right side with a Codex-like tool and file preview panel.
- Render common file outputs natively where feasible: HTML, Markdown, sheets, and PDF.
- Preserve existing agent, artifact, terminal, project, run, workflow, image, connection, and scheduler behavior.
- Apply small minimalist refinements without changing the product identity.

## Phases

1. Audit and integration map.
   - Inspect current agent side panel, artifact data, file APIs, i18n, tests, and visual validation setup.
   - Outcome: implementation scope confirmed.

2. Hybrid workspace shell.
   - Keep current sidebar and composer flow.
   - Rework the agent right panel into a Codex-like tool/file panel.
   - Preserve existing sidecar behavior behind the new panel.

3. Native preview renderers.
   - Add render states for HTML, Markdown, CSV/TSV/table-like sheets, and PDF.
   - Provide unsupported, loading, and error states.
   - Add an affordance for opening files in the default application or fallback download/open route.

4. Visual polish and copy.
   - Keep warm monochrome surfaces, low shadows, crisp borders, and modest radius.
   - Add required English and Simplified Chinese messages.
   - Avoid broad visual rewrites.

5. Validation and review.
   - Run focused tests while iterating.
   - Run frontend lint/test/i18n checks before final completion.
   - Perform visual review with `AUTH_MODE=dev` if local services are needed.
   - Spawn review agents, fix findings, then open a PR.

## Guardrails

- No unrelated route or navigation changes.
- No destructive git operations.
- Preserve user or generated changes, including existing concept mockups.
- Prefer existing Tailwind v4, Radix, Lucide, and local component patterns.
- New visible copy must be in both locale files.

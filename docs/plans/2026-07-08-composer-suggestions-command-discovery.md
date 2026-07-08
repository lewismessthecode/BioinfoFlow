# Composer Suggestions and Command Discovery Plan

## Goal

Add a restrained discovery layer around the starter agent composer:

- A Cursor-like starter suggestion list directly below the centered composer.
- A quiet bottom command discovery hint rail for capability tips.
- A real, narrow `@workflow` composer affordance that turns the token into workflow-focused context for the next turn.

## Design Direction

The UI should read as part of the composer, not as onboarding chrome. It should use the existing agent composer width, white or warm-white surfaces, `1px` soft borders, minimal shadow, small muted icons, and compact command tokens rendered like keyboard hints. Avoid the yellow annotation border from the reference screenshots, large cards, gradients, heavy shadows, and detached marketing-style empty states.

## Implementation Steps

1. Add focused tests around the current agent composer/workbench behavior:
   - Starter suggestions render only on the empty centered composer.
   - Clicking a starter suggestion fills the composer with the suggested prompt.
   - Bottom discovery hints render in the starter state and include `@workflow`, slash-skill selection, and `Shift+Tab`.
   - Submitting text containing `@workflow` sends workflow context with the turn.

2. Implement starter suggestions in `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`:
   - Keep suggestions aligned to the centered composer width.
   - Use 4 concise Bioinfoflow-specific suggestions.
   - Hide suggestions after a draft exists or once a conversation is active.

3. Implement command discovery hints:
   - Place them at the bottom of the starter surface with enough distance from the composer.
   - Use a lightweight horizontal ticker/rotating rail with muted text and `<kbd>`-style command tokens.
   - Keep motion subtle and respect reduced motion.

4. Implement `@workflow` support narrowly:
   - Treat `@workflow` as a composer token for workflow-focused context.
   - On submit, remove the literal token from the user-visible prompt sent as text and add a `file_ref`-compatible input part with a stable virtual path such as `bioinfoflow://workflow-context`.
   - Preserve existing file attachments, slash skills, model selection, and queue/interrupt behavior.

5. Update localized strings:
   - Add English and Chinese copy in `frontend/messages/en.json` and `frontend/messages/zh-CN.json`.
   - Run i18n coverage after changing copy.

6. Verification:
   - `rtk bun run test -- frontend/tests/unit/components/agent-composer.test.tsx frontend/tests/unit/components/agent-workbench.test.tsx`
   - `rtk bun run lint:i18n`
   - `rtk bun run lint`
   - Visual review with `AUTH_MODE=dev` if local services are needed for browser checks.

## Phase Commits

1. `docs: plan composer suggestions`
2. `feat: add composer suggestions and workflow hinting`
3. `test: cover composer discovery polish` if test-only follow-up is needed, otherwise include tests with the feature commit.


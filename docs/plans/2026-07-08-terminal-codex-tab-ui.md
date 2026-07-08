# Terminal Codex Tab UI Follow-up Plan

**Goal:** Make the Bioinfoflow terminal dock match the Codex terminal reference more closely: a restrained tab strip with one compact light-grey terminal tab, a nearby plus affordance, real terminal content padding, and no automatic expansion unless the user explicitly opens the terminal.

## Phase 0: Setup

- [x] Start from latest `origin/main` after PR #108 was merged.
- [x] Create `codex/terminal-codex-tab-ui`.
- [x] Dispatch parallel UI and open-state audit agents.

## Phase 1: Behavior Fix

- [ ] Stop restoring terminal open state from local storage.
- [ ] Keep height persistence only.
- [ ] Ensure `chdir()` does not open the terminal implicitly.
- [ ] Add integration coverage proving stored `open=true` no longer auto-opens.
- [ ] Commit behavior fix.

## Phase 2: Codex-like Terminal Surface

- [ ] Replace the old header-chip treatment with a Codex-like tab strip.
- [ ] Add a compact light-grey terminal tab plus a nearby `+` affordance.
- [ ] Increase top/left terminal viewport padding so prompt text no longer hugs the panel edge.
- [ ] Keep remote/local target labels readable without making the header busy.
- [ ] Update focused terminal dock tests.
- [ ] Commit UI redesign.

## Phase 3: Review, Verification, PR

- [ ] Run targeted frontend tests and lint.
- [ ] Run parallel review agents after implementation.
- [ ] Fix review findings.
- [ ] Run final verification.
- [ ] Push branch and open PR.

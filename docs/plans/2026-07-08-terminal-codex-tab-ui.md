# Terminal Codex Tab UI Follow-up Plan

**Goal:** Make the Bioinfoflow terminal dock match the Codex terminal reference more closely: a restrained tab strip with one compact light-grey terminal tab, a nearby plus affordance, real terminal content padding, and no automatic expansion unless the user explicitly opens the terminal.

## Phase 0: Setup

- [x] Start from latest `origin/main` after PR #108 was merged.
- [x] Create `codex/terminal-codex-tab-ui`.
- [x] Dispatch parallel UI and open-state audit agents.

## Phase 1: Behavior Fix

- [x] Stop restoring terminal open state from local storage.
- [x] Keep height persistence only.
- [x] Ensure `chdir()` does not open the terminal implicitly.
- [x] Add integration coverage proving stored `open=true` no longer auto-opens.
- [x] Commit behavior fix.

## Phase 2: Codex-like Terminal Surface

- [x] Replace the old header-chip treatment with a Codex-like tab strip.
- [x] Add a compact light-grey terminal tab plus a nearby `+` affordance.
- [x] Increase top/left terminal viewport padding so prompt text no longer hugs the panel edge.
- [x] Keep remote/local target labels readable without making the header busy.
- [x] Update focused terminal dock tests.
- [x] Commit UI redesign.

## Phase 3: Review, Verification, PR

- [x] Run targeted frontend tests and lint.
- [x] Run parallel review agents after implementation.
- [x] Fix review findings.
  - [x] Make closed-dock `chdir()` a no-op so hidden terminal actions cannot queue.
  - [x] Clear queued commands on project changes and validate command project ownership before execution.
  - [x] Hide run-directory terminal actions until the dock is already open.
  - [x] Make the `+` affordance truly disabled until multi-session terminals exist.
  - [x] Refine the active tab to a restrained grey surface and add reduced-motion coverage.
- [ ] Run final verification.
- [ ] Push branch and open PR.

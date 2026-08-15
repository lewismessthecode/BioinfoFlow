# CI/CD Simplification Plan

## Goal

Make pull-request validation, development image publication, and formal releases
follow one observable path each. The design should support parallel Codex and
Claude Code worktrees without weakening merge safety or multiplying orchestration
workflows.

## Delivery Invariants

1. Every pull request reports one stable required check named `CI` for the exact
   tested merge commit.
2. Internal backend, frontend, Docker, installer, and workflow checks may be
   skipped by changed-area detection, but the final `CI` gate always exists and
   fails closed.
3. Release Please-created pull requests trigger normal `pull_request` workflows;
   manually dispatched CI is not a substitute for PR checks.
4. Release Please owns only version calculation, `CHANGELOG.md`, the numeric Git
   tag, and the GitHub Release.
5. Formal images and installer assets are built only from the immutable numeric
   tag supplied to the publication workflow.
6. Formal publication is directly linked through `workflow_call`, not through an
   asynchronous `gh workflow run` hop.
7. Published images come only from formal numeric release tags; ordinary
   `main` pushes do not mutate package aliases.
8. Release recovery accepts the numeric tag as the source of truth regardless of
   which ref was used to start the recovery workflow.
9. Workflows use least-privilege job permissions and do not use a
   `pull_request_target` workflow merely to implement auto-merge.

## Decisions

### Pull-request CI

- Keep changed-area detection and parallel leaf jobs.
- Replace the three protected summary contexts (`backend`, `frontend`, and
  `docker`) with one `CI` summary job.
- Add `merge_group` support so CI is ready for GitHub's native merge queue.
- Keep strict branch protection until merge volume justifies migrating the
  repository to a merge-queue ruleset. Enabling the queue now would add external
  ruleset machinery without evidence that the current merge rate needs it.

### Release Please credentials

- Require `RELEASE_PLEASE_TOKEN`; do not fall back to `GITHUB_TOKEN`.
- Configure the repository secret before merging this change so Release
  Please-created PRs naturally trigger CI.
- Prefer a dedicated fine-grained PAT or GitHub App token. The existing local
  GitHub OAuth token may be used only as an explicit operational bridge when no
  narrower credential is available.

### Formal publication

- Convert `.github/workflows/release.yml` into a reusable and manually
  dispatchable publication workflow.
- Call it directly from `.github/workflows/release-please.yml` when Release
  Please reports `release_created=true`.
- Validate and checkout the numeric tag inside the publication workflow.
- Serialize formal releases with a fixed concurrency group and keep the Release
  PR as the human gate that prevents overlapping versions.

### Development images

- Repository search found documentation for `main` and `sha-*` images but no
  deployment or automation that consumes them.
- Remove image publication from ordinary `main` pushes. This eliminates an
  ordering race around the mutable `main` alias and avoids spending two
  multi-architecture builds after every merge.
- Keep source-built development through Compose and publish GHCR images only
  from intentional immutable releases.

### Auto-merge and multi-agent flow

- Delete the custom label-driven `pull_request_target` auto-merge workflow.
- Use GitHub's native auto-merge through `gh pr merge --auto`, choosing squash or
  rebase explicitly for the PR.
- Continue the repository rule: one writing agent, one worktree, one branch, one
  PR. Assign a single integration owner to hot files such as workflows,
  changelogs, lock files, migrations, and locale catalogs.

## Files

- Modify `.github/workflows/ci.yml`.
- Modify `.github/workflows/codeql.yml`.
- Delete `.github/workflows/auto-merge.yml`.
- Modify `.github/workflows/release-please.yml`.
- Modify `.github/workflows/release.yml`.
- Modify `.github/workflows/container-release.yml`.
- Modify `AGENTS.md`.
- Modify `RUNBOOK.md`.
- Modify `scripts/github/configure-repo.sh`.
- Modify `backend/tests/scripts/test_release_automation.py`.
- Modify workflow contract assertions in `scripts/tests/install-test.sh`.
- Modify `docs/development/github-ci-cd.md`.
- Modify `docs/development/releases.md`.

## Verification

1. Run `actionlint` over every workflow.
2. Run `sh scripts/tests/install-test.sh`.
3. Render the localhost and production Compose configurations.
4. Run `git diff --check` and inspect ignored/untracked state.
5. Push the branch and verify the new `CI` gate on the pull request.
6. Before merge, configure `RELEASE_PLEASE_TOKEN` and change branch protection
   from `backend`, `frontend`, `docker` to `CI` without weakening strict mode.
7. Rebase onto the latest `origin/main`, rerun relevant checks, and rebase-merge
   the pull request after all required checks pass.

## Recovery

- If the new `CI` context has not appeared, keep the old required contexts and
  do not merge.
- If the Release Please credential cannot be configured, do not merge a workflow
  that requires it; restore the branch to a working credential design first.
- If formal publication fails after a numeric tag exists, rerun `release.yml`
  with the same tag. Never recreate or move the tag.

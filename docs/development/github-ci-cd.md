# GitHub CI/CD and PR Automation

This repository uses GitHub Actions to make worktree branches flow through PRs, checks, review, and squash merge.

## What Runs

- `CI` runs on PRs to `main`, pushes to `main`, and manual dispatch.
- `CodeQL` runs on PRs to `main`, pushes to `main`, weekly schedule, and manual dispatch.
- `Container Release` publishes development Docker images after eligible code reaches `main`.
- `Release` maintains the Release Please PR and dispatches the installer/image release after that PR is intentionally merged.
- `Installer Release` publishes three formal multi-architecture images, smoke-tests the localhost installer, and attaches its assets to the GitHub Release.
- `PR Automation` opens a PR to `main` when you push a non-main branch.
- `Auto Merge` queues a squash merge when a reviewed PR has the `automerge` label.

Release Please creates its pull request with `GITHUB_TOKEN`. The `Release`
workflow explicitly dispatches `CI` against the generated release branch so the
protected `backend`, `frontend`, and `docker` checks still run. Release PRs must
not receive the `automerge` label.

## CI Change Detection

The `CI` workflow always produces the protected `backend`, `frontend`, and `docker` status checks. Do not add workflow-level `paths-ignore` or skip the whole workflow for PRs; GitHub branch protection waits forever if a required check never appears.

Heavy work is skipped inside the workflow instead:

- `backend checks` runs only when PR changes touch `backend/` or shared env defaults.
- `frontend lint`, `frontend test`, and `frontend build` run in parallel only when PR changes touch `frontend/` or shared env defaults.
- `docker build` runs only when Dockerfiles, compose files, dependency locks/manifests, or the CI/release workflows change.
- Pushes to `main` and manual dispatches run the full CI path.
- Docs-only PRs still get successful `backend`, `frontend`, and `docker` checks, but the expensive jobs are skipped.

## Required Checks

The protected `main` branch expects these status checks:

- `backend`
- `frontend`
- `docker`

The `scripts/github/configure-repo.sh` script configures these checks through the GitHub API.

Keep these three check names stable. If the internal CI job graph changes, make the required checks summary jobs rather than changing branch protection for every implementation detail.

## Worktree Flow

Create or enter a feature worktree:

```bash
git worktree add ../bioinfoflow-feature-auth -b feature/auth main
cd ../bioinfoflow-feature-auth
```

Develop normally, then commit and push:

```bash
git add .
git commit -m "feat: add auth flow"
git push -u origin feature/auth
```

GitHub Actions opens a PR from `feature/auth` to `main` when the repository allows Actions to create pull requests. The PR title is normalized to the Conventional Commits format and is treated as the future squash-merge title. Existing open PRs for the same branch are updated if the latest commit provides a better conventional title.

If that permission is disabled, `PR Automation` emits a warning and exits successfully; create the PR manually once, then every later push to the same branch updates the PR and reruns CI:

```bash
git push
```

When `main` moves ahead, rebase inside the worktree:

```bash
git fetch origin main
git rebase origin/main
git push --force-with-lease
```

After review, add the `automerge` label to let GitHub queue a squash merge once required checks pass.

## Review Automation Boundaries

CI, CodeQL, dependency update PRs, and branch protection are automated review aids. They catch formatting, test, build, Docker, dependency, and security issues.

They are not a replacement for human code review. GitHub Actions is configured with `can_approve_pull_request_reviews: false`, so automation cannot approve its own PR. On this single-collaborator repository, `scripts/github/configure-repo.sh` defaults to `REQUIRED_APPROVALS=0` to avoid making every PR impossible to merge. After adding collaborators, run:

```bash
REQUIRED_APPROVALS=1 scripts/github/configure-repo.sh lewismessthecode/BioinfoFlow
```

## Squash Merge Policy

The repository is configured to:

- allow squash merge
- disable merge commits
- allow rebase merge
- enable auto-merge
- delete merged branches

The recommended daily path is still squash merge. Rebase merge remains available for rare cases where preserving each commit is useful.

## Published Images

Development and formal release images are pushed to:

```text
ghcr.io/lewismessthecode/bioinfoflow-backend
ghcr.io/lewismessthecode/bioinfoflow-frontend
ghcr.io/lewismessthecode/bioinfoflow-frontend-localhost
```

Eligible merges to `main` publish development tags only:

```text
main
sha-<12-char-sha>
```

The development workflow publishes backend and frontend images independently.
Backend-only changes publish only the backend image. Frontend changes publish
both authenticated and localhost frontend variants. Manual `workflow_dispatch`
with `publish_images=force` publishes all three development images;
`publish_images=skip` publishes none.

Merging a Release Please PR dispatches `Installer Release`, which publishes all
three images with the same formal version:

```text
0.2.1
0.2
0
latest
```

Exact numeric versions identify immutable release source. Minor, major, and
`latest` aliases advance to the newest formal release. Ordinary merges to
`main` never update `latest`. See the [Release Maintainer SOP](releases.md) for
the release procedure and recovery rules.

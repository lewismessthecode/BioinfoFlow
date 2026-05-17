# GitHub CI/CD and PR Automation

This repository uses GitHub Actions to make worktree branches flow through PRs, checks, review, and squash merge.

## What Runs

- `CI` runs on every branch push, PR to `main`, and manual dispatch.
- `CodeQL` runs on PRs to `main`, pushes to `main`, weekly schedule, and manual dispatch.
- `Container Release` publishes backend and frontend Docker images to GHCR after code reaches `main`.
- `PR Automation` opens a PR to `main` when you push a non-main branch.
- `Auto Merge` queues a squash merge when a reviewed PR has the `automerge` label.

## Required Checks

The protected `main` branch expects these status checks:

- `backend`
- `frontend`
- `docker`

The `scripts/github/configure-repo.sh` script configures these checks through the GitHub API.

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

GitHub Actions opens a PR from `feature/auth` to `main` when the repository allows Actions to create pull requests. If that permission is disabled, `PR Automation` emits a warning and exits successfully; create the PR manually once, then every later push to the same branch updates the PR and reruns CI:

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

After a successful merge to `main`, images are pushed to:

```text
ghcr.io/lewismessthecode/bioinfoflow-backend
ghcr.io/lewismessthecode/bioinfoflow-frontend
```

Each image gets:

```text
latest
main
sha-<12-char-sha>
```

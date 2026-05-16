# GitHub CI/CD Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GitHub-native CI/CD and PR automation setup for BioinfoFlow so worktree branches can be pushed, opened as PRs, verified, reviewed, and squash-merged safely.

**Architecture:** Use GitHub Actions for PR CI, CodeQL scanning, Docker image delivery to GHCR, automatic PR creation, and guarded auto-merge. Use GitHub repository settings and branch protection to make `main` accept only checked PR merges.

**Tech Stack:** GitHub Actions, GitHub CLI/API, uv, Bun, Docker Buildx, GHCR, CodeQL.

---

### Task 1: PR and Push CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [x] **Step 1: Add backend CI**

Run backend checks on PRs, pushes to `main`, and manual dispatch:

```yaml
backend:
  name: backend
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6
    - uses: astral-sh/setup-uv@v8.1.0
      with:
        enable-cache: true
        cache-dependency-glob: backend/uv.lock
    - run: uv sync --frozen
      working-directory: backend
    - run: uv run ruff check .
      working-directory: backend
    - run: uv run pytest
      working-directory: backend
```

- [x] **Step 2: Add frontend CI**

Run frontend install, lint, i18n coverage, tests, and build with deterministic CI env:

```yaml
frontend:
  name: frontend
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6
    - uses: oven-sh/setup-bun@v2
      with:
        bun-version: latest
    - run: bun install --frozen-lockfile
      working-directory: frontend
    - run: bun run lint
      working-directory: frontend
    - run: bun run lint:i18n
      working-directory: frontend
    - run: bun run test
      working-directory: frontend
    - run: bun run build
      working-directory: frontend
```

- [x] **Step 3: Add Docker build verification**

Build both production images without pushing on PRs:

```yaml
docker:
  name: docker
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6
    - uses: docker/setup-buildx-action@v4
    - uses: docker/build-push-action@v7
      with:
        context: ./backend
        file: ./backend/Dockerfile
        push: false
        load: false
    - uses: docker/build-push-action@v7
      with:
        context: ./frontend
        file: ./frontend/Dockerfile
        push: false
        load: false
```

### Task 2: Delivery After Main

**Files:**
- Create: `.github/workflows/container-release.yml`

- [x] **Step 1: Publish backend and frontend images to GHCR**

On `main` pushes and manual dispatch, log into GHCR with `GITHUB_TOKEN` and publish:

```yaml
permissions:
  contents: read
  packages: write
```

Images:

```text
ghcr.io/lewismessthecode/bioinfoflow-backend
ghcr.io/lewismessthecode/bioinfoflow-frontend
```

Tags:

```text
latest
main
sha-<12-char-sha>
```

### Task 3: PR Automation and Guarded Auto-Merge

**Files:**
- Create: `.github/workflows/pr-automation.yml`
- Create: `.github/workflows/auto-merge.yml`
- Create: `.github/dependabot.yml`

- [x] **Step 1: Auto-open PRs from feature branches**

On branch push, skip `main`, `dependabot/**`, and temporary branches, then create a PR to `main` if one does not exist.

- [x] **Step 2: Queue squash auto-merge by label**

When a PR has the `automerge` label and is not a draft, call:

```bash
gh pr merge "$PR_URL" --squash --auto --delete-branch
```

This relies on branch protection so it waits for required checks instead of bypassing them.

- [x] **Step 3: Keep Actions dependencies fresh**

Configure Dependabot for GitHub Actions weekly updates.

### Task 4: Security Review Automation

**Files:**
- Create: `.github/workflows/codeql.yml`

- [x] **Step 1: Add CodeQL**

Run CodeQL for Python and JavaScript/TypeScript on PRs, pushes to `main`, weekly schedule, and manual dispatch.

### Task 5: Repository Policy Script and Documentation

**Files:**
- Create: `scripts/github/configure-repo.sh`
- Create: `docs/development/github-ci-cd.md`
- Modify: `backend/Dockerfile`

- [x] **Step 1: Add repo configuration script**

Configure GitHub repository settings:

```text
allow squash merge: true
allow merge commit: false
allow rebase merge: true
allow auto merge: true
delete branch on merge: true
```

Protect `main` with required checks:

```text
backend
frontend
docker
```

- [x] **Step 2: Document the worktree-to-PR flow**

Explain how to push a worktree branch, let the PR automation open a PR, watch CI, request review, label `automerge`, and let GitHub squash merge after required checks pass.

- [x] **Step 3: Fix backend Docker base image**

Change `backend/Dockerfile` from Python 3.12 to Python 3.13 so it matches `backend/pyproject.toml`.

### Task 6: Verification

**Commands:**
- Run: `bash -n scripts/github/configure-repo.sh`
- Run: `git diff --check`
- Run: `cd backend && uv run ruff check .`
- Run: `cd backend && uv run pytest`
- Run: `cd frontend && bun install --frozen-lockfile`
- Run: `cd frontend && bun run lint`
- Run: `cd frontend && bun run lint:i18n`
- Run: `cd frontend && bun run test`
- Run: `cd frontend && bun run build`

- [x] **Step 1: Run local verification**

Expected: all commands pass locally, or any pre-existing unrelated failures are called out with exact output.

- [x] **Step 2: Apply remote GitHub settings**

Run:

```bash
scripts/github/configure-repo.sh
```

Expected: repository merge settings and `main` branch protection are updated.

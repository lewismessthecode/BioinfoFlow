# Release Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish `0.1.0` as Bioinfoflow's first tracked release and automate future curated, numeric-tag releases with synchronized container images and an English maintainer SOP.

**Architecture:** A root `version.txt` and Release Please manifest represent one application version across the backend and frontend. Release Please maintains a human-gated release pull request; the same workflow publishes formal container tags after it creates a GitHub Release, while the existing main-branch workflow publishes only development tags.

**Tech Stack:** GitHub Actions, Release Please v4, GHCR, Docker Buildx, Python 3.13, pytest, JSON/TOML metadata, Markdown.

---

## File Map

- Create `version.txt`: canonical root release version for the simple releaser.
- Create `CHANGELOG.md`: curated English product changelog beginning at `0.1.0`.
- Create `release-please-config.json`: numeric-tag, pre-1.0, changelog, and extra-file policy.
- Create `.release-please-manifest.json`: record `0.1.0` as the current bootstrap version.
- Create `.github/workflows/release-please.yml`: maintain the Release PR and publish formal images.
- Modify `.github/workflows/container-release.yml`: publish only `main` and immutable SHA development tags.
- Modify `.github/workflows/ci.yml`: treat release workflow and metadata changes as Docker-impacting.
- Modify `backend/app/config.py`: mark the runtime version for Release Please updates.
- Modify `backend/tests/test_smoke.py`: compare FastAPI metadata with the configured release version.
- Create `backend/tests/scripts/test_release_automation.py`: enforce version and workflow contracts.
- Create `docs/development/releases.md`: full English release and recovery SOP.
- Modify `docs/development/github-ci-cd.md`: describe the split development/formal release channels.
- Modify `docs/getting-started/docker.md`: document stable and development image tags.
- Modify `docs/README.md`: link the release SOP.
- Modify `AGENTS.md` and `CLAUDE.md`: add concise durable release rules and the SOP pointer.

### Task 1: Add Failing Release-Policy Tests

**Files:**
- Create: `backend/tests/scripts/test_release_automation.py`
- Modify: `backend/tests/test_smoke.py`

- [ ] **Step 1: Add a version consistency test**

Read `version.txt`, `backend/pyproject.toml`, `frontend/package.json`,
`docs/contracts/openapi-v1.json`, and the `Settings.app_version` default. Assert
that every value equals `0.1.0`.

- [ ] **Step 2: Add Release Please configuration tests**

Assert that `release-please-config.json` uses `simple`, disables the `v` prefix,
enables minor bumps for pre-major breaking changes, and updates the backend,
frontend, runtime default, and OpenAPI contract through `extra-files`.

- [ ] **Step 3: Add workflow channel tests**

Assert that `.github/workflows/container-release.yml` contains `main` and
`sha-` tags but no `latest` tag. Assert that
`.github/workflows/release-please.yml` contains Release Please v4 and formal
exact, minor, major, and `latest` image tags.

- [ ] **Step 4: Remove the hard-coded FastAPI version assertion**

Change the smoke test to compare `fastapi_app.version` with the default from
`Settings.model_fields["app_version"]`.

- [ ] **Step 5: Run the narrow tests and verify failure**

Run:

```bash
rtk uv run pytest tests/scripts/test_release_automation.py tests/test_smoke.py -q
```

Expected: release-policy tests fail because the version, config, changelog, and
release workflow files do not exist yet; existing smoke tests still pass.

- [ ] **Step 6: Commit the failing contract**

```bash
rtk git add backend/tests/scripts/test_release_automation.py backend/tests/test_smoke.py
rtk git commit -m "test: define release automation contracts"
```

### Task 2: Add Version and Release Please Metadata

**Files:**
- Create: `version.txt`
- Create: `CHANGELOG.md`
- Create: `release-please-config.json`
- Create: `.release-please-manifest.json`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add the bootstrap version files**

Set `version.txt` to `0.1.0` and the root manifest to:

```json
{
  ".": "0.1.0"
}
```

- [ ] **Step 2: Configure one numeric-tag application release**

Use a root `simple` package named `bioinfoflow`, set
`include-v-in-tag` to `false`, set `bump-minor-pre-major` to `true`, keep
`bump-patch-for-minor-pre-major` false, and expose Features, Bug Fixes,
Performance Improvements, and Reverts in the changelog. Hide internal commit
types by setting their changelog sections to `hidden: true`.

Configure these extra files:

```text
backend/pyproject.toml                 $.project.version
backend/uv.lock                        generic annotation on the root package version
frontend/package.json                 $.version
backend/app/config.py                  generic annotation
docs/contracts/openapi-v1.json         $.info.version
```

- [ ] **Step 3: Annotate the runtime version default**

Keep the value at `0.1.0` and add the inline
`x-release-please-version` marker to the `app_version` field.

- [ ] **Step 4: Add the curated initial changelog**

Create an English `0.1.0` entry dated 2026-07-21 with a short initial-release
statement and 10 to 15 verified product highlights. Do not list historical
pull requests individually.

- [ ] **Step 5: Run version and config tests**

```bash
rtk uv run pytest tests/scripts/test_release_automation.py -q
```

Expected: metadata assertions pass; workflow assertions still fail until Task 3.

- [ ] **Step 6: Commit release metadata**

```bash
rtk git add version.txt CHANGELOG.md release-please-config.json .release-please-manifest.json backend/app/config.py
rtk git commit -m "chore: add initial release metadata"
```

### Task 3: Separate Development and Formal Container Publishing

**Files:**
- Create: `.github/workflows/release-please.yml`
- Modify: `.github/workflows/container-release.yml`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Restrict main-branch publishing to development tags**

Retain backend/frontend change detection, but publish only:

```text
main
sha-<12-char-sha>
```

Remove `latest` from both jobs.

- [ ] **Step 2: Add the Release Please job**

Run `googleapis/release-please-action@v4` on pushes to `main` and manual
dispatch, with `contents: write`, `pull-requests: write`, and `packages: write`.
Use the checked-in manifest and configuration files.

- [ ] **Step 3: Resolve automatic and bootstrap release versions**

Expose a `workflow_dispatch` input named `publish_version`. For a normal
Release Please release, use the action's `tag_name` and `version` outputs. For
the one-time bootstrap, require `publish_version` to match an existing numeric
GitHub Release and tag before allowing image publication. Parse major and minor
aliases from the validated semantic version.

- [ ] **Step 4: Publish both formal images**

Use a backend/frontend matrix, check out the release tag, and publish:

```text
<major>.<minor>.<patch>
<major>.<minor>
<major>
latest
```

Use a release-scoped concurrency group and never enable cancellation during a
publish.

- [ ] **Step 5: Expand CI change detection**

Treat Release Please configuration, version metadata, and both release
workflows as Docker-impacting so pull requests exercise the Docker build check.

- [ ] **Step 6: Run release contract tests**

```bash
rtk uv run pytest tests/scripts/test_release_automation.py tests/test_smoke.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit workflows**

```bash
rtk git add .github/workflows/release-please.yml .github/workflows/container-release.yml .github/workflows/ci.yml
rtk git commit -m "ci: automate curated releases"
```

### Task 4: Document the Maintainer SOP and Agent Rules

**Files:**
- Create: `docs/development/releases.md`
- Modify: `docs/development/github-ci-cd.md`
- Modify: `docs/getting-started/docker.md`
- Modify: `docs/README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Write the English release SOP**

Document the daily PR title rules, how to review the proposed version and
changelog, when to edit or merge the Release PR, required checks, post-release
verification, the one-time `0.1.0` bootstrap commands, urgent patch procedure,
and workflow rerun recovery. State that exact numeric tags are immutable.

- [ ] **Step 2: Update CI/CD and Docker documentation**

Explain that `main` and `sha-*` are development tags, while exact versions,
major/minor aliases, and `latest` are formal-release tags.

- [ ] **Step 3: Add the documentation index link**

Add the release SOP to `docs/README.md` under development or operations.

- [ ] **Step 4: Add concise release rules to both agent guides**

Add identical bullets to `AGENTS.md` and `CLAUDE.md`: bare numeric tags,
Conventional Commit version effects, no manual CHANGELOG edits in ordinary pull
requests, never auto-merge a Release PR, and the SOP path.

- [ ] **Step 5: Verify guide synchronization and Markdown**

```bash
rtk diff -u AGENTS.md CLAUDE.md
rtk git diff --check
```

Expected: no guide differences and no whitespace errors.

- [ ] **Step 6: Commit documentation**

```bash
rtk git add AGENTS.md CLAUDE.md docs/README.md docs/development/releases.md docs/development/github-ci-cd.md docs/getting-started/docker.md
rtk git commit -m "docs: add release maintainer SOP"
```

### Task 5: Full Verification and Pull Request

**Files:**
- Verify all files changed by Tasks 1 through 4.

- [ ] **Step 1: Run backend checks**

```bash
rtk uv run ruff check .
rtk uv run pytest
```

Expected: both commands pass from `backend/`.

- [ ] **Step 2: Run frontend checks**

```bash
rtk bun run lint
rtk bun run test
```

Expected: both commands pass from `frontend/`.

- [ ] **Step 3: Validate generated contracts and repository diffs**

```bash
rtk uv run python scripts/export_openapi_contract.py --check ../docs/contracts/openapi-v1.json
rtk git diff --check origin/main...HEAD
rtk git status --short
```

Expected: the generated contract matches, no whitespace errors exist, and only
intentional files are changed.

- [ ] **Step 4: Sync with the remote default branch**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

Expected: rebase completes without losing release automation changes.

- [ ] **Step 5: Push and open the pull request**

```bash
rtk git push -u origin codex/release-automation
rtk gh pr create --base main --head codex/release-automation \
  --title "ci: automate curated releases" \
  --body "Automate curated numeric releases with Release Please, separate development and formal container tags, establish the initial 0.1.0 changelog, and document the maintainer SOP."
```

Expected: GitHub returns the new pull request URL and required CI begins.

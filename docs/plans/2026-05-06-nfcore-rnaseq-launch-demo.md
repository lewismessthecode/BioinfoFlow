# nf-core/rnaseq Launch Demo Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a canonical nf-core/rnaseq onboarding demo and issue-triage artifacts suitable for a public launch checklist.

**Architecture:** The demo should live under `demo/nfcore-rnaseq/` and use the real upstream `nf-core/rnaseq` pipeline pinned to a stable release with the official `test,docker` profile. Repo-level documentation should point new users from README to the demo and to a canonical `docs/architecture.md` entrypoint. Lightweight tests should verify the demo files, commands, docs links, and issue triage templates stay present.

**Tech Stack:** Markdown docs, POSIX shell scripts, Nextflow/nf-core, Docker, pytest file/content checks.

### Task 1: Add Demo Contract Tests

**Files:**
- Create: `backend/tests/test_docs/test_launch_readiness.py`

**Step 1: Write failing tests**

Add tests that assert:
- `demo/nfcore-rnaseq/README.md`, `run-direct.sh`, `params.test-docker.json`, and `VERIFIED.md` exist.
- `run-direct.sh` uses `nf-core/rnaseq`, `-r 3.24.0`, `-profile test,docker`, and `--outdir`.
- README links to `demo/nfcore-rnaseq/README.md` and `docs/architecture.md`.
- `.github/ISSUE_TEMPLATE/config.yml` and at least 5 launch issue seed files exist.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_docs/test_launch_readiness.py -q`

Expected: FAIL because the files do not exist yet.

### Task 2: Create Canonical Demo Files

**Files:**
- Create: `demo/nfcore-rnaseq/README.md`
- Create: `demo/nfcore-rnaseq/run-direct.sh`
- Create: `demo/nfcore-rnaseq/params.test-docker.json`
- Create: `demo/nfcore-rnaseq/nextflow.test-docker.config`
- Create: `demo/nfcore-rnaseq/VERIFIED.md`

**Steps:**
- Document the direct Nextflow path and the Bioinfoflow path.
- Use official nf-core test data/profile rather than committing large FASTQ files.
- Make `run-direct.sh` fail fast, resolve paths from its own directory, and write outputs under `demo/nfcore-rnaseq/runs/direct-test-docker/`.
- Keep verification status honest: include an unverified template plus commands to fill it in.

**Verification:**
- Run the launch readiness test until it passes.
- Run `bash -n demo/nfcore-rnaseq/run-direct.sh`.

### Task 3: Add README and Architecture Entrypoint

**Files:**
- Modify: `README.md`
- Create: `docs/architecture.md`

**Steps:**
- Add a short “Canonical Demo” section to README after Quick Start.
- Link README docs list to `docs/architecture.md`.
- Make `docs/architecture.md` a concise public-facing wrapper that points to `docs/reference/architecture.md` and summarizes the agent runtime.

**Verification:**
- Run launch readiness tests.

### Task 4: Add Issue Triage Seeds

**Files:**
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUES/launch-01-validate-nfcore-rnaseq-linux.md`
- Create: `.github/ISSUES/launch-02-validate-nfcore-rnaseq-apple-silicon.md`
- Create: `.github/ISSUES/launch-03-apptainer-singularity-docs.md`
- Create: `.github/ISSUES/launch-04-nfcore-schema-advanced-params.md`
- Create: `.github/ISSUES/launch-05-nextflow-cache-resume-metadata.md`
- Create: `.github/ISSUES/launch-06-docker-pull-troubleshooting.md`
- Create: `.github/ISSUES/launch-07-completed-run-screenshots.md`

**Steps:**
- Seed 7 scoped issue drafts with labels and acceptance criteria.
- Keep them as importable local markdown even if GitHub issue creation cannot run from the local environment.

**Verification:**
- Run launch readiness tests.
- If `gh` is authenticated, create GitHub issues from the seed files.

### Task 5: Final Verification

**Commands:**
- `cd backend && uv run pytest tests/test_docs/test_launch_readiness.py -q`
- `bash -n demo/nfcore-rnaseq/run-direct.sh`
- `cd backend && uv run ruff check tests/test_docs/test_launch_readiness.py`
- Optionally: `demo/nfcore-rnaseq/run-direct.sh` on a fresh machine with Docker and Nextflow.

**Expected:** Static checks pass. Direct demo may be marked unverified locally unless it is actually run end-to-end.

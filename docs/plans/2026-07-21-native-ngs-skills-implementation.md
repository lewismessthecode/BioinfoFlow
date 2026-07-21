# Native NGS Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle the complete OpenAI NGS skill suite as native Bioinfoflow skills seeded once by the public curl installer.

**Architecture:** Store reviewed native skills under `bundled-skills/`, with `ngs-runtime-env` owning shared executable resources. Package that tree as a checksummed release archive, stage it transactionally during first installation, and mount only runtime subdirectories from the unified `~/.bioinfoflow` home.

**Tech Stack:** POSIX shell, Docker Compose, GitHub Actions, Python/FastAPI skill registry, pytest, Ruff.

---

### Task 1: Add the native NGS skill source tree

**Files:**
- Create: `bundled-skills/<skill-name>/...`
- Create: `bundled-skills/ngs-runtime-env/SOURCE.md`
- Test: `bundled-skills/ngs-runtime-env/tests/`

- [ ] Copy each upstream `skills/<name>` directory to a direct child of `bundled-skills/`.
- [ ] Move plugin-wide `scripts/`, `workflows/`, `references/`, `assets/`, and tests under `bundled-skills/ngs-runtime-env/`.
- [ ] Rewrite `plugins/ngs-analysis/...` command examples to `$BIOINFOFLOW_SKILLS_ROOT/ngs-runtime-env/...`.
- [ ] Add local-versus-remote execution guidance and upstream attribution.
- [ ] Run `rg -n 'plugins/ngs-analysis|\.codex-plugin' bundled-skills` and expect no matches.
- [ ] Run the copied pytest suite and fix path assumptions without changing analysis behavior.

### Task 2: Make skill resource locations explicit

**Files:**
- Modify: `backend/app/services/agent_core/context/assembler.py`
- Modify: `backend/app/services/agent_core/tools/skills/resources.py`
- Test: `backend/tests/test_agent_core/test_skills_plugins.py`
- Test: `backend/tests/test_agent_core/test_context_compaction.py`

- [ ] Add failing assertions that loaded and active skills expose their absolute skill directory.
- [ ] Render `Skill directory: <path>` before an active skill body and retain the existing API payload paths.
- [ ] Run the focused AgentCore skill tests and expect them to pass.

### Task 3: Adopt the unified localhost home and isolated mounts

**Files:**
- Modify: `scripts/install.sh`
- Modify: `docker-compose.local.yml`
- Modify: `scripts/tests/fixtures/local.env`
- Test: `scripts/tests/install-test.sh`
- Modify: `RUNBOOK.md`

- [ ] Change the managed data root from `~/.bioinfoflow/data` to `~/.bioinfoflow` while retaining `install/` as control state.
- [ ] Create and permission `skills`, `state`, `projects`, and `sources` explicitly.
- [ ] Mount those runtime directories individually and keep `install/` outside both containers.
- [ ] Update uninstall and purge markers so uninstall preserves the unified home and purge removes only a marked home.
- [ ] Update installer tests and run `sh scripts/tests/install-test.sh`.

### Task 4: Seed the skills archive only on first install

**Files:**
- Modify: `scripts/install.sh`
- Test: `scripts/tests/install-test.sh`

- [ ] Extend the fake release server to provide `bioinfoflow-skills.tar.gz` and its checksum.
- [ ] Add tests proving a fresh install seeds skills, update preserves modified files, a pre-existing skills directory is preserved, and failed health checks leave no staged skills.
- [ ] Download and verify the archive with the other version-matched assets.
- [ ] Validate archive paths and required `SKILL.md` files before extraction.
- [ ] Stage skills under `install/`, move them into place before Compose starts,
  and remove only that newly seeded directory if the fresh installation fails.
- [ ] Re-run installer shell tests.

### Task 5: Package and publish the skills release asset

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `backend/tests/scripts/test_release_automation.py`

- [ ] Add failing release-contract assertions for the archive, checksum, smoke copy, and GitHub upload.
- [ ] Build a deterministic `bioinfoflow-skills.tar.gz` from `bundled-skills/`.
- [ ] Include the archive in `SHA256SUMS`, artifacts, smoke-test serving, and release upload.
- [ ] Assert smoke installation contains representative NGS skills and that update preservation works.
- [ ] Run `uv run pytest tests/scripts/test_release_automation.py` from `backend/`.

### Task 6: Complete cross-layer verification

**Files:**
- Modify as required by failures in the files above.

- [ ] Run `sh -n scripts/install.sh scripts/tests/install-test.sh`.
- [ ] Run `shellcheck -e SC2317 scripts/install.sh scripts/tests/install-test.sh` when available.
- [ ] Run `sh scripts/tests/install-test.sh`.
- [ ] Render `docker-compose.local.yml` with the test environment and verify no mount targets `~/.bioinfoflow/install`.
- [ ] Run focused native NGS tests.
- [ ] Run `uv run pytest` and `uv run ruff check .` from `backend/`.
- [ ] Run `git diff --check` and inspect the final diff for private BGI/Phoenix content.

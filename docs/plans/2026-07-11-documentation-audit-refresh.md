# Documentation Audit Refresh Implementation Plan

> **For agentic workers:** Audit tasks may run in parallel when they only inspect files. The primary agent owns all edits, integration, verification, and publication.

**Goal:** Update all current Bioinfoflow documentation that is demonstrably stale, incomplete, duplicated, inconsistent, or incorrectly linked.

**Architecture:** Divide evidence gathering into independent product domains, synthesize findings into a single documentation inventory, then edit canonical pages from highest-impact user guidance outward. Historical plans remain read-only.

**Tech Stack:** Markdown, FastAPI, Typer, SQLAlchemy, Docker Compose, Next.js, Better Auth, Nextflow, MiniWDL, GitHub Actions.

---

### Task 1: Build the documentation inventory

**Inspect:** root Markdown files, current `docs/` pages, demo README files, `backend/README.md`, and `codemaps/`.

- [ ] Classify each document by audience and current/historical status.
- [ ] Identify canonical pages, duplicate coverage, and broken internal links.
- [ ] Record files intentionally excluded from editing.

### Task 2: Audit setup, configuration, auth, and operations

**Evidence:** `.env.example`, Compose files, configuration loaders, auth code, deployment configuration, and operational tests.

- [ ] Verify prerequisites, startup commands, ports, URLs, environment precedence, auth modes, and deployment warnings.
- [ ] Compare `README.md`, `README.zh-CN.md`, `RUNBOOK.md`, Docker quick start, security, storage, and operations pages.

### Task 3: Audit CLI, API, workflows, scheduler, and demos

**Evidence:** CLI registration and help, API routers, services, runtime and scheduler code, tests, workflow definitions, and demo assets.

- [ ] Verify documented CLI commands and target-selection behavior.
- [ ] Verify workflow engines, run lifecycle, scheduler behavior, storage paths, and demo instructions.
- [ ] Update only demonstrably affected reference, workflow, and demo pages.

### Task 4: Audit frontend, AgentCore, remote access, and developer documentation

**Evidence:** protected frontend routes, locale messages, AgentCore tools and configuration, SSH services, architecture code, and CI workflows.

- [ ] Verify user-facing navigation, settings, provider, terminal, AgentCore, and remote-connection claims.
- [ ] Verify architecture, CI/CD, backend README, and codemap descriptions against current implementation.

### Task 5: Integrate documentation changes

- [ ] Preserve established terminology and directory structure.
- [ ] Align equivalent English and Chinese README content.
- [ ] Replace unnecessary duplication with canonical links.
- [ ] Keep existing `docs/plans/` and `backend/docs/refactor*` files unchanged.

### Task 6: Verify and publish

- [ ] Run internal-link and Markdown checks.
- [ ] Run `rtk git diff --check`.
- [ ] Run CLI help and relevant frontend i18n checks.
- [ ] Run focused tests needed to prove changed implementation claims.
- [ ] Review the complete diff against the approved scope.
- [ ] Fetch and rebase onto `origin/main`, rerun final checks, commit, push, and open a draft PR.

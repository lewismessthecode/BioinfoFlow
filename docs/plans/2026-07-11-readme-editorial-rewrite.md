# README Editorial Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the English and Chinese root READMEs with concise, implementation-grounded technical-editorial introductions that help first-time open-source visitors decide whether to try Bioinfoflow.

**Architecture:** Keep both files structurally parallel while writing each language idiomatically. Move exhaustive operational detail to canonical docs, position Bioinfoflow as a local-first analysis workspace and runtime, call the public assistant “Agent,” and mention workflow engines only as implementation adapters.

**Tech Stack:** Markdown, Docker Compose, FastAPI, Next.js, the `bif` CLI, Bioinfoflow Agent, GitHub pull requests.

---

### Task 1: Rewrite the English README narrative

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the headline and opening narrative**

Use the subtitle “A local-first workspace for running, observing, and understanding bioinformatics analyses.” Follow it with short prose that explains how Bioinfoflow keeps projects, inputs, runs, logs, outputs, terminals, and the Agent together on user-controlled infrastructure. Do not use “Agentic control plane” or define the project through Nextflow/WDL.

- [ ] **Step 2: Replace the flat feature list with four capability domains**

Create sections for project/run workspaces, execution and observability, the approval-aware Agent, and remote/infrastructure access. Mention supported workflow engines only in the execution section.

- [ ] **Step 3: Add reader-fit and architecture sections**

Explain that the project fits developers, researchers, and small teams who operate their own compute and want reproducible, inspectable runs. Add this implementation flow:

```text
Web UI / bif CLI / Agent
        ↓
FastAPI services and persistent state
        ↓
Scheduler and workflow-engine adapters
        ↓
Containers, logs, events, and results on your infrastructure
```

- [ ] **Step 4: Simplify setup and operational detail**

Keep the source-build Docker quick start, required owner credentials, local URLs, a short published-image note, representative CLI commands, and development commands. Replace provider-variable, registry, and deployment matrices with links to `docs/getting-started/docker.md` and `RUNBOOK.md`.

- [ ] **Step 5: Add candid project boundaries**

State that Bioinfoflow is designed for trusted workstations and lab servers, the Docker socket grants host-level power, paths must remain visible consistently to workflow containers, and SSH connections support remote inspection/terminals but do not dispatch workflow runs.

### Task 2: Write the Chinese README independently

**Files:**
- Modify: `README.zh-CN.md`

- [ ] **Step 1: Recreate the English information architecture in Chinese**

Keep the same section order, commands, links, capabilities, and caveats as `README.md`, but write natural Chinese paragraphs rather than translating sentence by sentence.

- [ ] **Step 2: Use composed professional Chinese**

Use “本地优先的生物信息分析工作空间” as the central description. Prefer “分析流程”“运行记录”“结果目录”“远程主机”“流程引擎”“审批” and “本地部署”. Avoid “Agentic”“控制平面”“provider”“endpoint”“owner/admin” in explanatory prose when ordinary Chinese is clearer.

- [ ] **Step 3: Preserve necessary technical names**

Keep Bioinfoflow, Agent, Docker, FastAPI, Next.js, SSH, API, CLI, DAG, Nextflow, WDL, and MiniWDL where they identify actual products, protocols, interfaces, or engines. Use “Agent” consistently and never “AgentCore”.

### Task 3: Verify bilingual parity and trusted claims

**Files:**
- Verify: `README.md`
- Verify: `README.zh-CN.md`

- [ ] **Step 1: Compare section and command parity**

Confirm that both files contain the same quick-start commands, local URLs, architecture flow, capability domains, operational boundaries, document links, and license statement.

- [ ] **Step 2: Scan prohibited or stale positioning**

Run:

```bash
rtk rg -n 'AgentCore|Agentic control plane|your-org/bioinfoflow' README.md README.zh-CN.md
```

Expected: no matches.

- [ ] **Step 3: Validate Markdown links and formatting**

Run the repository's relative Markdown link/anchor checker used in the documentation audit, then:

```bash
rtk git diff --check
```

Expected: all links resolve and `git diff --check` exits 0.

- [ ] **Step 4: Run relevant repository checks**

From `frontend/` run:

```bash
rtk bun run lint:i18n
```

Expected: `PASS: i18n coverage check clean`.

### Task 4: Review and update the existing pull request

**Files:**
- Modify: `docs/plans/2026-07-11-readme-editorial-rewrite.md` only to check completed steps.

- [ ] **Step 1: Review the complete README diff against the design**

Check that the first screen explains the project before listing technology, the Chinese reads as original prose, details link outward instead of sprawling, and all claims are supported by the completed documentation audit.

- [ ] **Step 2: Commit the rewrite**

```bash
rtk git add README.md README.zh-CN.md docs/plans/2026-07-11-readme-editorial-rewrite.md
rtk git commit -m "docs: rewrite bilingual readme narrative"
```

- [ ] **Step 3: Synchronize and publish**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
rtk git push
```

Expected: the existing draft pull request for `codex/documentation-audit-refresh` includes the new commit.

- [ ] **Step 4: Normalize the pull request**

Set the PR title to `docs: audit and refresh repository documentation` and update the body to mention the bilingual editorial rewrite and its verification results.

# Agent-First Onboarding Design

**Date:** 2026-07-20
**Status:** Approved direction and implementation specification

## Objective

Make the first useful Bioinfoflow experience as short and concrete as possible:

```text
install -> open /agent -> connect a model -> click a starter prompt
        -> inspect a real demo -> approve the run -> understand the result
```

The work includes a localhost one-line installer, reliable provider connection,
an idempotently seeded demo project, Agent-first starter actions, and matching
English and Chinese READMEs. It does not add an onboarding wizard.

## Product Principles

1. The product teaches itself by doing real work.
2. Installation success and analysis success are both observable.
3. The first path has one choice at a time and no mandatory advanced settings.
4. Existing platform boundaries remain real: Docker socket access is powerful,
   model providers receive prompts sent to them, and consequential Agent actions
   remain approval-gated.
5. Local personal installation is deliberately narrower than team or public
   deployment.
6. Every README claim must be backed by a verified implementation.

## Considered Approaches

### Documentation and installer wrapper only

This is small but leaves the user at an empty Agent, redirects provider setup to
Settings, and requires manual project and workflow preparation. It improves
discovery without producing the promised first success and is rejected.

### Agent-first localhost experience

This design uses a versioned release installer, localhost-only no-auth runtime,
a compact provider connection dialog, a user-scoped demo bootstrap, and
contextual one-click Agent prompts. It reuses existing platform services and is
the selected approach.

### General onboarding framework

A state machine, tutorial checklist, multiple demos, and a provider diagnostics
center would support more cases but introduce a second product surface. It is
rejected under the first-principles and YAGNI constraints.

## Scope Decomposition

The implementation is divided into four independently testable phases.

1. Provider reliability and compact composer connection.
2. Localhost release installer and runtime contract.
3. Demo bootstrap and Agent-first starter actions.
4. Bilingual README and supporting documentation.

Each phase receives its own verification and commit. Team/public deployment,
remote workflow dispatch, and a generalized onboarding framework are outside
this project.

## First-Run User Flow

### Installation

The primary command is:

```bash
curl -fsSL https://github.com/lewisliu/bioinfoflow/releases/latest/download/install.sh | sh
```

The installer checks prerequisites, creates its control and data directories,
downloads a version-matched Compose definition, pulls pinned images, starts the
services, waits for health, and opens `http://localhost:3000/agent`.

The browser must not show an account form in this localhost mode. The service
must listen only on loopback, and the installer must reject remote Docker
contexts because the backend receives Docker-daemon control.

### Model connection

When no usable model exists, the empty Agent composer displays a quiet
`Connect a model` action. It does not show a full settings panel.

The compact path offers OpenAI, Anthropic, and DeepSeek, followed by
`More providers`. The first three require only the provider selection and API
key. `More providers` navigates to the existing Provider Settings surface for
Kimi, Kimi China, Ollama, vLLM, OpenAI-compatible gateways, and other advanced
templates.

The shared connection operation performs these explicit stages:

1. Save the provider and credential through existing catalog APIs.
2. Discover models.
3. Select a usable discovered model.
4. Probe the provider/model.
5. Refresh Agent model state and focus the composer.

Failure messaging identifies the failed stage. A credential that was saved
before discovery or probe failure remains recoverable and is not described as
an invalid key unless the provider actually rejected authentication.

### Demo activation

On a genuinely fresh workspace, the Agent route calls an idempotent bootstrap
endpoint in the current user context. The endpoint creates or repairs:

- a managed `Bioinfoflow Demo` project;
- one registered and project-bound quickstart WDL workflow;
- a sample sheet and two tiny FASTQ-like input files;
- stable metadata identifying the managed demo assets.

The UI explicitly selects the returned demo project once. Existing users and
remembered project selections are never overwritten.

### Agent action

For the demo project, the empty composer preserves the existing line-based
starter layout and shows at most four short contextual suggestions. Starter
copy must remain comparable in length to the current UI; it must not become a
sentence-length tutorial. The primary suggestion is:

> Check and run the demo workflow

Selecting it attaches the registered workflow context and submits the Agent
turn immediately. It does not submit the workflow directly. The existing
high-impact `runs.submit` policy remains responsible for pausing for approval.

After completion, the Agent can inspect the run, logs, and outputs and explain
the produced report. Non-demo projects keep the existing generic suggestions.

## Provider Reliability

Bioinfoflow already separates Kimi Global and Kimi China:

- Global: `KIMI_API_KEY` and `https://api.moonshot.ai/v1`
- China: `KIMI_CN_API_KEY`, `MOONSHOT_CN_API_KEY`, or legacy
  `MOONSHOT_API_KEY` and `https://api.moonshot.cn/v1`

The implementation preserves that split and adds regression coverage for
endpoint selection, legacy provider reconciliation, model routing, discovery
errors, and recoverable saved credentials.

The composer and Settings must share one provider-connection operation rather
than accumulate divergent request sequences. No new backend aggregation API is
required unless implementation evidence shows that existing APIs cannot
maintain recoverable state.

## Demo Asset Design

The demo must be recognizably biological but operationally tiny. It uses a
purpose-built two- or three-stage WDL under the backend package so release
images contain it. Inputs include two small FASTQ-like files and a sample sheet.
Outputs include a compact machine-readable summary and a human-readable report.

Requirements:

- completes in less than 60 seconds after required images are present;
- uses one small pinned multi-architecture runtime image;
- does not download input data during execution;
- has deterministic outputs suitable for assertions;
- uses paths under the managed project data root and respects identity mounts;
- can be compiled and run through ordinary Bioinfoflow services;
- can be repaired without creating duplicate projects, workflows, or bindings.

The bootstrap runs lazily in user context rather than at FastAPI startup.
Startup has no appropriate owning user, and system-owned projects are not the
desired first-run object.

## Installer Architecture

The installer is a POSIX shell entrypoint distributed with each GitHub release.
It downloads a Compose file and checksum from the same selected release.

### Filesystem contract

```text
~/.bioinfoflow/
├── install/    # installer-owned Compose and configuration
└── data/       # persistent Bioinfoflow platform data
```

`BIOINFOFLOW_HOME` is set to the absolute host path of
`~/.bioinfoflow/data` and mounted at the identical container path. The local
installer never defaults to `/srv/bioinfoflow`.

### Network and security contract

- Frontend and backend bind to `127.0.0.1` only.
- The installer accepts only a running local Unix-socket Docker daemon.
- Localhost mode uses no application login.
- The installer never requests or stores provider API keys.
- Control directories use mode `700`; generated configuration uses mode `600`.
- Public/team deployments continue to use the documented authenticated path.

Because the current public frontend image compiles personal auth into client
configuration, the first implementation publishes an explicit localhost
frontend variant with dev auth compiled in. A broader runtime-config refactor is
not required for this project.

### Image and release contract

Backend and frontend release images must publish both `linux/amd64` and
`linux/arm64`. Installed instances use a versioned tag or digest, never a
floating `latest` reference.

The release contains:

- `install.sh`;
- the localhost Compose file;
- SHA-256 checksums;
- version-matched image references.

### Lifecycle commands

The installer supports initial install, idempotent repair/start, `--dry-run`,
`--version`, `--update`, `--uninstall`, `--purge`, and `--no-open`.

`--uninstall` removes containers and installer control files but preserves
platform data. `--purge` explicitly names and removes only the managed data
root. Failed health checks print Compose status and bounded relevant logs.

## Minimal Composer UI

The implementation follows the existing Agent visual system and the
`minimalist-ui` constraints:

- reuse the current composer typography, spacing, neutral surfaces, and icons;
- one quiet inline action rather than a banner or card wall;
- a small dialog with a maximum 8 px container radius and a light structural
  border;
- no gradients, heavy shadows, large pills, celebratory animation, or new icon
  library;
- no onboarding progress UI;
- all user-facing copy exists in English and Chinese.

The composer placeholder may cycle through short, contextual examples with a
typewriter treatment: type left-to-right, pause, delete quickly right-to-left,
then continue with the next example. This is placeholder-only motion and must
not change layout or reserve additional space. It stops while the composer is
focused, whenever the user has entered text, and under `prefers-reduced-motion`.
Timers are cleaned up on unmount, and assistive technology receives the stable
composer label rather than every animated intermediate string.

A visual review must run in local dev auth mode after implementation.

## README Narrative

Both root READMEs use the same factual structure and differ only in natural
language, not claims or feature scope.

1. Bioinfoflow in one sentence.
2. Product demonstration.
3. A fast suitability check.
4. Verified one-line localhost install.
5. The first successful Agent-guided demo.
6. The Agent's real inspect-plan-act-approve-observe loop.
7. Fit and non-fit boundaries.
8. Data, model, Docker socket, and approval trust boundaries.
9. Source builds, authenticated/team deployments, and development.
10. Documentation, contribution, and license links.

The voice is restrained, technical, specific, and free of unsupported scale or
performance claims. It avoids generic AI marketing language.

## Error Handling

### Installer

Prerequisite, architecture, Docker context, occupied port, download, checksum,
pull, startup, and health failures produce an explicit failing stage and a
recovery command. Partial downloads are atomic and do not replace a known-good
installation.

### Provider connection

Authentication, model discovery, no usable model, probe timeout, endpoint, and
network failures are distinguished. Saved credentials remain visible as
configured when later stages fail.

### Demo bootstrap

The operation is idempotent and transaction-aware. Concurrent requests cannot
create duplicate canonical objects. Missing files or bindings are repaired.
Unexpected user-created objects with similar names are not silently overwritten.

### Agent run

The starter action uses ordinary Agent and scheduler behavior. Approval denial,
workflow failure, and unavailable Docker runtime remain visible in the normal
Agent transcript and run inspection surfaces.

## Verification

### Provider phase

- Backend regression tests for Kimi Global/China routing and recoverable
  discovery/probe failures.
- Frontend tests for compact connect success and each failure stage.
- Settings regression tests proving shared connection behavior.
- Frontend lint, i18n lint, tests, and build.

### Installer phase

- `sh -n`, ShellCheck, and table-driven fake-command tests.
- Rendered Compose assertions for loopback ports, identity mount, local Docker
  socket, no-auth mode, and pinned images.
- CI smoke installs on amd64 and arm64.
- Live manifest inspection before documenting architecture support.

### Demo phase

- API tests for fresh creation, repeated calls, repair, concurrency, workspace
  isolation, and non-destructive existing-user behavior.
- Workflow compilation assertions and deterministic output checks.
- Frontend tests for one-time project selection, contextual prompts, workflow
  attachment, immediate Agent submission, and preserved approval boundary.
- Frontend timer and accessibility tests for the dynamic placeholder, including
  focus, typed-input, unmount, and reduced-motion behavior.
- Docker-enabled smoke run where available.

### Documentation phase

- English/Chinese claim and section parity review.
- Link and command inspection.
- `git diff --check` and Markdown hygiene checks.
- A clean-install walkthrough matching the README exactly.

### Final gate

Run the relevant backend and frontend suites, build the frontend, render the
Compose files, exercise the installer harness, visually inspect the Agent first
run, and request independent parallel reviews. Critical and important findings
must be fixed and re-reviewed before the branch is rebased, pushed, and opened
as a ready pull request.

## Explicit Non-Goals

- Public or team one-line deployment.
- Automatic collection of provider keys in shell.
- Bundling or operating a local language model.
- Multiple onboarding tutorials or a tutorial progress system.
- Remote workflow dispatch over SSH.
- Replacing the existing Provider Settings catalog.
- Claiming full offline operation.

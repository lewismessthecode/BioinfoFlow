# Product Marketing Context

**Document version:** v1
**Last updated:** 2026-07-20

## Product Overview

**One-liner:** Bioinfoflow is a local Agent workspace that can inspect, prepare,
run, and explain Nextflow and WDL analyses on infrastructure you control.

**What it does:** Bioinfoflow brings project files, workflow definitions,
inputs, runs, DAGs, logs, results, terminals, and operational context into one
system. Its Agent works against that real platform state, uses bounded tools,
and pauses for approval before consequential actions.

**Product category:** Local agentic bioinformatics workflow platform.

**Product type:** Self-hosted open-source application.

**Business model:** MIT-licensed open source; no hosted Bioinfoflow account is
required for the local product.

## Target Audience

**Target users:** Bioinformaticians, workflow developers, individual
researchers, and small technical teams operating workstations, lab servers, or
SSH-accessible compute.

**Primary use case:** Run and understand reproducible bioinformatics workflows
without losing the surrounding project and operational context across terminal
sessions and directories.

**Jobs to be done:**

- Decide whether a workflow and its inputs are ready to run.
- Submit, inspect, follow, diagnose, resume, and explain workflow runs.
- Keep files, workflow versions, logs, DAGs, events, and results traceable.
- Let an Agent perform useful platform work without silently crossing important
  operational boundaries.

## Personas

| Persona | Cares about | Challenge | Value we promise |
| --- | --- | --- | --- |
| Bioinformatician | Correct inputs, reproducible runs, interpretable failures | Analysis context is scattered across commands, folders, and logs | One project and run context the user and Agent can inspect together |
| Workflow developer | Engine behavior, containers, retries, portability | Local, container, and server paths behave differently | Explicit runtime, storage, and identity-mount contracts |
| Lab or small-team operator | Data control, recoverability, approvals | Hosted services may not fit data or infrastructure constraints | A self-hosted control plane with explicit security boundaries |

## Problems & Pain Points

**Core problem:** A workflow command is only one fragment of an analysis. The
files, parameters, environment, container images, execution history, logs,
results, and reasoning that make the run understandable are easily separated.

**Where the current workflow can create friction:**

- Terminal-first work can leave analysis context distributed across commands,
  directories, and logs.
- Engine-native state may still need to be connected to project files, notes,
  and operational decisions.
- A general-purpose chat only knows the project state supplied to it.
- Some hosted deployment models do not match teams that need to keep platform
  state and research data on infrastructure they control.

**What it costs:** Repeated setup, slow failure diagnosis, uncertain resume and
retry decisions, and analyses that are difficult to revisit or hand over.

**Emotional tension:** Users should not have to wonder whether the Agent saw the
right files, whether a retry will repeat expensive work, or where a result came
from.

## Comparison Frame

Do not make blanket feature claims about another product without a dated,
verifiable comparison. Compare Bioinfoflow on observable dimensions instead:

- Where platform state and research data run.
- Whether workflow, project, file, and run context share one model.
- Which Agent actions are available and where approval is required.
- Which engines, remote connections, and deployment modes are supported.
- What installation, authentication, and operational work the user owns.

## Differentiation

**Key differentiators:**

- The Agent shares Bioinfoflow's project, workflow, run, scheduler, file, image,
  skill, and selected remote context.
- Agent actions use explicit permissions, risk assessment, and approval gates.
- Nextflow and WDL operate behind one project and run model.
- Local-first describes ownership and control while still allowing deliberate
  remote connections and hosted or local models.
- A fresh local install contains a real demo project, workflow, and input data.

**How we do it differently:** The Agent does not merely suggest commands. It
inspects evidence, prepares work, calls platform tools, requests approval, and
can inspect or follow the resulting run.

**Why that's better:** The conversation and the execution refer to the same
durable state, so actions are inspectable and results remain connected to their
inputs and history.

## Objections

| Objection | Response |
| --- | --- |
| This looks difficult to install | The current path builds from source. The first tagged release containing the installer will add a loopback-only path using versioned images and a seeded demo. |
| I do not want research data uploaded to another service | Bioinfoflow runs on user-controlled infrastructure. A hosted model receives only the context sent to that provider; local compatible models are also supported. |
| I do not trust an Agent with workflow execution | Read work and consequential actions have explicit policy boundaries; run submission remains approval-gated. |
| I only need a workflow engine | Users satisfied with raw Nextflow or MiniWDL and filesystem conventions may not need Bioinfoflow. |

**Anti-persona:** Teams seeking a fully managed hosted analysis service,
zero-administration multi-tenant deployment, or an Agent allowed to execute
unrestricted infrastructure changes without review.

## Switching Dynamics

**Push:** Scattered context, opaque failures, repeated setup, manual monitoring,
and generic Agents that cannot see real workflow state.

**Pull:** One inspectable workspace and an Agent that can move from diagnosis to
approved action.

**Habit:** Existing shell scripts, directory conventions, engine-native CLIs,
and reluctance to add another platform.

**Anxiety:** Docker socket access, installation complexity, model keys, data
exposure, path behavior, and whether Agent actions are controllable.

## Messaging Hypotheses

The following lines are draft messaging hypotheses, not sourced customer quotes.
Validate them through interviews, issues, support conversations, or other
research before presenting them as customer language:

- "The run failed, but the log does not tell me what I should fix."
- "The samples, config, work directory, and results are all in different places."
- "Can I resume this safely, or will it repeat everything?"
- "I want the Agent to inspect the real project, not guess from pasted text."

**Words to use:** inspect, prepare, run, explain, project context, workflow,
inputs, approval, traceable, self-hosted, infrastructure you control.

**Words to avoid:** seamless, revolutionary, next-generation, unleash,
AI-powered platform, effortless at any scale, fully autonomous.

**Glossary:**

| Term | Meaning |
| --- | --- |
| Agent | Bioinfoflow's tool-using analysis worker operating within selected project and permission context |
| Project | Durable boundary for files, workflows, runs, and analysis context |
| Run | One scheduled workflow execution with inputs, events, logs, DAG, audit trail, and results |
| Local-first | Platform state and research data remain under user control; it does not mean every model or compute host must be local |

## Brand Voice

**Tone:** Restrained, technical, candid.

**Style:** Lead with concrete user situations and observable behavior. Prefer
short sentences, specific nouns, and truthful boundaries over slogans.

**Personality:** Capable, calm, rigorous, practical, respectful of user control.

## Proof Points

**Metrics:** Do not publish adoption, performance, or scale metrics without
current verifiable evidence.

**Value themes:**

| Theme | Proof |
| --- | --- |
| Agent that works | Registered tools cover platform files, workflows, runs, images, scheduling, and bounded remote operations |
| Human control | Consequential actions produce approval decisions rather than bypassing policy |
| Traceability | Runs persist inputs, events, DAGs, logs, audit records, and results |
| Low-friction trial | The implemented release path includes a loopback-only installer, UI provider connection, and seeded deterministic demo; describe it as available only after the first tagged release publishes its assets |

## Goals

**Business goal:** Turn qualified repository visitors into successful local
users, then into repeat users, issue reporters, and contributors.

**Conversion action:** Install Bioinfoflow, connect a model, and run the seeded
demo through the Agent.

**Current metrics:** Not established. Track discovery source, installer starts,
successful health checks, demo bootstrap, first Agent turn, first approved run,
and returning usage separately.

## Changelog

- v1 (2026-07-20) — Initial Agent-first positioning and first-run conversion context.

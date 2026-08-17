# DeepSeek Sandbox Adoption

Date: 2026-08-18
Status: implemented and verified
Upstream: `deepseek-ai/deepseek-harness` tag `dsh-v0.1.0-rc.7`, commit
`99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`

## Outcome

Replace BioinfoFlow's home-grown local Bubblewrap and Seatbelt profile builders
with the published DeepSeek Harness sandbox packages. Keep BioinfoFlow's agent
harness, approval workflow, process supervision, remote SSH execution, and file
I/O hardening. The supported security promise becomes explicit:

- local agent processes may read anything readable by their execution identity
  except control-plane capability paths such as state/auth and request files,
  process metadata such as `/proc`, and credential configuration paths;
- confined modes protect filesystem integrity by restricting writes;
- network and process visibility are not sandbox properties;
- an approved `danger-full-access` call is a one-shot capability, never a
  session-wide or sticky mode;
- unavailable or broken confinement fails closed;
- ambient Docker and BioinfoFlow control-plane authority must not be reachable
  from ordinary agent Bash.

The DeepSeek packages remain upstream dependencies. BioinfoFlow will not vendor,
fork, submodule, or translate their platform profiles into Python. Native/source
execution keeps Python process supervision around a persistent Node confinement
worker. Compose execution adds a disposable container identity because the
long-lived backend must retain Docker authority for workflow scheduling.

## First-principles invariants

1. A policy is real only when the operating system enforces it. Command-string
   classification is approval UX and audit data, not a security boundary.
2. `read_only` means a process cannot write the workspace even if a classifier
   incorrectly calls its command read-only.
3. `workspace-write` grants writes to exactly one canonical workspace root and
   the backend-defined temporary area. Host-readable paths remain readable.
4. `danger-full-access` is wider than both confined modes and is valid for one
   exact approved tool call only.
5. A sandbox provider crash, malformed response, partial enforcement, launcher
   failure, or inability to hide ambient privileged endpoints stops execution.
6. Docker socket access is equivalent to host write authority. A read-only bind
   of the socket is not protection because a Unix socket can still be used.
7. Secrets and control-plane credentials are capabilities, not ordinary ambient
   environment. They remain scrubbed and are exposed only by structured paths.
8. The remote SSH sandbox is a separate trust domain and remains unchanged.

## Current-to-target layer map

| Concern | Current | Target |
| --- | --- | --- |
| Public session policy | `permission_mode` plus `workspace_access` | unchanged public contract |
| Local sandbox profiles | Python `BubblewrapAdapter` / `SeatbeltAdapter` | DeepSeek `LocalSandboxProvider` |
| Cross-language seam | none | versioned JSON-lines stdio worker protocol |
| Process spawn/cancel/output | Python asyncio | retained in Python |
| Direct reads | workspace/skill roots only | host-readable canonical paths except control-plane capability roots |
| Direct writes/edits | workspace roots with fd-relative hardening | retained |
| Remote SSH | BioinfoFlow remote Bubblewrap | retained unchanged |
| Escalation | inferred risk approval only | structured, one-shot `require_escalated` |
| Docker authority | socket ambient in backend container and Agent Bash | backend retains socket; Agent Bash runs in a disposable socket-free container |

## Runtime modes

The existing database and API values are mapped at the tool boundary:

| BioinfoFlow state | Effective DeepSeek mode |
| --- | --- |
| `workspace_access=read_only` | `read-only` |
| `workspace_access=read_write` | `workspace-write` |
| approved local Bash with `sandbox_permissions=require_escalated` | `danger-full-access` for that call |

`permission_mode=full_access` continues to mean no soft confirmation for normal
tool effects. It does not silently disable the OS sandbox. An escalated call
always needs an explicit confirmation, including under `full_access`.

Remote SSH rejects `require_escalated`; it never bypasses the remote sandbox.

## Worker protocol and lifecycle

Add `backend/sandbox_worker/` as a standalone Node ESM package with a committed
lockfile and exact direct versions:

- `@deepseek-ai/dsh-sandbox@0.1.0-rc.7`
- `@deepseek-ai/dsh-sandbox-local@0.1.0-rc.7`
- `@deepseek-ai/cordis@4.0.1`
- same-release DeepSeek peer packages required by npm resolution

For native/source execution, the Python backend starts one lazy persistent
worker. Requests and responses are one JSON object per line and are serialized
until the protocol proves safe for concurrency.

Request v1:

```json
{
  "version": 1,
  "id": "opaque-request-id",
  "method": "confine",
  "argv": ["/bin/bash", "--noprofile", "--norc", "-c", "..."],
  "mode": "read-only",
  "workspace_root": "/canonical/existing/root",
  "protected_endpoints": ["/var/run/docker.sock"]
}
```

Successful response v1 returns the exact wrapped argv plus `enforcement`,
`denial_signatures`, and `runner_failure_rules`. Errors return a stable code and
message. Unknown versions, IDs, fields, modes, or malformed JSON are rejected.

The worker owns the Cordis context and provider lifetime; Python continues to
own spawn, cwd, sanitized environment, timeout, cancellation, process-group
termination, redaction, output bounds, and artifact capture. EOF, timeout,
unexpected ID, invalid schema, or worker exit invalidates the client and fails
the call closed. A later call may start a fresh worker, but the failed call is
never retried automatically.

`danger-full-access` is resolved in Python and bypasses `confine()` exactly as
the upstream Bash consumer does. It still uses the same sanitized environment,
supervision, and output handling.

For Compose execution, `AGENT_SANDBOX_IMAGE` selects the exact backend image for
a one-shot execution protocol. Python writes a mode, argv, environment, inode,
timeout, and output-limit request beneath the identity-mounted BioinfoFlow state
root. The backend then asks Docker to run `/app/sandbox_worker/executor.mjs` in
a disposable container. That executor initializes the same pinned DeepSeek
provider, supervises the command inside the child container, and emits one JSON
result. Python retains result classification, redaction, artifact handling,
approval semantics, cancellation, and audit output.

## Docker authority boundary

DeepSeek's local sandbox constrains writes; it is not a container or daemon
capability boundary. Bubblewrap can hide an already-mounted socket, but Docker
Desktop commonly makes the provider select Landlock, which cannot hide an
existing Unix socket. Therefore same-container masking is insufficient as the
production design.

Compose keeps the writable Docker socket only in the long-lived backend. Every
Agent Bash call runs in a fresh sibling container with:

- the exact matching backend image;
- no Docker socket or Docker configuration mount;
- explicit project/source/skill roots read-only, the canonical workspace
  overlaid read-write, and the call's own request file, with no control-plane
  state, concurrent request directory, or arbitrary host-path binds;
- fail-closed validation that rejects `/` or any workspace/read root containing,
  or contained by, a control-plane or external-write capability path;
- a read-only container root and bounded `/tmp` tmpfs;
- all Linux capabilities dropped and `no-new-privileges`;
- Docker's default seccomp/AppArmor policy plus dropped capabilities and
  `no-new-privileges`; the provider must select a fully enforcing adapter under
  those constraints or fail closed;
- the backend network namespace when needed so an existing loopback-scoped
  `bif` API URL remains reachable.

The request file is always removed, the child container is killed on timeout or
cancellation, and the child is removed after every result. Any image mismatch,
container failure, malformed response, partial provider enforcement, or cleanup
failure without a prior execution error fails the call closed. An approved
`danger-full-access` bypasses the DeepSeek write profile and receives a writable
ephemeral image root, so it is strictly wider than `workspace-write`; it still
runs in the same socket-free identity and gains no additional persistent mount.

Native macOS/Linux development does not normally mount the Docker socket into
the backend process. The compatibility layer conceals BioinfoFlow state/auth and
request roots because readable tokens are write capabilities, rejects partial
providers, and scrubs Docker endpoint environment variables. An upstream runner
that cannot conceal an existing protected capability path fails closed.
Provider-specific socket masking remains defense in depth where the upstream
adapter can express it, not the Compose integrity boundary.

## Turn loop and tool model

The agent turn loop, batching, durable interactions, and recovery remain
unchanged. Bash gains two structured fields:

```text
sandbox_permissions: use_default | require_escalated
justification: non-empty text required for require_escalated
```

The approval fingerprint covers the normalized command, canonical cwd and cwd
identity, requested mode, and justification. Approval is valid only for the
same call. A denial, cancellation, process crash, recovered turn, changed cwd,
changed command, changed mode, or changed justification cannot reuse it.

Write and edit tools do not gain escalation in this change. Their write boundary
remains the workspace root.

## Context and memory

AGENTS/CLAUDE discovery may continue walking toward the project root. Because
host reads are intentional, prompt discovery and execution no longer have
different read boundaries. Workspace root remains the immutable write boundary.

No new durable sandbox state is stored. The effective mode and worker/provider
facts are recorded in tool output/audit data, while approval interactions remain
the durable record for escalation.

## Delegation and orchestration

Child agents inherit the session's workspace access but do not inherit an
approved escalated call. Each escalation is independently structured and
approved. Routed remote environments retain their existing scope and cannot use
the local escalation field to bypass remote confinement.

## Extension and maintenance model

BioinfoFlow owns only:

- the JSON protocol;
- lifecycle/fail-closed Python client;
- the disposable-container Docker-capability boundary and its one-shot protocol;
- policy mapping and approval integration;
- packaging and compatibility tests.

Upstream owns provider selection, probes, platform write profiles, denial
signatures, and runner-failure rules. Upgrades are explicit dependency PRs:

1. change exact versions and regenerate the lockfile;
2. review upstream changelog and the pinned source diff;
3. run protocol, mode, socket, platform, backend, and image tests;
4. update the pinned tag/commit in this document.

No automated dependency update may merge without these compatibility tests.

## Safety and observability

Every local Bash result records effective mode, enforcement, and provider facts.
Runner failure is classified before sandbox denial using upstream's structured
rules. Messages distinguish unavailable confinement, denied filesystem effect,
ordinary command failure, timeout, cancellation, and output-limit termination.

The product documentation must not claim network isolation. `allow_network` is
removed from the local sandbox contract; scoped `bif` token injection remains a
separate structured capability path pending a dedicated `bif` tool.

## TDD and verification

Implement vertical slices in this order:

1. Worker protocol: valid confine, invalid request, mismatched ID, crash/EOF and
   timeout fail closed.
2. Modes: real or representative tests prove read-only denies workspace writes,
   workspace-write allows workspace writes, and external host reads succeed.
3. Direct file semantics: external read succeeds; external write/edit and
   symlink races remain denied.
4. Escalation: schema, mandatory justification, forced confirmation, exact
   fingerprint, one-shot widening, next-call confinement, and remote rejection.
5. Docker capability: Compose uses the matching backend image, mounts no socket
   into Agent execution, and fails closed on incapable/partial runners.
6. Integration: cancellation, timeout, output cap, redaction, artifacts, cwd
   binding, routed local/remote execution, durable interaction recovery.
7. Packaging: Node version, exact package pins, frozen install, backend image
   smoke, and CI installation.

Before merge run:

```text
backend/sandbox_worker npm test
backend/sandbox_worker npm ci
backend ruff check
backend full pytest
backend Docker build
nested disposable-container smoke with an outer Docker socket
git diff --check
```

After rebasing onto the latest `origin/main`, repeat the broad backend checks and
perform two independent reviews against `origin/main`: repository standards and
this specification. Fix all material findings before PR merge.

## Rollout and rollback

This is a direct replacement, not a dual-stack runtime flag. A hidden fail-open
or legacy fallback would weaken the invariant and complicate support. Rollout is
gated by platform smoke tests and the backend image test.

Rollback means reverting the adoption commit and restoring the previous pinned
release, never silently selecting the legacy implementation at runtime. Worker
startup and confinement failures remain visible and fail closed throughout.

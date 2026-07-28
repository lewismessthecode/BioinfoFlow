# Agent Docker Access and Image Registry Resolution Design

## Summary

BioinfoFlow will make container-image resolution explicit and predictable:

- a workflow image reference is used exactly as written unless the workflow or
  project has an explicitly selected registry;
- the platform-wide default registry concept is removed;
- an explicitly selected workflow registry continues to rewrite unqualified
  static image references in the run-local workflow copy;
- Agent Bash receives the configured Docker socket and can use the Docker CLI
  directly, with the same broad Docker authority as any socket client;
- Linux sandbox failures report whether Bubblewrap is missing or present but
  blocked by the container or kernel.

No `images.pull` Agent tool and no per-run `image_source` abstraction will be
added.

## Problem Statement

The current registry fallback can transform a portable WDL declaration such as:

```wdl
docker: "ubuntu:22.04"
```

into:

```text
10.227.4.56:80/pipeline-dev/ubuntu:22.04
```

without the workflow author or run submitter selecting that source. The chain
is `RunCompiler._resolve_workflow_image_registry()` ->
`ContainerRegistryService.get_effective_registry()` -> global default registry
-> `resolve_container_image_reference()` -> Docker SDK pull. The Agent does not
construct that qualified reference.

Separately, Agent Bash runs inside the backend container under Bubblewrap. The
backend container has the host Docker socket, but the Agent filesystem boundary
currently masks it. This prevents the Agent from using ordinary Docker CLI
commands even when the user intentionally grants full Agent access.

On Linux, Bubblewrap availability collapses binary absence, namespace denial,
probe timeout, and other probe failures into the same generic error. In Docker,
the common failure is that the runtime security policy blocks the unprivileged
user namespace required by Bubblewrap.

## Design Principles

1. The image reference is the source of truth.
2. Only an explicit scoped choice may rewrite an unqualified reference.
3. Original workflow source remains portable and immutable.
4. Generated runtime files may contain deployment-specific resolved references.
5. Docker socket access is full Docker authority; the product must not describe
   it as pull-only confinement.
6. Diagnostics must preserve the first concrete failing condition.

## Registry Resolution

### Remove the global default

Remove `ContainerRegistry.is_default` from the model, API schemas, frontend,
database constraints, documentation, and tests. Add an Alembic migration that
removes the column and its uniqueness/index machinery.

Container registries become named endpoint and credential records. Merely
creating a registry must never affect workflow registration or execution.

### Resolution precedence

For each static workflow image:

1. If the image already contains a registry host, keep it unchanged.
2. Otherwise, if the workflow has `container_registry_id`, resolve through that
   registry.
3. Otherwise, if the project has an explicit `container_registry_id`, resolve
   through that registry.
4. Otherwise, keep the original unqualified reference and let Docker apply its
   normal semantics, such as Docker Hub for `ubuntu:22.04`.

There is no platform-wide fallback.

### Explicit workflow registry binding

The workflow registration UI continues to allow selecting a registry. That
selection is an explicit deployment binding.

For an unqualified static image and selected registry:

- registration prefetch pulls the qualified registry reference;
- the stored original WDL remains unchanged;
- run compilation creates a run-local WDL copy with the static literal rewritten
  to the same qualified reference;
- MiniWDL therefore uses the exact tag that registration prefetched.

The platform must not retag the private image as the unqualified source name.
Retagging would create local-name collisions and hide which registry supplied
the bytes.

Dynamic WDL container expressions remain untouched because their value is not
known at compile time.

### Credentials for explicit image hosts

When a workflow already contains a qualified image such as
`10.227.4.56:80/pipeline-dev/tool:1.0`, keep the reference unchanged and look up
a configured registry with the matching normalized endpoint solely to obtain
credentials. Credential lookup must not rewrite the name or namespace.

## Agent Docker Access

Agent Bash will receive the configured Docker socket as a read-write sandbox
capability when that socket exists. The socket is removed from permanent
protected roots and included in the local execution boundary passed to
Bubblewrap or Seatbelt.

This deliberately grants full Docker daemon authority, including pull, build,
run, stop, delete, volume, network, and host bind-mount operations. The existing
Agent approval policy still decides whether a shell action may execute, but the
shell command classifier is not treated as a security boundary around Docker.

The Agent can therefore perform the same direct operation a local coding agent
would use:

```bash
docker pull ubuntu:22.04
```

No Docker-specific Agent tool is added. The existing `bash` tool remains the
single shell surface.

## Linux Sandbox Availability

Replace the boolean-only adapter availability result with a small diagnostic
result containing:

- adapter name;
- executable path when found;
- availability;
- failure category such as `binary_missing`, `probe_exit`, `probe_timeout`, or
  `probe_os_error`;
- a bounded, sanitized failure message.

The existing short-lived availability cache remains. `SandboxRunner` includes
the concrete Linux reason in `SandboxUnavailableError`, and startup logging
reports the selected adapter or failure category without exposing secrets.

Official Compose files continue to provide the runtime setting required by
Bubblewrap. Tests must verify that every distributed Compose variant carries the
same requirement and does not make the backend privileged or add `SYS_ADMIN`.

## Agent Harness Behaviour

The existing general failure-recovery rules remain sufficient once hidden image
rewriting is removed and Docker is available through Bash. Add only narrow
platform guidance:

- use the exact workflow image reference unless an explicit workflow or project
  registry binding is observed;
- use Bash for direct Docker inspection and pulls when needed;
- do not replace a workflow image with an unrelated locally available image;
- after a pull or rerun, verify the command result or run terminal state.

Do not add registry-name heuristics, automatic mirror guessing, or image-name
allowlists.

## Data Flow Examples

### No selected registry

```text
WDL: ubuntu:22.04
Resolved image: ubuntu:22.04
Docker SDK/CLI semantics: docker pull ubuntu:22.04
Run-local WDL: unchanged
```

### Workflow explicitly selects the internal registry

```text
WDL: ubuntu:22.04
Workflow registry: 10.227.4.56:80, namespace pipeline-dev
Resolved image: 10.227.4.56:80/pipeline-dev/ubuntu:22.04
Registration prefetch: pull the resolved image
Run-local WDL: rewritten to the resolved image
Stored source WDL: unchanged
```

### Workflow contains an explicit private image

```text
WDL: 10.227.4.56:80/pipeline-dev/tool:1.0
Resolved image: unchanged
Credentials: matched by endpoint when configured
Run-local WDL: unchanged
```

## Testing Strategy

Use TDD for each behaviour change.

Backend tests must prove:

- a registry record marked default in pre-migration data no longer influences
  unqualified workflow images after migration;
- no workflow/project registry preserves `ubuntu:22.04` and Docker receives
  repository `ubuntu`, tag `22.04`;
- an explicit workflow registry qualifies the image and rewrites only the
  run-local WDL;
- an explicit project registry remains a scoped fallback;
- an already qualified image is unchanged and receives matching configured
  credentials;
- the Agent sandbox exposes the configured Docker socket read-write;
- Bubblewrap diagnostics distinguish missing binary from a failed namespace
  probe;
- all Compose variants retain the required Bubblewrap runtime configuration.

Frontend tests must prove:

- registry create/edit forms no longer expose a default toggle;
- registry lists no longer display default badges or actions;
- workflow registration still supports explicit registry selection;
- English and Chinese locale files remain synchronized.

Run focused tests during development, then run the full backend and frontend
verification required by `AGENTS.md`.

## Migration and Compatibility

Existing workflow and project `container_registry_id` values remain valid and
keep their explicit scoped behaviour. Existing registry credentials remain
valid. Only the global `is_default` state is removed.

Deployments using older Compose assets must update the Compose file and recreate
the backend container so Bubblewrap receives the required runtime policy.

## Non-Goals

- Per-run image-source overrides.
- A dedicated `images.pull` Agent tool.
- Restricting Docker socket access to selected Docker subcommands.
- Automatic discovery of equivalent images in other registries.
- Mutating original workflow source during registration or execution.
- Configuring the host Docker daemon's registry mirror settings.

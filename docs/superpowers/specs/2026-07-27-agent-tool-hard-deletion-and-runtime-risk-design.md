# Agent Tool Hard Deletion and Runtime Risk Design

## Problem

The recent Agent tool-surface simplification changed the model-visible surface,
but it stopped short of deleting the retired implementations and compatibility
paths. The runtime therefore has two competing truths: the model sees the new
surface, while the registry, providers, exports, tests, and historical aliases
still preserve parts of the old one. The same change also exposed three runtime
defects: Bubblewrap cannot create its namespace in the Docker backend, harmless
interpreter introspection such as `python3 --version` falls through to
`act_high`, and a Bash process with a non-zero exit code is rendered as
successful completion.

## Principles

### First principles

An Agent tool exists only if the runtime registers and executes it. Hiding an
old schema is not deletion. A retired name must be absent from providers,
registration, exports, dispatch aliases, prompts, filters, implementations, and
tests. Persisted calls using a retired name should follow the ordinary unknown
tool path; they do not deserve a second execution semantics.

Shell risk is derived from observable effects, not from an ever-growing list of
command names. The classifier should parse command structure, derive effects,
apply hard safety floors, and only then map those facts to a policy-facing risk
level. Approval policy remains separate from effect inference.

The OS sandbox, not command-string classification, is the confinement boundary.
Bubblewrap must be invoked in a form that can create a user namespace inside the
supported Docker deployment, and Compose must grant only the kernel facility
needed for that operation. The backend must not run privileged.

A tool call succeeds only when its execution contract succeeds. For Bash, a
zero exit status is success and a non-zero exit status is failure even when the
tool returned a structured payload containing stdout and stderr.

### Occam's razor

- Delete compatibility aliases instead of maintaining two names for one tool.
- Delete retired implementations instead of keeping a hidden shadow surface.
- Use one effect pipeline for local and remote commands instead of parallel
  command-name exception lists.
- Add the minimum Bubblewrap namespace flags and Compose permission required by
  the reproduced failure; do not add `privileged` or broad Linux capabilities.
- Derive UI state from the existing exit code instead of adding another status
  protocol.

## Scope

### Hard-delete retired Agent tools

Delete all Agent-side implementations and compatibility logic for:

- `files.read`
- `files.apply_patch`
- `glob`
- `grep`
- `attachments.read`
- `attachments.search`
- Agent-side `images.*`
- `files.write` as an alias for `write`
- `files.edit` as an alias for `edit`

Keep `write`, `edit`, `bash`, platform tools, `web.search`, mode-specific host
extensions, and the product Image API/UI. Attachment storage and prompt context
remain because Bash reads the session-owned read-only attachment paths.

### Semantic command-risk pipeline

The classifier has four layers:

1. Parse shell structure and reject or elevate syntax that prevents a reliable
   simple-command proof, including pipelines, redirects, substitutions, and
   compound commands.
2. Infer structured effects: `read`, `write`, `delete`, `network`,
   `process_control`, `privilege`, `code_execution`, and `unknown`.
3. Apply hardline inspectors for catastrophic or authorization-sensitive forms.
   These floors cannot be relaxed by later heuristics or an optional guardian.
4. Map effects, target boundary, sandbox state, and confidence to the existing
   risk levels consumed by permission policy.

Generic introspection is a proof, not a command-name exemption. It applies only
when all of the following are true:

- the input is one simple command;
- there is no pipeline, redirect, command/process substitution, or compound
  shell syntax;
- arguments contain only version/help introspection flags;
- there is no inline program, script path, module execution, stdin program, or
  code string;
- the executable belongs to a trusted read-only runtime/tool family.

Consequently, `python3 --version` is read-only, while `python3 -c ...`,
`python3 script.py`, redirected output, and composed shell forms remain governed
by their actual effects and confidence. Unknown ambiguous commands continue to
fail conservatively. An optional guardian may classify only ambiguous cases and
may never override hardline results.

## Bubblewrap runtime

On Linux, Bubblewrap starts with an unprivileged user namespace and maps the
process to root inside that namespace:

```text
bwrap --unshare-user --uid 0 --gid 0 ...
```

The backend Compose service enables the namespace syscall path with
`security_opt: ["seccomp:unconfined"]`. It does not use `privileged` and does
not add `SYS_ADMIN`. Adapter tests assert argv ordering and flags; deployment
tests assert the Compose security option and the absence of privileged mode.
The runtime/doctor check must exercise namespace creation rather than treating
the presence of the `bwrap` binary as proof of usability.

## Non-zero Bash exits

The Bash executor continues returning its structured result, including
`exit_code`, `stdout`, `stderr`, `cwd`, and `command`. The tool-execution layer
marks a Bash call with `exit_code != 0` as failed using the existing error event
path. The frontend renders that durable failure state and may show the exit
code/output; it must not infer success merely because a result payload exists.

## Compatibility and migration

There is no compatibility window. Requests and persisted actions naming a
deleted tool fail with the normal `Agent tool not found` behavior. No registry
alias, provider shim, schema filter, migration, or event rewrite translates old
names. This intentionally turns stale calls into visible failures rather than
silently preserving obsolete behavior.

## Verification

- Focused red-green tests for each removed surface, risk case, Bubblewrap
  runtime contract, and non-zero exit path.
- Full backend tests and Ruff.
- Frontend lint, tests, and dead-code lint when frontend code changes.
- Repository-wide search proving retired registrations, aliases, and dedicated
  implementations are gone while product Image API/UI remains.
- Docker/Compose contract tests proving the backend is not privileged.


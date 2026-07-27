# Agent Tool Surface Simplification Implementation Plan

> **Execution contract:** Use `superpowers:subagent-driven-development`, strict TDD, specification review, code-quality review, full verification, and then finish the branch with a PR. Do not pause between tasks unless a genuine external blocker prevents progress.

**Goal:** Reduce BioinfoFlow's redundant model-facing tools while preserving the platform tools that encode real product semantics. The ordinary execution surface becomes `write`, `edit`, `bash`, BioinfoFlow platform tools, and `web.search`.

**First-principles rationale:** A tool deserves a model-visible schema only when it contributes a boundary that Bash cannot safely or reliably express. File reading, searching, globbing, Docker CLI use, and web-page retrieval are composable command-line operations. BioinfoFlow projects, workflows, runs, and scheduler actions retain dedicated tools because they enforce product ownership, authorization, lifecycle, and typed API semantics. `web.search` remains dedicated because search-result discovery is not equivalent to opening a known URL.

**Approved scope:**

- Generic tools exposed to an executing model: `write`, `edit`, `bash`.
- Keep model-facing platform families: `projects.*`, `workflows.*`, `runs.*`, `scheduler.*`.
- Keep `web.search` as a small provider-backed search primitive.
- Keep runtime interaction/coordination extensions such as `ask_user`, `todo_write`, `exit_plan_mode`, and `task` where the selected mode already requires them.
- Remove model exposure for `read`, `files.*`, `attachments.*`, `grep`, `glob`, `images.*`, and `web.fetch`.
- Attachments are advertised as session-owned read-only paths and are read through `bash` (`sed`, `rg`, `file`, `agent-browser` where appropriate).
- Docker is invoked through `bash`. Do not reject `docker run`, `create`, `compose`, `exec`, `volume`, `system`, or remote contexts merely by verb.
- Full access (`permission_mode=bypass`) runs ordinary shell, Docker, SSH, network, install, and repository commands without prompting. Catastrophic data-loss operations remain approval-gated; authorization/target mismatches remain denied.
- Known-URL retrieval and browser interaction use the `agent-browser` CLI through `bash`; do not expose the broad agent-browser MCP surface by default.
- Preserve the existing product Image API/UI and all non-Agent image functionality.

## Non-goals

- Replacing BioinfoFlow platform tools with `bif` in this PR.
- Removing remote tools, memory, skills, plugins, or subagent extensions.
- Rewriting the Agent loop, ledger, durable event vocabulary, or public event protocol.
- Implementing a browser engine or HTML extraction stack inside BioinfoFlow.
- Treating all destructive commands as equivalent to catastrophic commands.

## Architectural decisions

### Tool exposure

Registration and model exposure remain separate. Legacy implementations may remain registered only where host compatibility requires them, but they must not appear in default, plan, execution, capability-bundle, worker, or remote-target model schemas. Explicit historical allowlists are filtered through the supported model-visible surface rather than resurrecting retired schemas.

The execution core is:

```text
write  edit  bash
projects.*  workflows.*  runs.*  scheduler.*
web.search
mode-specific host extensions
```

`write` and `edit` reuse the existing bounded filesystem implementations under unnamespaced tool names. There is no `read`: `bash` covers bounded reads with `sed`, `rg`, `head`, `tail`, `file`, and similar commands.

### Attachments

The canonical attachment storage remains unchanged. For a session `<session-id>`, the environment prompt advertises the absolute read-only root returned by `agent_session_attachments_root(<session-id>)` and a bounded manifest of ready attachments.

Local Bash receives the session attachment root as an additional read root and never as a write root. `write`, `edit`, redirects, and mutating shell commands cannot change it. Remote SSH execution does not silently copy attachments to the remote host; the prompt states that the advertised attachment path is local-only.

### Docker and full access

The command classifier assigns semantic risk; it does not blacklist Docker command names. Read-only Docker inspection is read/low risk, ordinary container lifecycle and remote-context operations are elevated/external, and data-loss operations such as prune or destructive volume removal are destructive/critical as appropriate.

Policy semantics:

| Condition | guarded/ask modes | full access (`bypass`) |
| --- | --- | --- |
| ordinary command, Docker, SSH, network, install | existing guarded behavior | allow |
| destructive but recoverable/scoped | ask | allow |
| catastrophic broad deletion, disk wipe, destructive prune/data loss | ask | ask |
| authorization, ownership, target/context mismatch | deny | deny |
| unattended worker cannot present required approval | deny/fail closed | deny/fail closed |

The distinction between approval-required catastrophe and non-bypassable authorization violation must be explicit in risk data; `critical` alone must not imply denial.

### Web search and agent-browser

`web.search` owns discovery only and returns normalized `{title, url, snippet}` results. Its provider boundary follows the Hermes pattern: isolate provider selection/normalization from the Agent tool, use bounded retries/timeouts, and return useful provider errors without fabricating results. The initial provider may remain DDGS, but the interface must make replacement possible without changing the tool schema.

`agent-browser` owns known-URL reading and browser interaction through Bash:

```bash
agent-browser read https://example.org
agent-browser open https://example.org
agent-browser snapshot
agent-browser click @e1
```

Before execution, BioinfoFlow recognizes direct `agent-browser` URL-bearing
commands and applies defense-in-depth public-URL checks: only `http`/`https`;
reject embedded credentials, localhost, loopback, link-local, private, reserved,
and metadata-service destinations. Browser CLI absence is reported as an
environment/runtime diagnostic, not replaced by a second in-process HTML
scraper.

This preflight validation is defense in depth, not a complete DNS-rebinding
boundary. `agent-browser`/Chromium resolves the hostname again after BioinfoFlow
validates it, and `--allowed-domains` constrains hostnames rather than pinning the
validated IP address. Closing that time-of-check/time-of-use gap requires a
controlled network broker or DNS/IP pinning and is intentionally outside this
tool-surface simplification PR. Deployments that require a strict outbound SSRF
boundary must enforce it at the network layer.

The URL/action parser and isolated config/environment apply to recognized direct
`agent-browser` invocations. Arbitrary Bash deliberately permits scripts,
interpreters, renamed executables, and other indirection that static parsing
cannot prove equivalent to the pinned binary. Such commands remain subject to
the normal Bash permission decision and OS sandbox; in Full Access they are part
of the authority the user explicitly granted. This direct-command hardening is
therefore defense in depth, not a substitute for a network egress boundary or a
restricted command runner.

Pin the supported agent-browser CLI major/minor in the backend runtime image or installer path and add a doctor/runtime check. Do not rely on an arbitrary globally installed version.

## TDD delivery plan

### Task 1: Lock the reduced model-visible surface

**Tests first**

- Update `backend/tests/test_agent_core/test_toolsets.py` to assert exact default, plan, execution, capability, worker, and remote-target surfaces.
- Add assertions that retired names never become visible through an explicit `allowed_tools` list.
- Update API/harness invariant tests that assert tool counts or names.
- Run the focused tests and confirm they fail because the old tools are still exposed.

**Implementation**

- Rename the existing model-facing `files.write` and `files.edit` specs to `write` and `edit`.
- Stop registering or expose-filter `files.read`, `files.apply_patch`, attachment, grep/glob, image, and web-fetch tools.
- Keep platform and mode-specific extensions intact.
- Update provider descriptions and system instructions so they no longer recommend retired tools.
- Re-run focused tests until green.

**Likely files**

- `backend/app/services/agent_core/tools/providers.py`
- `backend/app/services/agent_core/tools/toolsets.py`
- `backend/app/services/agent_core/tools/files/resources.py`
- `backend/app/services/agent_core/context/system_prompt.py`
- `backend/tests/test_agent_core/test_toolsets.py`
- `backend/tests/test_agent_core/test_harness_invariants.py`
- API toolset tests that assert exact names/counts

### Task 2: Make attachments readable through local Bash and immutable

**Tests first**

- Add a shell test that creates a ready session attachment and reads it with `bash` from the advertised absolute path.
- Add tests proving shell redirects, `sed -i`, `rm`, `chmod`, and `write`/`edit` reject attachment paths.
- Add a context test for the advertised attachment root and bounded ready-attachment manifest.
- Add a remote-target prompt test stating that attachments are local-only and are not copied automatically.
- Run tests and confirm failure because the attachment root is not yet included in the per-session shell boundary.

**Implementation**

- Derive the owned session attachment root from `context.session_id`; never accept an attachment root supplied by the model.
- Extend local Bash sandbox construction with the attachment root in `read_roots` only.
- Validate Bash `cwd` only against writable workspace/data roots, not attachment roots.
- Make `write` and `edit` resolve only through writable roots.
- Advertise the root and ready attachment summaries in environment context.
- Re-run focused tests until green.

**Likely files**

- `backend/app/services/agent_core/tools/execution/shell.py`
- `backend/app/services/agent_core/sandbox/process_sandbox.py`
- `backend/app/services/agent_core/permissions/context.py`
- `backend/app/services/agent_core/context/assembler.py`
- `backend/tests/test_agent_core/test_tools/test_execution_shell.py`
- `backend/tests/test_agent_core/test_context_picker.py` or a focused environment-context test

### Task 3: Correct Docker and full-access permission semantics

**Tests first**

- Add table tests for `docker run/create/compose/exec/volume/system/context --context` proving they are classified semantically and are not hard-blocked by verb.
- Add tests for Docker inspection, network/pull/push, scoped deletion, volume deletion, prune, and broad data-loss variants.
- Change/add policy tests proving full access allows ordinary, external, elevated, and scoped destructive commands without prompts.
- Add tests proving catastrophic commands return `ask`, not `deny`, in an interactive full-access session.
- Preserve tests proving ownership, scope, or remote connection mismatches are denied in every mode.
- Add unattended-worker tests proving an approval-required catastrophe fails closed.
- Run the focused tests and confirm the old hard-block behavior fails.

**Implementation**

- Separate `hard_blocked` authorization violations from `requires_explicit_approval` catastrophic actions.
- Refine Docker parsing so `volume` and `system` are classified by their subcommand and flags, not by the top-level noun.
- In `PermissionPolicy`, let bypass auto-allow every non-authorization violation except catastrophe; catastrophe becomes `ask` when interaction is possible.
- Keep broad `rm -rf`, unsafe device writes, filesystem formatting, shutdown, fork bombs, pipe-to-shell hardlines, and destructive Docker prune/data-loss operations approval-gated.
- Ensure the executor rejects an approval requirement only when the role/runtime cannot resume for a user decision.
- Re-run command-risk, approval, and shell tests until green.

**Likely files**

- `backend/app/services/agent_core/permissions/command_risk.py`
- `backend/app/services/agent_core/permissions/policy.py`
- `backend/app/services/agent_core/actions.py`
- `backend/app/services/agent_core/tools/executor.py`
- `backend/tests/test_agent_core/test_command_risk.py`
- `backend/tests/test_agent_core/test_tools/test_execution_shell.py`
- approval/resume tests

### Task 4: Keep one robust `web.search` and delegate browsing to agent-browser

**Tests first**

- Add `backend/tests/test_agent_core/test_web_tools.py` for normalized provider results, result limits, retryable errors, terminal provider errors, and stable schema.
- Add command-risk/URL-policy tests for valid public `agent-browser read/open`, unsupported schemes, credentials, localhost, private/loopback/link-local/reserved IPs, metadata endpoints, and DNS results that resolve privately.
- Add runtime/doctor tests for a missing or incompatible agent-browser binary.
- Confirm tests fail against the current direct DDGS coupling and absent URL policy/runtime integration.

**Implementation**

- Extract a small search-provider protocol and DDGS implementation; keep `SearchWebTool` responsible only for validation and normalization.
- Remove `FetchWebPageTool` from registration and delete the weak `urllib`/regex fetch implementation when no host compatibility caller remains.
- Add a shared public-URL validator used for recognized agent-browser commands.
- Add agent-browser to the backend runtime/install path at a pinned compatible version, plus a doctor capability check.
- Update the Bash description/environment prompt with the supported `agent-browser` commands and the fact that `web.search` discovers URLs.
- Re-run focused tests until green.

**Likely files**

- `backend/app/services/agent_core/tools/web/resources.py`
- new focused provider/URL-policy module under `backend/app/services/agent_core/`
- `backend/app/services/agent_core/permissions/command_risk.py`
- `backend/app/services/agent_core/context/system_prompt.py`
- `backend/app/cli/commands/doctor.py`
- `backend/Dockerfile`, install/runtime packaging files
- `backend/tests/test_agent_core/test_web_tools.py`
- `backend/tests/test_cli/test_doctor.py`

### Task 5: Remove stale assumptions and verify the product boundary

**Tests first**

- Update frontend/backend tests that render or list exact Agent tool names.
- Add a regression assertion that Image API/UI modules remain importable and their existing tests still pass while `images.*` is absent from Agent schemas.
- Search for instructions that tell the model to prefer file/image/fetch wrappers and make the search fail until those references are removed.

**Implementation**

- Remove dead Agent-only imports/modules/tests where no compatibility caller remains.
- Keep product image services, API endpoints, CLI/product UI, database models, and migrations untouched.
- Use generic tool rendering for `write`, `edit`, `bash`, platform tools, and `web.search`; remove retired-name branches only if present.
- Update user/developer documentation and the plan status.

**Verification**

From `backend/`:

```bash
rtk uv run pytest
rtk uv run ruff check .
```

If frontend files change, from `frontend/`:

```bash
rtk bun run lint
rtk bun run test
rtk bun run lint:dead-code
```

From the repository root:

```bash
rtk git diff --check
rtk git status --short
```

## Review and delivery gates

1. After every implementation task, run a fresh specification-compliance review.
2. Only after specification compliance passes, run a separate code-quality review.
3. Fix every Critical or Important finding and re-run the corresponding review.
4. Run the complete verification suite again after all review fixes.
5. Fetch and rebase onto current `origin/main`; resolve conflicts without dropping user changes.
6. Re-run affected verification after the rebase.
7. Force-add this ignored plan file deliberately, commit with a Conventional Commit title, push the branch, and create or update the PR.

## Acceptance criteria

- No default/session model schema exposes `read`, any `files.*`, `attachments.*`, `grep`, `glob`, `images.*`, or `web.fetch`.
- Execution models receive `write`, `edit`, and `bash`; approved platform tools and `web.search` remain available.
- Ready attachments can be inspected through Bash but cannot be mutated through any Agent file or shell path.
- Docker commands are judged by effects, not rejected by command-family names.
- Full access does not prompt for ordinary shell/Docker/SSH/network operations.
- Catastrophic data-loss operations require approval; authorization and target violations remain denied.
- `web.search` has a stable provider boundary and normalized output.
- Known-URL reading/browser interaction is documented and supported through a pinned `agent-browser` CLI with direct-command public-URL hardening and explicit residual-risk boundaries.
- Product Image API/UI behavior is unchanged.
- Focused and full verification pass, review findings are resolved, and the PR contains the implementation plus this plan.

## Implementation status (2026-07-27)

- [x] Reduced every model-visible surface to the supported generic, platform,
  coordination, and `web.search` tools; legacy write/edit names remain lookup
  aliases only.
- [x] Exposed session attachment paths through context and enforced read-only
  access while preserving the newer product-source and internal-state sandbox
  boundaries from `origin/main`.
- [x] Reworked Docker/full-access risk semantics so ordinary operations run in
  bypass mode, catastrophic data loss asks, and authorization/target violations
  remain denied.
- [x] Added provider-backed normalized web search, removed `web.fetch`, pinned
  agent-browser 0.33.0, added version-aware doctor checks, and documented the
  direct-command/DNS-rebinding residual-risk boundary.
- [x] Completed specification and code-quality review with no remaining
  Critical or Important findings.
- [x] Rebasing onto `origin/main` preserved its Agent/product-source isolation.
- [x] Verification: Ruff passed; affected regression suites passed; full backend
  suite passed with `2926 passed, 2 skipped`; `git diff --check` passed.
- [x] Packaging: Dockerfile tests passed and the pinned Linux ARM64 binary
  reported `agent-browser 0.33.0` inside a Linux container. A complete backend
  image build reached Debian dependency installation but Docker Desktop stopped
  it with `cannot allocate memory` while downloading Chromium.

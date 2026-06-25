# Agent Remote Diagnostics Implementation Plan

Goal: add bounded SSH-backed remote diagnostic tools for Bioinfoflow agents without taking ownership of the connection CRUD/API work.

Architecture:
- Add `backend/app/services/remote_execution.py` as the transport boundary. It exposes a small `RemoteConnectionConfig`, a `RemoteCommandResult`, and an `SshRemoteExecutor` that builds argv lists for OpenSSH and captures bounded subprocess output.
- Add `backend/app/services/agent_core/tools/remote/` for agent tools. The tools depend on a resolver helper that can use Agent A's connection service when it exists, while tests can inject an in-memory resolver.
- Add a dynamic context helper near the context assembler that renders selected remote connection instructions only when a selection can be resolved. The integration point is deliberately small so Agent A/frontend selection plumbing can wire it later.

Tasks:
- Write failing tests for SSH argv construction, timeout handling, truncation, safe quoted `cat`/`ls` command generation, remote tool output shape, tool registration, and context rendering.
- Implement the remote execution abstraction and SSH executor.
- Implement `remote.connections.list`, `remote.exec`, `remote.read_file`, and `remote.list_dir` tools with structured observations.
- Register the tools in the default registry and rely on existing risk/toolset policy: read-only list/read/list-dir tools expose in read contexts, while `remote.exec` is `act_high`.
- Run focused backend tests and ruff on changed backend files.

Integration notes to preserve:
- The connection resolver is intentionally thin until Agent A's model/service lands. Replace or extend it with the canonical repository/service instead of changing the tool contracts.
- Selected-connection context is opt-in through agent session metadata/toolset policy for now, so future API/frontend work can pass the current connection id without changing the prompt assembler shape.

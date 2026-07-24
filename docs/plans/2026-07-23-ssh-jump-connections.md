# SSH Jump Connections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic single-hop chained SSH mode that logs into a saved jump connection and then uses that host's local SSH identity to reach the target, while keeping selected and connecting host cards visually stable.

**Architecture:** A remote connection may use `auth_method="jump"` and reference one direct connection through `jump_connection_id`. `RemoteConnectionService` resolves the persisted pair into one `RemoteConnectionConfig`; command execution, streaming, remote browsing, Agent tools, and interactive terminals all consume that same resolved configuration. The executor starts the second `ssh` command on the jump host rather than using OpenSSH `ProxyJump`, so target credentials remain on the jump host.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, AsyncSSH and system OpenSSH, Next.js 16, React 19, Tailwind CSS 4, next-intl, Vitest, Testing Library, pytest.

---

## File map

- `backend/alembic/versions/0053_remote_connection_jump_host.py`: add the nullable self-referencing jump connection foreign key and extend the auth-method check constraint.
- `backend/app/models/remote_connection.py`: persist `jump_connection_id` and expose the `jump` auth method.
- `backend/app/schemas/remote_connection.py`: accept and serialize jump connections while rejecting incomplete direct/jump combinations.
- `backend/app/repositories/remote_connection_repo.py`: resolve workspace-scoped jump records and detect connections that depend on a jump host.
- `backend/app/services/remote_connection_service.py`: validate one-hop topology, protect referenced jump hosts, and produce resolved execution configuration.
- `backend/app/services/remote_execution.py`: compose and run the inner SSH command on the jump host for bounded commands and streaming.
- `backend/app/services/terminal_service.py`: open an interactive nested SSH session through the jump host.
- `backend/app/api/v1/connections.py`, `backend/app/api/v1/terminal.py`, `backend/app/services/agent_core/tools/remote/resources.py`: replace direct model-to-config conversion with the shared async resolver.
- `backend/tests/test_remote_connections_api.py`, `backend/tests/test_remote_execution.py`, `backend/tests/test_services/test_terminal_service.py`: backend red-green coverage.
- `frontend/lib/demo-connections.ts`: add the jump auth method and jump connection identifier to client contracts.
- `frontend/app/(app)/connections/page.tsx`: build jump payloads and resolve jump labels from the loaded connection set.
- `frontend/app/(app)/connections/components/connection-dialog.tsx`: add a restrained direct/via-jump route choice and saved jump-host selector.
- `frontend/app/(app)/connections/components/connection-list.tsx`: keep selected/testing card geometry stable and show the jump route in existing metadata space.
- `frontend/messages/en.json`, `frontend/messages/zh-CN.json`: add route labels, validation, and help copy.
- `frontend/tests/integration/pages/connections-page.test.tsx`: frontend red-green coverage for route configuration and card geometry.
- `docs/guides/remote-connections.md`, `docs/reference/architecture.md`, `docs/security.md`: document delegated target credentials, single-hop constraints, and troubleshooting.
- `docs/contracts/openapi-v1.json`: regenerate the API contract after schema changes.

### Task 1: Persist and validate single-hop jump connections

**Files:**
- Create: `backend/alembic/versions/0053_remote_connection_jump_host.py`
- Modify: `backend/app/models/remote_connection.py`
- Modify: `backend/app/schemas/remote_connection.py`
- Modify: `backend/app/repositories/remote_connection_repo.py`
- Modify: `backend/app/services/remote_connection_service.py`
- Test: `backend/tests/test_remote_connections_api.py`

- [ ] **Step 1: Write failing API tests for valid jump creation and redacted serialization**

Add a test that creates a direct `agent` connection, then creates a target with this payload:

```python
{
    "name": "HALOS acceptance",
    "host": "10.32.5.1",
    "port": 22,
    "username": "phoenix",
    "auth_method": "jump",
    "jump_connection_id": jump_id,
    "skill_instructions": None,
}
```

Assert status `201`, `auth_method == "jump"`, `jump_connection_id == jump_id`, and that password, private-key, alias, and key-path secrets are absent or null.

- [ ] **Step 2: Write failing service/API tests for topology constraints**

Cover each behavior independently:

```python
# jump mode requires jump_connection_id
assert response.status_code == 422

# direct modes reject jump_connection_id
assert response.status_code == 422

# an update cannot point a connection at itself
assert response.status_code == 422

# a jump host must belong to the same workspace
assert response.status_code == 422

# a jump host cannot itself use jump mode
assert response.status_code == 422

# deleting a referenced jump host is a conflict
assert response.status_code == 409

# converting a referenced direct host into jump mode is rejected
assert response.status_code == 422
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_remote_connections_api.py -q
```

Expected: the new cases fail because `jump` and `jump_connection_id` are not accepted or persisted.

- [ ] **Step 4: Add the model and migration**

Add `RemoteConnectionAuthMethod.JUMP = "jump"`, include it in `VALUES`, and add:

```python
jump_connection_id: Mapped[str | None] = mapped_column(
    ForeignKey("remote_connections.id", ondelete="RESTRICT"),
    nullable=True,
    index=True,
)
```

Migration `0053_remote_connection_jump_host` must:

```python
op.add_column(
    "remote_connections",
    sa.Column("jump_connection_id", sa.String(length=36), nullable=True),
)
op.create_index(
    "ix_remote_connections_jump_connection_id",
    "remote_connections",
    ["jump_connection_id"],
)
op.create_foreign_key(
    "fk_remote_connections_jump_connection_id",
    "remote_connections",
    "remote_connections",
    ["jump_connection_id"],
    ["id"],
    ondelete="RESTRICT",
)
```

Recreate the SQLite-compatible auth check constraint so it accepts `jump`.

- [ ] **Step 5: Add schema validation**

Extend both create/read/update contracts with `jump_connection_id: UUID | None`. The complete validator must enforce:

```python
if auth_method == "jump" and jump_connection_id is None:
    raise ValueError("jump_connection_id is required when auth_method is jump")
if auth_method != "jump" and jump_connection_id is not None:
    raise ValueError(
        f"jump_connection_id must be empty when auth_method is {auth_method}"
    )
```

When `auth_method == "jump"`, direct credential fields must be empty.

- [ ] **Step 6: Add repository and service topology validation**

Add repository methods with workspace scoping:

```python
async def get_jump_connection(
    self,
    jump_connection_id: str,
    *,
    workspace_id: str,
) -> RemoteConnection | None:
    return await self.get_for_workspace(
        jump_connection_id,
        workspace_id=workspace_id,
    )

async def has_jump_dependents(self, connection_id: str) -> bool:
    stmt = (
        select(self.model.id)
        .where(self.model.jump_connection_id == connection_id)
        .limit(1)
    )
    result = await self.session.execute(stmt)
    return result.scalar_one_or_none() is not None
```

In `RemoteConnectionService`, validate that the referenced jump exists, is direct, is not the same connection, and belongs to the same workspace. Clear all stored direct credentials when switching to jump mode; clear `jump_connection_id` when switching back to a direct method. Reject deletion of a referenced jump host and reject converting a referenced jump host into jump mode.

- [ ] **Step 7: Run the focused tests and verify GREEN**

```bash
rtk uv run pytest tests/test_remote_connections_api.py -q
```

Expected: all remote connection API tests pass.

- [ ] **Step 8: Apply the migration in the test environment**

```bash
rtk uv run alembic upgrade head
```

Expected: upgrade reaches `0053_remote_connection_jump_host` without error.

- [ ] **Step 9: Commit the persistence slice**

```bash
rtk git add backend/alembic/versions/0053_remote_connection_jump_host.py backend/app/models/remote_connection.py backend/app/schemas/remote_connection.py backend/app/repositories/remote_connection_repo.py backend/app/services/remote_connection_service.py backend/tests/test_remote_connections_api.py
rtk git commit -m "feat: model SSH jump connections"
```

### Task 2: Route bounded commands, streams, browsing, and Agent tools through the jump host

**Files:**
- Modify: `backend/app/services/remote_connection_service.py`
- Modify: `backend/app/services/remote_execution.py`
- Modify: `backend/app/api/v1/connections.py`
- Modify: `backend/app/services/agent_core/tools/remote/resources.py`
- Test: `backend/tests/test_remote_execution.py`
- Test: `backend/tests/test_remote_connections_api.py`
- Test: `backend/tests/test_agent_remote_tools.py`

- [ ] **Step 1: Write failing executor tests for nested command composition**

Create a direct jump config and a jump target config:

```python
jump = RemoteConnectionConfig(
    id="jump-1",
    name="Simulation environment",
    host="10.227.5.224",
    username="phoenix",
    port=22,
    password="jump-secret",
)
target = RemoteConnectionConfig(
    id="target-1",
    name="HALOS acceptance",
    host="10.32.5.1",
    username="phoenix",
    port=22,
    jump_connection=jump,
)
```

Assert `run(target, "hostname")` connects AsyncSSH only to `10.227.5.224` and executes this command there:

```text
ssh -p 22 -o BatchMode=yes -o ConnectTimeout=5 -- phoenix@10.32.5.1 hostname
```

Add a streaming case that verifies the same routing and preserves stdout, stderr, timeout, truncation, and exit frames.

- [ ] **Step 2: Write failing resolver tests**

Assert `RemoteConnectionService.resolve_connection_config(target)` returns a target config containing the fully decrypted direct jump config, while its public `summary()` includes only the target identity and a non-secret jump label/id.

- [ ] **Step 3: Write failing API and Agent tests**

For directory browsing, WebSocket probe execution, and `DatabaseRemoteConnectionResolver`, assert the executor receives a target config with `jump_connection.id == jump_id`. Do not duplicate nested SSH logic in those call sites.

- [ ] **Step 4: Run focused tests and verify RED**

```bash
rtk uv run pytest tests/test_remote_execution.py tests/test_remote_connections_api.py tests/test_agent_remote_tools.py -q
```

Expected: failures show that configs have no jump relationship and call sites still use the synchronous model converter.

- [ ] **Step 5: Extend the runtime configuration and command builder**

Add the recursive field with a one-hop runtime guard:

```python
@dataclass(frozen=True)
class RemoteConnectionConfig:
    jump_connection: RemoteConnectionConfig | None = None
```

Add a helper that builds the inner command entirely with argv quoting:

```python
def build_jump_command(
    connection: RemoteConnectionConfig,
    command: str,
    *,
    connect_timeout_seconds: int,
    interactive: bool = False,
) -> str:
    argv = ["ssh"]
    if connection.port is not None:
        argv.extend(["-p", str(connection.port)])
    if interactive:
        argv.append("-tt")
    argv.extend(["-o", "BatchMode=yes"])
    argv.extend(["-o", f"ConnectTimeout={connect_timeout_seconds}"])
    argv.extend(["--", connection.ssh_target, command])
    return shlex.join(argv)
```

Reject an empty command and a nested `jump_connection.jump_connection` with `BadRequestError`.

- [ ] **Step 6: Route run and stream through the direct jump config**

At the start of `SshRemoteExecutor.run()` and `.stream()`, when a jump exists, build the inner command and invoke the existing direct execution path with `connection.jump_connection`. This reuses password, stored private key, key-file, SSH config, and agent support for the first hop without adding another transport implementation.

- [ ] **Step 7: Centralize persisted config resolution**

Add:

```python
async def resolve_connection_config(
    self,
    connection: RemoteConnection,
) -> RemoteConnectionConfig:
    jump = None
    if connection.jump_connection_id:
        jump_model = await self.repo.get_jump_connection(
            str(connection.jump_connection_id),
            workspace_id=str(connection.workspace_id),
        )
        if jump_model is None:
            raise ValidationError("Jump connection is unavailable")
        jump = remote_connection_config_from_model(jump_model)
    return remote_connection_config_from_model(
        connection,
        jump_connection=jump,
    )
```

Change connection tests, directory browsing, exec WebSocket handling, and Agent database resolution to await this method.

- [ ] **Step 8: Run focused tests and verify GREEN**

```bash
rtk uv run pytest tests/test_remote_execution.py tests/test_remote_connections_api.py tests/test_agent_remote_tools.py -q
```

Expected: all focused command, API, and Agent tests pass.

- [ ] **Step 9: Commit the shared execution slice**

```bash
rtk git add backend/app/services/remote_connection_service.py backend/app/services/remote_execution.py backend/app/api/v1/connections.py backend/app/services/agent_core/tools/remote/resources.py backend/tests/test_remote_execution.py backend/tests/test_remote_connections_api.py backend/tests/test_agent_remote_tools.py
rtk git commit -m "feat: route SSH commands through jump hosts"
```

### Task 3: Route interactive remote terminals through the jump host

**Files:**
- Modify: `backend/app/services/terminal_service.py`
- Modify: `backend/app/api/v1/terminal.py`
- Test: `backend/tests/test_services/test_terminal_service.py`
- Test: `backend/tests/test_api/test_terminal_api.py`
- Test: `backend/tests/test_api/test_terminal_ws.py`

- [ ] **Step 1: Write failing terminal factory tests**

For a target with a stored-password jump connection, assert the factory connects AsyncSSH to the jump host and creates an outer PTY process whose command is equivalent to:

```text
ssh -p 22 -tt -o BatchMode=yes -o ConnectTimeout=10 -- phoenix@10.32.5.1 'cd /data/halos && exec "${SHELL:-/bin/sh}" -i'
```

For a system-SSH jump connection, assert `_spawn_pty_process` receives the jump host argv and the same nested interactive command. Keep resize, input, close, and exit semantics on the existing outer transport.

- [ ] **Step 2: Write a failing terminal API resolution test**

Create a remote project whose target connection uses a jump host. Assert `create_terminal_session` passes a resolved config with the jump connection to `TerminalSessionManager.create_or_get_remote`.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
rtk uv run pytest tests/test_services/test_terminal_service.py tests/test_api/test_terminal_api.py tests/test_api/test_terminal_ws.py -q
```

Expected: the new terminal routing assertions fail because the factory opens the target directly.

- [ ] **Step 4: Reuse the jump command builder in the terminal factory**

Before opening a terminal transport:

```python
command = _remote_shell_command(remote_root_path)
transport_connection = connection
if connection.jump_connection is not None:
    command = self.ssh_executor.build_jump_command(
        connection,
        command,
        connect_timeout_seconds=self.connect_timeout_seconds,
        interactive=True,
    )
    transport_connection = connection.jump_connection
```

Then run the existing AsyncSSH/system-SSH terminal logic against `transport_connection`. Do not add browser-side SSH handling.

- [ ] **Step 5: Resolve terminal configurations through the service**

In `backend/app/api/v1/terminal.py`, await `RemoteConnectionService.resolve_connection_config(connection)` before creating the remote session.

- [ ] **Step 6: Run focused tests and verify GREEN**

```bash
rtk uv run pytest tests/test_services/test_terminal_service.py tests/test_api/test_terminal_api.py tests/test_api/test_terminal_ws.py -q
```

Expected: all terminal service and API tests pass.

- [ ] **Step 7: Commit the terminal slice**

```bash
rtk git add backend/app/services/terminal_service.py backend/app/api/v1/terminal.py backend/tests/test_services/test_terminal_service.py backend/tests/test_api/test_terminal_api.py backend/tests/test_api/test_terminal_ws.py
rtk git commit -m "feat: open terminals through SSH jump hosts"
```

### Task 4: Add restrained jump configuration UI and stabilize connection cards

**Files:**
- Modify: `frontend/lib/demo-connections.ts`
- Modify: `frontend/app/(app)/connections/page.tsx`
- Modify: `frontend/app/(app)/connections/components/connection-dialog.tsx`
- Modify: `frontend/app/(app)/connections/components/connection-list.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: `frontend/tests/integration/pages/connections-page.test.tsx`

- [ ] **Step 1: Write failing card stability tests**

Render a selected connection in the `connecting` state and assert:

```typescript
expect(card.closest("article")).toHaveClass("h-[108px]", "box-border")
expect(card).toHaveClass("grid-cols-[44px_minmax(0,1fr)_6rem]")
expect(within(card).getByText("Connecting…").closest("span")).toHaveClass(
  "w-24",
  "justify-center",
)
```

Also assert the selected article uses an inset ring so selection never changes the outer visual footprint.

- [ ] **Step 2: Write failing jump form and card tests**

Load one direct connection named `Simulation environment` and open the add panel. Select `Via jump host`, choose that saved connection, enter `HALOS acceptance`, `10.32.5.1`, and `phoenix`, then assert the POST body contains:

```typescript
{
  name: "HALOS acceptance",
  host: "10.32.5.1",
  port: 22,
  username: "phoenix",
  auth_method: "jump",
  jump_connection_id: "simulation-224",
  ssh_alias: null,
  key_path: null,
  password: null,
  private_key: null,
  passphrase: null,
  skill_instructions: null,
}
```

Assert the card shows `phoenix@10.32.5.1` and a compact `via Simulation environment` route label. Assert the jump selector excludes the connection currently being edited and excludes connections that already use jump mode.

- [ ] **Step 3: Write failing client validation tests**

Assert jump mode cannot save without selecting a jump host, and that switching back to direct password mode clears `jump_connection_id` and restores the password requirement.

- [ ] **Step 4: Run the focused frontend test and verify RED**

Run from `frontend/`:

```bash
rtk bun run test tests/integration/pages/connections-page.test.tsx
```

Expected: failures show missing jump contracts, controls, route metadata, and stable geometry classes.

- [ ] **Step 5: Extend frontend contracts and form state**

Add `"jump"` to `RemoteConnectionAuthMethod` and add nullable `jump_connection_id` to read/create types and `ConnectionFormState`. Normalize absent values to an empty string in form state.

- [ ] **Step 6: Implement the compact route control**

Use existing Tailwind, button, label, and Radix Select components only. Add a `Connection route` section with two quiet options:

- `Direct`
- `Via jump host`

When jump is selected, show one labeled selector and a short helper explaining that Bioinfoflow logs into the selected host first and uses that host's local SSH key/config for the target. Keep target address, port, username, label, and Host Skill unchanged. Hide direct credential choices while in jump mode.

- [ ] **Step 7: Stabilize card geometry**

Change the article and inner grid to fixed geometry:

```tsx
<article
  className={cn(
    "group relative box-border h-[108px] rounded-2xl border bg-background px-4 py-3.5 transition-colors hover:bg-muted/35",
    selected
      ? "border-primary/30 bg-primary/[0.025] ring-1 ring-inset ring-primary/15"
      : "border-border/60",
  )}
>
  <button className="grid h-full w-full grid-cols-[44px_minmax(0,1fr)_6rem] items-center gap-3.5 pr-11 text-left focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">
```

Use `ring-inset` for selection. Give the status badge `w-24 justify-center`, keep the text column `min-w-0`, and keep route metadata within the same fixed text area. Do not introduce Framer Motion or a new icon package for this targeted fix.

- [ ] **Step 8: Add bilingual copy**

Add matching English and Chinese keys for route, direct, jump host, selector placeholder, helper text, missing-jump validation, and the card's `via` label. Run the i18n lint after implementation.

- [ ] **Step 9: Run focused tests and verify GREEN**

```bash
rtk bun run test tests/integration/pages/connections-page.test.tsx
rtk bun run lint:i18n
```

Expected: connection page tests and locale parity both pass.

- [ ] **Step 10: Commit the frontend slice**

```bash
rtk git add frontend/lib/demo-connections.ts 'frontend/app/(app)/connections/page.tsx' 'frontend/app/(app)/connections/components/connection-dialog.tsx' 'frontend/app/(app)/connections/components/connection-list.tsx' frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/integration/pages/connections-page.test.tsx
rtk git commit -m "feat: configure SSH jump hosts in connections UI"
```

### Task 5: Update contracts, documentation, and verification

**Files:**
- Modify: `docs/guides/remote-connections.md`
- Modify: `docs/reference/architecture.md`
- Modify: `docs/security.md`
- Modify: `docs/contracts/openapi-v1.json`

- [ ] **Step 1: Document the operational model**

Document these exact distinctions:

- Jump mode is session-level chained SSH, not OpenSSH `ProxyJump`.
- Bioinfoflow authenticates only to the saved jump connection.
- The jump host's local `ssh`, `~/.ssh/config`, agent, keys, and known-host policy authenticate the target.
- The first release supports one direct jump host only.
- The same route is used by tests, probes, file browsing, Agent tools, and remote terminals.
- Administrators should test the jump connection first, then verify `ssh -o BatchMode=yes user@target 'printf bioinfoflow-ok'` from that host.

- [ ] **Step 2: Regenerate the OpenAPI contract**

Run from `backend/`:

```bash
rtk uv run python scripts/export_openapi_contract.py ../docs/contracts/openapi-v1.json
rtk uv run python scripts/export_openapi_contract.py --check ../docs/contracts/openapi-v1.json
```

Expected: the committed contract contains `jump` and `jump_connection_id`, then check mode exits zero.

- [ ] **Step 3: Run backend verification**

```bash
rtk uv run pytest
rtk uv run ruff check .
```

Expected: all backend tests pass and Ruff reports no errors.

- [ ] **Step 4: Run frontend verification**

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
```

Expected: lint, locale parity, dead-code scan, tests, and production build all exit zero.

- [ ] **Step 5: Inspect migration and diff integrity**

From the repo root:

```bash
rtk git diff --check
rtk git status --short
rtk git diff origin/main...HEAD --stat
```

Expected: no whitespace errors and only jump-connection, card-stability, contract, documentation, plan, and test files are present.

- [ ] **Step 6: Commit documentation and generated contracts**

```bash
rtk git add docs/guides/remote-connections.md docs/reference/architecture.md docs/security.md docs/contracts/openapi-v1.json
rtk git commit -m "docs: explain chained SSH jump connections"
```

- [ ] **Step 7: Request independent code review**

Use `superpowers:requesting-code-review` with base `origin/main` and the current branch head. Fix every Critical and Important finding, add regression tests before fixes, and rerun the affected verification commands.

- [ ] **Step 8: Rebase and publish the PR**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

Rerun the complete verification after the rebase. Then push `codex/add-ssh-jump-connections` and open a draft PR titled:

```text
feat: add chained SSH jump connections
```

The PR body must explain the distinction from `ProxyJump`, list the unified consumers, describe the card geometry fix, and include every verification command and result.

## Plan self-review

- Every requested surface is covered: card layout, connection configuration, tests, probes, browsing, Agent tools, terminals, docs, review, and PR.
- The plan implements one hop only and contains no multi-hop route graph, forwarding agent, TCP proxy, or browser-side SSH.
- Runtime credentials remain on the direct jump connection; target credentials are never added to the Bioinfoflow target record.
- Production changes are always preceded by a focused failing test and observed RED result.
- All names are consistent: persisted `jump_connection_id`, runtime `jump_connection`, and auth method `jump`.

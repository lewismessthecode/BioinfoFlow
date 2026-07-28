# Agent Docker Access and Image Registry Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove hidden global registry rewriting, preserve explicit workflow/project registry bindings, give Agent Bash direct Docker socket access, and make Linux sandbox failures actionable.

**Architecture:** Treat workflow image references as authoritative unless a workflow or project explicitly binds a registry. Keep ordinary file-tool roots separate from process-sandbox capabilities so only Bash receives the Docker socket. Represent sandbox availability as structured diagnostic data while preserving fail-closed execution.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Docker SDK, Bubblewrap/Seatbelt, Nextflow, MiniWDL, Next.js 16, React 19, next-intl, Pytest, Vitest.

---

## File Structure

- `backend/app/models/container_registry.py` — registry persistence without a global-default flag.
- `backend/app/schemas/container_registry.py` — create/update/read API contracts.
- `backend/app/repositories/container_registry_repo.py` — deterministic listing and normalized endpoint lookup.
- `backend/app/services/container_registry_service.py` — scoped project lookup, credentials, and endpoint matching.
- `backend/alembic/versions/0058_remove_container_registry_default.py` — schema migration from the current merged head.
- `backend/app/services/workflow_image_service.py` — exact-reference resolution and registration prefetch.
- `backend/app/services/run_compiler.py` — workflow/project-only registry precedence and run-local WDL rewriting.
- `backend/app/services/agent_core/sandbox/local_boundary.py` — separate file roots from Bash sandbox capabilities.
- `backend/app/services/agent_core/sandbox/filesystem_policy.py` — ordinary file policy without special Docker-socket masking.
- `backend/app/services/agent_core/sandbox/process_sandbox.py` — structured adapter diagnostics and fail-closed errors.
- `backend/app/services/agent_core/tools/execution/shell.py` — pass Bash-specific roots to the sandbox.
- `backend/app/services/agent_core/permissions/context.py` — expose accurate local shell capability context.
- `backend/app/services/agent_core/context/assembler.py` — narrow Docker/image guidance for local Agent sessions.
- `backend/app/startup_logging.py` — report sandbox adapter availability and failure category.
- `frontend/components/bioinfoflow/settings/container-registries-panel.tsx` — remove default-registry UI.
- `frontend/app/(app)/workflows/components/register-form-fields.tsx` — describe explicit registry selection.
- `frontend/app/(app)/workflows/components/register-preview-panel.tsx` — show the no-selection state accurately.
- `frontend/lib/types.ts` — remove only the container-registry default field.
- `frontend/messages/en.json`, `frontend/messages/zh-CN.json` — synchronized copy changes.
- `docker-compose.yml`, `docker-compose.local.yml`, `docker-compose.prod.yml` — explicit read-write Docker socket mount plus existing Bubblewrap seccomp policy.
- `.env.example`, `backend/.env.example`, `RUNBOOK.md`, `docs/getting-started/docker.md`, `docs/security.md` — operational and security contracts.
- `docs/contracts/openapi-v1.json` — regenerated API contract.

### Task 1: Remove the global registry default from backend persistence and API contracts

**Files:**
- Create: `backend/alembic/versions/0058_remove_container_registry_default.py`
- Create: `backend/tests/test_migrations/test_remove_default_container_registry.py`
- Modify: `backend/app/models/container_registry.py`
- Modify: `backend/app/schemas/container_registry.py`
- Modify: `backend/app/repositories/container_registry_repo.py`
- Modify: `backend/app/services/container_registry_service.py`
- Modify: `backend/tests/test_api/test_container_registries.py`
- Modify: `backend/tests/test_services/test_container_registry_service.py`
- Modify: `backend/tests/test_schemas.py`

- [ ] **Step 1: Write failing API and service tests for registries without `is_default`**

Update the registry CRUD test so create/read payloads contain endpoint, namespace,
credential metadata, and status but never `is_default`. Add a scoped lookup test:

```python
@pytest.mark.asyncio
async def test_registry_service_returns_only_explicit_project_registry(db_session):
    service = ContainerRegistryService(db_session)
    registry = await service.create_registry(
        {
            "name": "Project Harbor",
            "endpoint": "https://harbor.example.test",
            "credential_source": "none",
            "updated_by": "user-1",
        }
    )
    project = Project(
        name="Bound project",
        user_id="user-1",
        workspace_id=DEFAULT_WORKSPACE_ID,
        container_registry_id=str(registry.id),
    )
    db_session.add(project)
    await db_session.commit()

    assert await service.get_project_registry(str(project.id)) == registry
    assert await service.get_project_registry(None) is None
```

Delete tests that enforce one global default. Add assertions that create and
update schemas reject or omit `is_default` according to their canonical contract.

- [ ] **Step 2: Run the focused tests and verify the old contract fails**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_api/test_container_registries.py tests/test_services/test_container_registry_service.py tests/test_schemas.py -q
```

Expected: failures show `is_default` still present and `get_project_registry()` missing.

- [ ] **Step 3: Write the failing migration test**

Create a migration test that upgrades a database at `0057_merge_agent_heads`
containing one registry with `is_default = true`, then asserts:

```python
columns = {column[1] for column in connection.execute("PRAGMA table_info(container_registries)")}
indexes = {
    row[1]
    for row in connection.execute("PRAGMA index_list(container_registries)")
}
assert "is_default" not in columns
assert "ix_container_registries_is_default" not in indexes
assert "uq_container_registries_default_singleton" not in indexes
assert connection.execute("SELECT name FROM container_registries").fetchall() == [
    ("Legacy Harbor",)
]
```

- [ ] **Step 4: Run the migration test and verify it fails because revision 0058 does not exist**

```bash
rtk uv run pytest tests/test_migrations/test_remove_default_container_registry.py -q
```

Expected: FAIL because the new migration/head is absent.

- [ ] **Step 5: Implement the migration and backend contract removal**

Create revision `0058_remove_default_container_registry` with
`down_revision = "0057_merge_agent_heads"`. In `upgrade()`, drop both known
indexes when present, then use `op.batch_alter_table("container_registries")`
to drop `is_default`. In `downgrade()`, restore a non-null Boolean column with
server default false and recreate both compatibility indexes.

Change the model table arguments to contain only the credential/status checks.
Remove `is_default` from all registry schemas and serialized dictionaries.
Simplify repository ordering:

```python
async def list_all(self) -> list[ContainerRegistry]:
    stmt = select(self.model).order_by(self.model.name, self.model.endpoint)
    result = await self.session.execute(stmt)
    return list(result.scalars().all())

async def get_by_endpoint(self, endpoint: str) -> ContainerRegistry | None:
    stmt = select(self.model).where(self.model.endpoint == endpoint).limit(1)
    result = await self.session.execute(stmt)
    return result.scalar_one_or_none()
```

Remove default-unsetting and singleton `IntegrityError` handling from create/update.
Replace `get_effective_registry()` with an explicit project-only method:

```python
async def get_project_registry(self, project_id: str | None) -> ContainerRegistry | None:
    if not project_id:
        return None
    project = await self.project_repo.get(project_id)
    if project is None:
        raise NotFoundError(f"Project not found: {project_id}")
    if not project.container_registry_id:
        return None
    return await self.registry_repo.get(str(project.container_registry_id))
```

- [ ] **Step 6: Run migration, API, schema, and service tests**

```bash
rtk uv run alembic upgrade head
rtk uv run alembic heads
rtk uv run pytest tests/test_migrations/test_remove_default_container_registry.py tests/test_api/test_container_registries.py tests/test_services/test_container_registry_service.py tests/test_schemas.py -q
```

Expected: one Alembic head and all focused tests pass.

- [ ] **Step 7: Commit Task 1**

```bash
rtk git add backend/alembic/versions/0058_remove_container_registry_default.py backend/app/models/container_registry.py backend/app/schemas/container_registry.py backend/app/repositories/container_registry_repo.py backend/app/services/container_registry_service.py backend/tests/test_migrations/test_remove_default_container_registry.py backend/tests/test_api/test_container_registries.py backend/tests/test_services/test_container_registry_service.py backend/tests/test_schemas.py
rtk git commit -m "refactor: remove global container registry default"
```

### Task 2: Make workflow image resolution explicit and attach credentials by endpoint

**Files:**
- Modify: `backend/app/services/workflow_image_service.py`
- Modify: `backend/app/services/run_compiler.py`
- Modify: `backend/tests/test_services/test_workflow_image_service.py`
- Modify: `backend/tests/test_services/test_run_compiler.py`
- Modify: `backend/tests/test_runtime/test_jobs_logging.py`
- Modify: `backend/tests/test_engine/test_wdl_adapter.py`

- [ ] **Step 1: Write failing resolution tests**

Add tests for these exact behaviours:

```python
def test_unqualified_image_without_binding_keeps_docker_reference():
    requirement = resolve_container_image_reference(
        "ubuntu:22.04",
        selected_registry=None,
    )
    assert requirement.full_name == "ubuntu:22.04"
    assert requirement.registry == "docker.io"
    assert requirement.rewrite_applied is False


def test_explicit_workflow_registry_qualifies_unqualified_image():
    registry = WorkflowImageRegistry(
        endpoint="http://10.227.4.56:80",
        namespace="pipeline-dev",
        registry_id="registry-1",
    )
    requirement = resolve_container_image_reference(
        "ubuntu:22.04",
        selected_registry=registry,
    )
    assert requirement.full_name == "10.227.4.56:80/pipeline-dev/ubuntu:22.04"
    assert requirement.rewrite_applied is True


def test_explicit_image_host_is_never_rewritten():
    requirement = resolve_container_image_reference(
        "quay.io/biocontainers/samtools:1.20",
        selected_registry=WorkflowImageRegistry(
            endpoint="http://10.227.4.56:80",
            namespace="pipeline-dev",
        ),
    )
    assert requirement.full_name == "quay.io/biocontainers/samtools:1.20"
    assert requirement.rewrite_applied is False
```

Add RunCompiler tests proving precedence is workflow binding -> project binding ->
no binding, with no global fallback. Add a WDL test proving only the generated
run-local copy changes and the registered source file remains byte-identical.

- [ ] **Step 2: Write failing credential-matching tests**

Add a repository/service test for normalized endpoint matching and a dispatch test:

```python
@pytest.mark.asyncio
async def test_explicit_registry_host_resolves_credentials_without_rewriting(db_session):
    registry = await ContainerRegistryService(db_session).create_registry(
        {
            "name": "Harbor",
            "endpoint": "https://harbor.example.test",
            "credential_source": "stored",
            "username": "robot",
            "password": "secret",
        }
    )
    requirements = await resolve_workflow_image_requirements_with_credentials(
        db_session,
        _schema("harbor.example.test/bio/tool:1.0"),
        selected_registry=None,
    )
    assert requirements[0].full_name == "harbor.example.test/bio/tool:1.0"
    assert requirements[0].registry_id == str(registry.id)
    assert requirements[0].auth_config == {"username": "robot", "password": "secret"}
```

- [ ] **Step 3: Run focused tests and verify failures**

```bash
rtk uv run pytest tests/test_services/test_workflow_image_service.py tests/test_services/test_run_compiler.py tests/test_runtime/test_jobs_logging.py tests/test_engine/test_wdl_adapter.py -q
```

Expected: failures expose the current global fallback API and missing endpoint credential lookup.

- [ ] **Step 4: Implement explicit-only resolution**

Rename resolver parameters from `default_registry` to `selected_registry` so the
API describes actual semantics. `WorkflowImagePrefetchService` loads only the
workflow registry, then the explicit project registry when a project is supplied;
otherwise it passes `None`.

Add one shared async resolver:

```python
async def resolve_workflow_image_requirements_with_credentials(
    session: AsyncSession,
    schema_json: dict | None,
    *,
    selected_registry: WorkflowImageRegistry | None,
) -> list[WorkflowImageRequirement]:
    requirements = resolve_workflow_image_requirements(
        schema_json,
        selected_registry=selected_registry,
    )
    # For an already-qualified image with no selected registry, match only the
    # configured endpoint and attach registry_id/auth without changing full_name.
    return await _attach_matching_registry_credentials(session, requirements)
```

Use this resolver for registration prefetch and RunCompiler runtime requirements.
Persist only `registry_id` through `runtime_dict()`; the existing
`attach_required_image_auth()` continues resolving secrets at dispatch.

Update `RunCompiler._resolve_workflow_image_registry()`:

```python
async def _resolve_workflow_image_registry(self, workflow, *, project_id: str):
    service = ContainerRegistryService(self.session)
    workflow_registry_id = getattr(workflow, "container_registry_id", None)
    if workflow_registry_id:
        material = await service.resolve_auth_material(str(workflow_registry_id))
        return workflow_registry_from_auth_material(material)
    project_registry = await service.get_project_registry(project_id)
    if project_registry is None:
        return None
    material = await service.resolve_auth_material(str(project_registry.id))
    return workflow_registry_from_auth_material(material)
```

Keep `rewrite_wdl_static_container_literals()` and Nextflow `docker.registry`
injection only when this method returns an explicit scoped registry.

- [ ] **Step 5: Implement normalized endpoint credential lookup**

Add a service method that compares `normalize_registry(registry.endpoint)` to
the requested registry host and returns auth material only for an exact match.
Use it in the shared credential-aware resolver for already-qualified images.
Never add a namespace or alter `full_name`.

Refactor `RunCompiler._enrich_runtime()` to accept the already-resolved
requirements rather than resolving synchronously. When there is no scoped
binding, remove stale `docker.registry` from both `config_overrides` and
`request.config_overrides`, including after `extra_config` merging, so retries
cannot resurrect the removed global behaviour.

- [ ] **Step 6: Run focused image/compiler/runtime tests**

```bash
rtk uv run pytest tests/test_services/test_workflow_image_service.py tests/test_services/test_run_compiler.py tests/test_runtime/test_jobs_logging.py tests/test_engine/test_wdl_adapter.py -q
```

Expected: all pass; `ubuntu:22.04` remains direct without an explicit binding.

- [ ] **Step 7: Commit Task 2**

```bash
rtk git add backend/app/services/workflow_image_service.py backend/app/services/run_compiler.py backend/tests/test_services/test_workflow_image_service.py backend/tests/test_services/test_run_compiler.py backend/tests/test_runtime/test_jobs_logging.py backend/tests/test_engine/test_wdl_adapter.py
rtk git commit -m "fix: resolve workflow images from explicit registries"
```

### Task 3: Remove global-default controls from the frontend while preserving workflow selection

**Files:**
- Modify: `frontend/components/bioinfoflow/settings/container-registries-panel.tsx`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/app/(app)/workflows/components/register-form-fields.tsx`
- Modify: `frontend/app/(app)/workflows/components/register-preview-panel.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Modify: `frontend/tests/unit/components/settings-page.test.tsx`
- Modify: `frontend/tests/integration/components/workflow-register-dialog.test.tsx`

- [ ] **Step 1: Write failing frontend expectations**

Update the settings test to assert the registry panel has no control or badge
named `Default` and sends this payload:

```ts
expect(body).toEqual({
  name: "Company Harbor",
  endpoint: "http://10.227.4.56:80",
  namespace: "pipeline-dev",
  insecure: true,
  credential_source: "stored",
  username: "pipeline-dev",
  password: "secret",
})
expect(screen.queryByRole("button", { name: "Make default" })).not.toBeInTheDocument()
```

In workflow registration tests, keep the explicit-selection assertion for
`container_registry_id`, add multipart coverage, and assert an empty selection
omits the field and displays “Use image references as written.”

- [ ] **Step 2: Run focused frontend tests and verify failures**

Run from `frontend/`:

```bash
rtk bun run test -- tests/unit/components/settings-page.test.tsx tests/integration/components/workflow-register-dialog.test.tsx
```

Expected: failures identify the default toggle/badge/action and stale copy.

- [ ] **Step 3: Implement the frontend contract cleanup**

In `container-registries-panel.tsx`, remove:

- `RegistryForm.is_default` and its empty/edit state;
- default-first sorting branches;
- the Default switch;
- `makeDefault()` and its PATCH;
- default badge, `Star` import, action prop, and Make default button;
- `is_default` from `buildRegistryPayload()`.

Keep deterministic alphabetical sorting. Remove only
`ContainerRegistryConfig.is_default` from `frontend/lib/types.ts`; do not alter
project/workspace `is_default` fields.

Use synchronized workflow copy:

```json
"asWritten": "Use image references as written",
"hint": "Optional. Select a registry only when unqualified workflow images should be resolved through it; explicit image hosts are kept as written."
```

```json
"asWritten": "按镜像引用原样使用",
"hint": "可选。仅当未限定 host 的工作流镜像需要通过指定仓库解析时才选择仓库；带显式 host 的镜像引用保持原样。"
```

Delete `defaultSaved`, `defaultBadge`, `fields.default`, and
`actions.makeDefault` in both locales.

- [ ] **Step 4: Run focused tests and i18n lint**

```bash
rtk bun run test -- tests/unit/components/settings-page.test.tsx tests/integration/components/workflow-register-dialog.test.tsx
rtk bun run lint:i18n
```

Expected: tests and locale synchronization pass.

- [ ] **Step 5: Commit Task 3**

```bash
rtk git add frontend/components/bioinfoflow/settings/container-registries-panel.tsx frontend/lib/types.ts 'frontend/app/(app)/workflows/components/register-form-fields.tsx' 'frontend/app/(app)/workflows/components/register-preview-panel.tsx' frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/unit/components/settings-page.test.tsx frontend/tests/integration/components/workflow-register-dialog.test.tsx
rtk git commit -m "refactor: remove default registry controls"
```

### Task 4: Give Agent Bash the Docker socket without expanding ordinary file tools

**Files:**
- Modify: `backend/app/services/agent_core/sandbox/local_boundary.py`
- Modify: `backend/app/services/agent_core/sandbox/filesystem_policy.py`
- Modify: `backend/app/services/agent_core/tools/execution/shell.py`
- Modify: `backend/app/services/agent_core/permissions/context.py`
- Modify: `backend/app/services/agent_core/context/assembler.py`
- Modify: `backend/tests/test_agent_core/test_local_filesystem_boundary.py`
- Modify: `backend/tests/test_agent_core/test_sandbox.py`
- Modify: `backend/tests/test_agent_core/test_permission_context.py`
- Modify: `backend/tests/test_agent_core/test_project_instructions.py`

- [ ] **Step 1: Write failing split-boundary tests**

Add tests proving an existing Unix Docker socket:

```python
assert socket not in boundary.policy.read_roots
assert socket not in boundary.policy.write_roots
assert socket in boundary.sandbox_read_roots
assert socket in boundary.sandbox_write_roots
assert socket not in boundary.protected_roots
```

Also prove nonexistent/non-Unix sockets are absent, broad configured roots that
contain the socket remain rejected, and file tools cannot resolve the socket as
an ordinary allowed path.

- [ ] **Step 2: Run boundary and permission tests and verify failures**

```bash
rtk uv run pytest tests/test_agent_core/test_local_filesystem_boundary.py tests/test_agent_core/test_permission_context.py tests/test_agent_core/test_project_instructions.py -q
```

Expected: failures show the socket is still protected and Bash-specific roots do not exist.

- [ ] **Step 3: Implement separate file and process capability roots**

Extend the boundary:

```python
@dataclass(frozen=True, slots=True)
class LocalFilesystemBoundary:
    working_directory: Path
    read_roots: tuple[Path, ...]
    write_roots: tuple[Path, ...]
    sandbox_read_roots: tuple[Path, ...]
    sandbox_write_roots: tuple[Path, ...]
    protected_roots: tuple[Path, ...]
    policy: FilesystemPolicy
```

When the configured `unix://` socket exists, append only that resolved path to
the sandbox roots. Remove it from `_protected_roots()`. Keep `_configured_roots()`
rejecting an ancestor directory that would expose the socket implicitly.

Remove the unconditional Docker-socket special case from
`FilesystemPolicy._require_not_protected()`; ordinary policy roots still exclude
the socket.

Pass `boundary.sandbox_read_roots` and `boundary.sandbox_write_roots` to
`SandboxRunner.build()`. Use the same roots in local permission target context,
and expose `docker_socket_access: "read_write"` or `"unavailable"` in the
bounded permission snapshot.

- [ ] **Step 4: Add narrow local Agent guidance**

When the socket capability exists, render guidance stating that Bash may use
Docker directly, image references remain exact unless an explicit scoped
registry is observed, unrelated images must not be substituted, and Docker
socket access grants full daemon authority. Ensure the guidance is absent for
remote SSH targets.

- [ ] **Step 5: Run focused shell, boundary, permission, and prompt tests**

```bash
rtk uv run pytest tests/test_agent_core/test_local_filesystem_boundary.py tests/test_agent_core/test_sandbox.py tests/test_agent_core/test_permission_context.py tests/test_agent_core/test_project_instructions.py tests/test_agent_core/test_tools/test_execution_shell.py tests/test_agent_core/test_command_risk.py -q
```

Expected: all pass and file-tool scope remains unchanged.

- [ ] **Step 6: Commit Task 4**

```bash
rtk git add backend/app/services/agent_core/sandbox/local_boundary.py backend/app/services/agent_core/sandbox/filesystem_policy.py backend/app/services/agent_core/tools/execution/shell.py backend/app/services/agent_core/permissions/context.py backend/app/services/agent_core/context/assembler.py backend/tests/test_agent_core/test_local_filesystem_boundary.py backend/tests/test_agent_core/test_sandbox.py backend/tests/test_agent_core/test_permission_context.py backend/tests/test_agent_core/test_project_instructions.py backend/tests/test_agent_core/test_tools/test_execution_shell.py backend/tests/test_agent_core/test_command_risk.py
rtk git commit -m "feat: allow agent bash to access Docker"
```

### Task 5: Preserve concrete Bubblewrap failure diagnostics

**Files:**
- Modify: `backend/app/services/agent_core/sandbox/process_sandbox.py`
- Modify: `backend/app/services/agent_core/sandbox/__init__.py`
- Modify: `backend/app/startup_logging.py`
- Modify: `backend/tests/test_agent_core/test_sandbox.py`
- Modify: `backend/tests/test_startup_logging.py`

- [ ] **Step 1: Write failing adapter diagnostic tests**

Cover `binary_missing`, successful probe, `probe_exit` with sanitized stderr,
`probe_timeout`, `probe_os_error`, cached full diagnostics, cache expiry, and a
fail-closed exception containing the category and bounded message.

Use an immutable value:

```python
@dataclass(frozen=True, slots=True)
class SandboxAvailability:
    adapter: str
    executable: str | None
    available: bool
    failure_category: str | None = None
    failure_message: str | None = None
```

Add startup logging expectations for enabled/fail-closed state, adapter,
executable, availability, category, and sanitized message.

- [ ] **Step 2: Run diagnostic tests and verify failures**

```bash
rtk uv run pytest tests/test_agent_core/test_sandbox.py tests/test_startup_logging.py -q
```

Expected: failures show boolean-only availability and generic startup reporting.

- [ ] **Step 3: Implement structured availability and caching**

Change adapters to expose `availability() -> SandboxAvailability`. Store the full
Bubblewrap result in the existing 30-second cache. Capture stderr only for the
bounded probe, collapse whitespace/control characters, and truncate to 400
characters. Preserve the two-second timeout.

`SandboxRunner.build()` must still fail closed, with an error such as:

```text
agent sandbox unavailable: bubblewrap probe_exit: bwrap: No permissions to create new namespace
```

Keep `available_adapter()` as a compatibility wrapper if it avoids unrelated
call-site churn.

- [ ] **Step 4: Add structured startup reporting**

Allow `SandboxRunner.from_settings(source)` to use the settings object passed to
`build_startup_summary()`. Report a nested `agent_core.sandbox` object. Disabled
sandbox reports disabled state without a fabricated adapter failure. Startup
must not fail when the probe fails; Bash itself remains fail-closed.

- [ ] **Step 5: Run focused diagnostic tests**

```bash
rtk uv run pytest tests/test_agent_core/test_sandbox.py tests/test_startup_logging.py -q
```

Expected: all pass, including bounded-message and cache tests.

- [ ] **Step 6: Commit Task 5**

```bash
rtk git add backend/app/services/agent_core/sandbox/process_sandbox.py backend/app/services/agent_core/sandbox/__init__.py backend/app/startup_logging.py backend/tests/test_agent_core/test_sandbox.py backend/tests/test_startup_logging.py
rtk git commit -m "fix: report agent sandbox probe failures"
```

### Task 6: Normalize Compose socket contracts and update operational documentation

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.local.yml`
- Modify: `docker-compose.prod.yml`
- Modify: `.env.example`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_local_first_run.py`
- Modify: `RUNBOOK.md`
- Modify: `docs/getting-started/docker.md`
- Modify: `docs/security.md`
- Modify: `docs/contracts/openapi-v1.json`

- [ ] **Step 1: Write failing Compose contract tests**

For all three distributed base Compose files assert:

```python
assert backend["security_opt"] == ["seccomp:unconfined"]
assert backend.get("privileged", False) is False
assert "SYS_ADMIN" not in backend.get("cap_add", [])
socket_mount = next(
    item for item in backend["volumes"] if item.get("target") == "/var/run/docker.sock"
)
assert "DOCKER_SOCKET_PATH" in socket_mount["source"]
assert socket_mount.get("read_only", False) is False
assert backend["environment"]["DOCKER_SOCKET"] == "unix:///var/run/docker.sock"
```

Also render base + GPU override and prove it inherits the socket and seccomp contract.

- [ ] **Step 2: Run Compose contract tests and verify failures**

```bash
rtk uv run pytest tests/test_local_first_run.py -q
```

Expected: failures show inconsistent short-syntax socket mounts.

- [ ] **Step 3: Normalize the Compose files**

Use long syntax in each base stack:

```yaml
- type: bind
  source: ${DOCKER_SOCKET_PATH:-/var/run/docker.sock}
  target: /var/run/docker.sock
  read_only: false
```

Keep `DOCKER_SOCKET=unix:///var/run/docker.sock`, `seccomp:unconfined`, no
`privileged`, and no `SYS_ADMIN`.

- [ ] **Step 4: Update environment examples and documentation**

Document that:

- `DOCKER_SOCKET_PATH` is the host socket mounted by Compose;
- `DOCKER_SOCKET` is the backend-visible URI;
- Agent Bash receives full Docker daemon authority;
- Bubblewrap filesystem/network restrictions do not constrain actions performed
  by the Docker daemon;
- global default workflow registries no longer exist;
- explicit workflow/project registry bindings still rewrite unqualified static
  images in run-local workflow copies;
- no binding leaves `ubuntu:22.04` unchanged;
- `binary_missing`, `probe_exit`, `probe_timeout`, and `probe_os_error` are the
  supported sandbox diagnostics;
- recovery uses rendered Compose inspection and backend recreation, not
  privileged mode or `SYS_ADMIN`.

Do not remove or rename deployment `IMAGE_REGISTRY`; it selects BioinfoFlow's own
published images and is unrelated to workflow registry resolution.

- [ ] **Step 5: Regenerate and check the OpenAPI contract**

Run from `backend/`:

```bash
rtk uv run python scripts/export_openapi_contract.py ../docs/contracts/openapi-v1.json
rtk uv run python scripts/export_openapi_contract.py --check ../docs/contracts/openapi-v1.json
```

Inspect that registry create/update schemas no longer contain `is_default`, while
workflow registration still contains `container_registry_id`.

- [ ] **Step 6: Run focused Compose, docs, and contract checks**

```bash
rtk uv run pytest tests/test_local_first_run.py tests/scripts/test_contract_exporters.py -q
rtk docker compose -f ../docker-compose.yml config
rtk docker compose -f ../docker-compose.prod.yml config
rtk docker compose --env-file ../scripts/tests/fixtures/local.env -f ../docker-compose.local.yml config
rtk docker compose -f ../docker-compose.yml -f ../docker-compose.gpu.yml config
```

Expected: all commands exit zero.

- [ ] **Step 7: Commit Task 6**

```bash
rtk git add docker-compose.yml docker-compose.local.yml docker-compose.prod.yml .env.example backend/.env.example backend/tests/test_local_first_run.py RUNBOOK.md docs/getting-started/docker.md docs/security.md docs/contracts/openapi-v1.json
rtk git commit -m "docs: align Docker and registry operations"
```

### Task 7: Run complete verification, review, rebase, and publish the PR

**Files:**
- Modify if required by failures: only files already in this plan.

- [ ] **Step 1: Run full backend verification**

From `backend/`:

```bash
rtk uv run alembic upgrade head
rtk uv run alembic heads
rtk uv run pytest
rtk uv run ruff check .
rtk uv run python scripts/export_openapi_contract.py --check ../docs/contracts/openapi-v1.json
```

Expected: one Alembic head, zero test failures, zero Ruff errors, contract check passes.

- [ ] **Step 2: Run full frontend verification**

From `frontend/`:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
```

Expected: all commands exit zero.

- [ ] **Step 3: Run repository and Compose verification**

From repo root:

```bash
rtk docker compose config
rtk docker compose -f docker-compose.prod.yml config
rtk docker compose --env-file scripts/tests/fixtures/local.env -f docker-compose.local.yml config
rtk docker compose -f docker-compose.yml -f docker-compose.gpu.yml config
rtk git diff --check
rtk git status --short
```

Expected: Compose renders, diff check passes, and only intended files are modified.

- [ ] **Step 4: Request independent final specification and code-quality reviews**

Provide reviewers the approved design, this implementation plan, the git range
from `origin/main` to `HEAD`, and fresh verification output. Fix every Critical
or Important issue, rerun affected tests, and request re-review until approved.

- [ ] **Step 5: Sync and rebase on the latest remote main**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

After a successful rebase, rerun the backend/frontend/Compose verification above.

- [ ] **Step 6: Push and create the PR**

Use title:

```text
fix: make agent Docker and registry resolution explicit
```

Push and create a ready PR whose body summarizes registry semantics, Docker
authority, sandbox diagnostics, migration compatibility, and all verification.

- [ ] **Step 7: Enable rebase automerge**

After required checks are present and the PR is mergeable, enable GitHub
automerge using the repository's rebase merge method. Do not force-push main or
weaken branch protection. If GitHub reports automerge unavailable, leave the PR
open and report the exact repository/check constraint.

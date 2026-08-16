from __future__ import annotations

import asyncio

import pytest

from app.services.agent_harness.environment_scope import (
    EnvironmentDescriptor,
    EnvironmentScopeRequest,
    resolve_environment_scope,
)
from app.services.agent_harness.workspace_router import (
    EnvironmentOutOfScopeError,
    EnvironmentUnavailableError,
    WorkspaceRouter,
)


async def _identity(workspace: object) -> object:
    return workspace


@pytest.mark.asyncio
async def test_router_rejects_out_of_scope_environment_before_resolution() -> None:
    scope = resolve_environment_scope(
        EnvironmentScopeRequest(
            mode="manual",
            selected_environment_ids=("local:primary",),
        ),
        [
            EnvironmentDescriptor("local:primary", "local", "Local"),
            EnvironmentDescriptor("ssh:gpu", "ssh", "GPU"),
        ],
    )
    authorization_checks: list[str] = []
    resolutions: list[str] = []

    async def authorize(environment_id: str) -> bool:
        authorization_checks.append(environment_id)
        return True

    async def resolve(environment_id: str) -> object | None:
        resolutions.append(environment_id)
        return object()

    router = WorkspaceRouter(
        scope=scope,
        authorize=authorize,
        resolve=resolve,
    )

    with pytest.raises(EnvironmentOutOfScopeError) as exc_info:
        await router.execute("ssh:gpu", _identity)

    assert exc_info.value.code == "environment_out_of_scope"
    assert exc_info.value.environment_id == "ssh:gpu"
    assert authorization_checks == []
    assert resolutions == []


@pytest.mark.asyncio
async def test_router_reports_an_authorized_environment_as_unavailable() -> None:
    scope = resolve_environment_scope(
        EnvironmentScopeRequest(mode="auto"),
        [EnvironmentDescriptor("ssh:gpu", "ssh", "GPU")],
    )

    async def authorize(_environment_id: str) -> bool:
        return True

    async def resolve(_environment_id: str) -> object | None:
        return None

    router = WorkspaceRouter(
        scope=scope,
        authorize=authorize,
        resolve=resolve,
    )

    with pytest.raises(EnvironmentUnavailableError) as exc_info:
        await router.execute("ssh:gpu", _identity)

    assert exc_info.value.code == "environment_unavailable"
    assert exc_info.value.environment_id == "ssh:gpu"


@pytest.mark.asyncio
async def test_router_rechecks_authorization_for_every_tool_call() -> None:
    scope = resolve_environment_scope(
        EnvironmentScopeRequest(mode="auto"),
        [EnvironmentDescriptor("ssh:gpu", "ssh", "GPU")],
    )
    decisions = iter((True, False))
    authorization_checks: list[str] = []
    workspace = object()

    async def authorize(environment_id: str) -> bool:
        authorization_checks.append(environment_id)
        return next(decisions)

    async def resolve(_environment_id: str) -> object | None:
        return workspace

    router = WorkspaceRouter(
        scope=scope,
        authorize=authorize,
        resolve=resolve,
    )

    assert await router.execute("ssh:gpu", _identity) is workspace
    with pytest.raises(EnvironmentOutOfScopeError):
        await router.execute("ssh:gpu", _identity)

    assert authorization_checks == ["ssh:gpu", "ssh:gpu"]


@pytest.mark.asyncio
async def test_execute_routes_parallel_calls_without_an_implicit_current_environment() -> (
    None
):
    scope = resolve_environment_scope(
        EnvironmentScopeRequest(mode="auto"),
        [
            EnvironmentDescriptor("local:primary", "local", "Local"),
            EnvironmentDescriptor("ssh:gpu", "ssh", "GPU"),
        ],
    )
    workspaces = {
        "local:primary": "local-runtime",
        "ssh:gpu": "remote-runtime",
    }

    async def authorize(_environment_id: str) -> bool:
        return True

    async def resolve(environment_id: str) -> str | None:
        return workspaces.get(environment_id)

    async def operation(workspace: str) -> str:
        await asyncio.sleep(0)
        return workspace

    router = WorkspaceRouter(
        scope=scope,
        authorize=authorize,
        resolve=resolve,
    )

    local_result, remote_result = await asyncio.gather(
        router.execute("local:primary", operation),
        router.execute("ssh:gpu", operation),
    )

    assert local_result == "local-runtime"
    assert remote_result == "remote-runtime"


@pytest.mark.asyncio
async def test_auto_scope_rejects_an_environment_discovered_after_run_start() -> None:
    scope = resolve_environment_scope(
        EnvironmentScopeRequest(mode="auto"),
        [EnvironmentDescriptor("local", "local", "Local")],
    )

    async def authorize(environment_id: str) -> bool:
        return environment_id == "ssh:new"

    async def resolve(environment_id: str) -> str | None:
        return "new-runtime" if environment_id == "ssh:new" else None

    router = WorkspaceRouter(scope=scope, authorize=authorize, resolve=resolve)

    with pytest.raises(EnvironmentOutOfScopeError):
        await router.execute("ssh:new", _identity)

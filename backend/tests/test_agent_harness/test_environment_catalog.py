from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.schemas.common import Pagination
from app.services.agent_harness.environment_catalog import EnvironmentCatalog


@dataclass
class _Connection:
    id: str
    name: str
    host: str
    port: int
    username: str
    last_status: str


class _Repository:
    def __init__(self, pages: list[list[_Connection]]) -> None:
        self.pages = pages
        self.workspace_ids: list[str] = []
        self.connections = {
            connection.id: connection for page in pages for connection in page
        }

    async def list_for_workspace(
        self,
        *,
        workspace_id: str,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[_Connection], Pagination]:
        self.workspace_ids.append(workspace_id)
        index = int(cursor or 0)
        next_cursor = str(index + 1) if index + 1 < len(self.pages) else None
        return self.pages[index], Pagination(
            limit=limit,
            has_more=next_cursor is not None,
            next_cursor=next_cursor,
        )

    async def get_for_workspace(
        self,
        connection_id: str,
        *,
        workspace_id: str,
    ) -> _Connection | None:
        self.workspace_ids.append(workspace_id)
        return self.connections.get(connection_id)


@pytest.mark.asyncio
async def test_catalog_lists_local_and_all_workspace_connections_without_secrets() -> (
    None
):
    repository = _Repository(
        [
            [_Connection("remote-a", "Alpha", "alpha.internal", 22, "alice", "online")],
            [_Connection("remote-b", "Beta", "beta.internal", 2202, "bob", "offline")],
        ]
    )

    environments = await EnvironmentCatalog(repository).list_authorized(
        workspace_id="workspace-1"
    )

    assert [item.environment_id for item in environments] == [
        "local",
        "remote-a",
        "remote-b",
    ]
    assert environments[0].kind == "local"
    assert environments[1].description == "alice@alpha.internal:22"
    assert environments[2].status == "offline"
    assert repository.workspace_ids == ["workspace-1", "workspace-1"]
    assert "password" not in repr(environments)


@pytest.mark.asyncio
async def test_catalog_rechecks_workspace_authorization_by_opaque_id() -> None:
    repository = _Repository(
        [[_Connection("remote-a", "Alpha", "alpha", 22, "alice", "online")]]
    )
    catalog = EnvironmentCatalog(repository)

    assert await catalog.is_authorized("local", workspace_id="workspace-1") is True
    assert await catalog.is_authorized("remote-a", workspace_id="workspace-1") is True
    assert (
        await catalog.is_authorized("remote-missing", workspace_id="workspace-1")
        is False
    )

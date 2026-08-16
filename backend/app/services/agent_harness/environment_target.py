from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol


class RemoteConnectionLookup(Protocol):
    async def get_for_workspace(
        self,
        connection_id: str,
        *,
        workspace_id: str,
    ) -> Any | None: ...


_CONFIGURATION_FIELDS = (
    "host",
    "port",
    "username",
    "auth_method",
    "ssh_alias",
    "key_path",
    "encrypted_password",
    "encrypted_private_key",
    "encrypted_passphrase",
    "jump_connection_id",
)


async def remote_environment_target_snapshot(
    repository: RemoteConnectionLookup,
    connection: Any,
) -> dict[str, Any]:
    configuration = _configuration_payload(connection)
    jump_connection_id = configuration.get("jump_connection_id")
    if jump_connection_id:
        jump = await repository.get_for_workspace(
            str(jump_connection_id),
            workspace_id=str(connection.workspace_id),
        )
        configuration["jump_connection"] = (
            _configuration_payload(jump) if jump is not None else None
        )
    revision = hashlib.sha256(
        json.dumps(
            configuration,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "kind": "ssh",
        "display_name": str(connection.name),
        "host": str(connection.host),
        "port": int(connection.port),
        "username": str(connection.username),
        "configuration_revision": revision,
    }


def _configuration_payload(connection: Any) -> dict[str, Any]:
    return {
        field: getattr(connection, field, None)
        for field in _CONFIGURATION_FIELDS
    }


__all__ = ["remote_environment_target_snapshot"]

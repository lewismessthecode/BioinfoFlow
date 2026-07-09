from __future__ import annotations

from typing import Any, Literal

from app.utils.exceptions import BadRequestError


ExecutionTargetType = Literal["local", "remote_ssh"]

LOCAL_EXECUTION_TARGET: dict[str, str] = {"type": "local"}


def normalize_execution_target(
    execution_target: Any,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, str]:
    source = execution_target
    if source is None:
        source = _execution_target_from_metadata(metadata)
    if source is None:
        return dict(LOCAL_EXECUTION_TARGET)

    if isinstance(source, str):
        target_type = source.strip().lower()
        target_payload: dict[str, Any] = {}
    elif isinstance(source, dict):
        target_type = str(source.get("type") or source.get("kind") or "").strip().lower()
        target_payload = source
    else:
        raise BadRequestError("execution_target must be an object or string")

    if target_type == "remote":
        target_type = "remote_ssh"
    if target_type in {"", "local"}:
        return dict(LOCAL_EXECUTION_TARGET)
    if target_type != "remote_ssh":
        raise BadRequestError("execution_target.type must be local or remote_ssh")

    connection_id = _first_selected_remote_connection_id(target_payload)
    if connection_id is None:
        connection_id = _first_selected_remote_connection_id(metadata)
    if connection_id is None:
        raise BadRequestError("remote_ssh execution_target requires connection_id")
    return {"type": "remote_ssh", "connection_id": connection_id}


def session_execution_target_from_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, str]:
    return normalize_execution_target(None, metadata=metadata)


def execution_target_from_session(session: Any) -> dict[str, str]:
    return session_execution_target_from_metadata(
        getattr(session, "session_metadata", None)
    )


def session_metadata_with_execution_target(
    metadata: dict[str, Any] | None,
    execution_target: Any,
) -> dict[str, Any] | None:
    next_metadata = dict(metadata or {})
    if execution_target is not None:
        next_metadata["execution_target"] = normalize_execution_target(
            execution_target,
            metadata=next_metadata,
        )
    elif "execution_target" in next_metadata:
        next_metadata["execution_target"] = normalize_execution_target(
            next_metadata.get("execution_target"),
            metadata=next_metadata,
        )
    return next_metadata or None


def is_remote_ssh_execution_target(execution_target: Any) -> bool:
    try:
        normalized = normalize_execution_target(execution_target)
    except BadRequestError:
        return False
    return normalized.get("type") == "remote_ssh"


def selected_remote_connection_ids_from_policy(policy: Any) -> list[str]:
    if not isinstance(policy, dict):
        return []
    ids: list[str] = []
    execution_target = policy.get("execution_target")
    if isinstance(execution_target, dict):
        ids.extend(_selected_ids_from_mapping(execution_target))
    ids.extend(_selected_ids_from_mapping(policy))
    return ids


def _execution_target_from_metadata(metadata: dict[str, Any] | None) -> Any:
    if not isinstance(metadata, dict):
        return None
    if "execution_target" in metadata:
        return metadata.get("execution_target")
    connection_id = _first_selected_remote_connection_id(metadata)
    if connection_id:
        return {"type": "remote_ssh", "connection_id": connection_id}
    return None


def _first_selected_remote_connection_id(policy: Any) -> str | None:
    for connection_id in selected_remote_connection_ids_from_policy(policy):
        return connection_id
    return None


def _selected_ids_from_mapping(policy: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in (
        "connection_id",
        "remote_connection_id",
        "selected_remote_connection_id",
        "current_remote_connection_id",
    ):
        value = policy.get(key)
        if isinstance(value, str) and value.strip():
            ids.append(value.strip())
    for key in ("remote_connection", "selected_remote_connection", "remote"):
        value = policy.get(key)
        if isinstance(value, dict):
            nested = value.get("id") or value.get("connection_id")
            if isinstance(nested, str) and nested.strip():
                ids.append(nested.strip())
    return ids


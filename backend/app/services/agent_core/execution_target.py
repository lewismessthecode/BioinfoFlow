from __future__ import annotations

from typing import Any, Literal

from app.utils.exceptions import BadRequestError


ExecutionTargetType = Literal["local", "remote_ssh"]
ExecutionScopeMode = Literal["auto", "manual"]

LOCAL_EXECUTION_TARGET: dict[str, str] = {"type": "local"}
AUTO_EXECUTION_SCOPE: dict[str, str] = {"mode": "auto"}


class ExecutionTargetChangedError(RuntimeError):
    pass


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


def session_execution_scope_from_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None
    return normalize_execution_scope(metadata.get("execution_scope"))


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


def normalize_execution_scope(execution_scope: Any) -> dict[str, Any] | None:
    if execution_scope is None:
        return None
    if isinstance(execution_scope, str):
        mode = execution_scope.strip().lower()
        payload: dict[str, Any] = {}
    elif isinstance(execution_scope, dict):
        mode = str(execution_scope.get("mode") or "").strip().lower()
        payload = execution_scope
    else:
        raise BadRequestError("execution_scope must be an object or string")

    if mode in {"", "auto"}:
        return dict(AUTO_EXECUTION_SCOPE)
    if mode != "manual":
        raise BadRequestError("execution_scope.mode must be auto or manual")

    targets = payload.get("selected_targets")
    if not isinstance(targets, list) or not targets:
        raise BadRequestError("manual execution_scope requires selected_targets")
    selected_targets = _dedupe_targets(
        [_normalize_scope_target(target) for target in targets]
    )
    if not selected_targets:
        raise BadRequestError("manual execution_scope requires selected_targets")
    return {"mode": "manual", "selected_targets": selected_targets}


def session_metadata_with_execution_scope(
    metadata: dict[str, Any] | None,
    execution_scope: Any,
) -> dict[str, Any] | None:
    next_metadata = dict(metadata or {})
    if execution_scope is not None:
        normalized_scope = normalize_execution_scope(execution_scope)
        if normalized_scope is not None:
            next_metadata["execution_scope"] = normalized_scope
    elif "execution_scope" in next_metadata:
        normalized_scope = normalize_execution_scope(next_metadata.get("execution_scope"))
        if normalized_scope is not None:
            next_metadata["execution_scope"] = normalized_scope
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
    execution_scope = policy.get("execution_scope")
    if isinstance(execution_scope, dict):
        scope_ids = _selected_ids_from_execution_scope(execution_scope)
        if scope_ids:
            return _dedupe(scope_ids)
    execution_target = policy.get("execution_target")
    if isinstance(execution_target, dict):
        target_ids = _selected_ids_from_mapping(execution_target)
        if target_ids:
            return _dedupe(target_ids)
        target_type = str(
            execution_target.get("type") or execution_target.get("kind") or ""
        ).strip().lower()
        if target_type in {"", "local"}:
            return []
        if target_type in {"remote", "remote_ssh", "ssh"}:
            return _dedupe(_selected_ids_from_mapping(policy))
    elif isinstance(execution_target, str):
        target_type = execution_target.strip().lower()
        if target_type in {"", "local"}:
            return []
        if target_type in {"remote", "remote_ssh", "ssh"}:
            return _dedupe(_selected_ids_from_mapping(policy))
    return _dedupe(_selected_ids_from_mapping(policy))


def _execution_target_from_metadata(metadata: dict[str, Any] | None) -> Any:
    if not isinstance(metadata, dict):
        return None
    if "execution_target" in metadata:
        return metadata.get("execution_target")
    scope_target = _single_execution_target_from_scope(metadata.get("execution_scope"))
    if scope_target is not None:
        return scope_target
    connection_id = _first_selected_id_from_mapping(metadata)
    if connection_id:
        return {"type": "remote_ssh", "connection_id": connection_id}
    return None


def _first_selected_remote_connection_id(policy: Any) -> str | None:
    for connection_id in selected_remote_connection_ids_from_policy(policy):
        return connection_id
    return None


def _first_selected_id_from_mapping(policy: dict[str, Any]) -> str | None:
    for connection_id in _dedupe(_selected_ids_from_mapping(policy)):
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


def _selected_ids_from_execution_scope(scope: dict[str, Any]) -> list[str]:
    if str(scope.get("mode") or "").strip().lower() != "manual":
        return []
    targets = scope.get("selected_targets")
    if not isinstance(targets, list):
        return []
    ids: list[str] = []
    for target in targets:
        if isinstance(target, dict):
            ids.extend(_selected_ids_from_mapping(target))
    return ids


def _single_execution_target_from_scope(scope: Any) -> dict[str, str] | None:
    try:
        normalized_scope = normalize_execution_scope(scope)
    except BadRequestError:
        return None
    if not normalized_scope or normalized_scope.get("mode") != "manual":
        return None
    targets = normalized_scope.get("selected_targets")
    if not isinstance(targets, list) or len(targets) != 1:
        return dict(LOCAL_EXECUTION_TARGET)
    target = targets[0]
    if target.get("type") == "remote_ssh" and target.get("connection_id"):
        return {"type": "remote_ssh", "connection_id": target["connection_id"]}
    return dict(LOCAL_EXECUTION_TARGET)


def _normalize_scope_target(target: Any) -> dict[str, str]:
    if isinstance(target, str):
        target_type = target.strip().lower()
        payload: dict[str, Any] = {}
    elif isinstance(target, dict):
        target_type = str(target.get("type") or target.get("kind") or "").strip().lower()
        payload = target
    else:
        raise BadRequestError("execution_scope.selected_targets must contain objects")

    if target_type == "remote":
        target_type = "remote_ssh"
    if target_type in {"", "local"}:
        return dict(LOCAL_EXECUTION_TARGET)
    if target_type != "remote_ssh":
        raise BadRequestError(
            "execution_scope.selected_targets type must be local or remote_ssh"
        )

    connection_id = _first_selected_remote_connection_id(payload)
    if connection_id is None:
        raise BadRequestError("remote_ssh execution_scope target requires connection_id")
    return {"type": "remote_ssh", "connection_id": connection_id}


def _dedupe_targets(targets: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for target in targets:
        key = (target.get("type", "local"), target.get("connection_id", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)
    return deduped


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped

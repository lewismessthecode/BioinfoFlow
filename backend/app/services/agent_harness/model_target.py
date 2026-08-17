from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.agent_harness.runtime_strategy import runtime_strategy_from_mapping
from app.services.model_runtime.contracts import ModelTarget


def model_target_from_snapshot(snapshot: Mapping[str, Any] | None) -> ModelTarget:
    """Build a target from the current private Session snapshot structure."""

    raw = snapshot.get("target") if isinstance(snapshot, Mapping) else None
    if not isinstance(raw, Mapping):
        raise ValueError(
            "agent session model snapshot must use the current target structure"
        )
    if any(alias in raw for alias in ("provider", "model", "api_base")):
        raise ValueError(
            "agent session model snapshot must use the current target structure"
        )

    endpoint_id = _required(raw, "endpoint_id")
    provider_kind = _required(raw, "provider_kind")
    model_name = _required(raw, "model_name")
    routed_model_name = _required(raw, "routed_model_name", default=model_name)
    wire_protocol = str(raw.get("wire_protocol") or "chat_completions")
    if wire_protocol not in {"chat_completions", "responses"}:
        raise ValueError(f"unsupported model wire protocol: {wire_protocol}")

    return ModelTarget(
        endpoint_id=endpoint_id,
        provider_kind=provider_kind,
        model_name=model_name,
        routed_model_name=routed_model_name,
        wire_protocol=wire_protocol,
        base_url=_optional(raw, "base_url"),
        network_access=str(raw.get("network_access") or "unrestricted"),
        api_key=_optional(raw, "api_key"),
        target_revision=_optional(raw, "target_revision"),
    )


def model_target_from_resolved(resolved: Mapping[str, Any]) -> ModelTarget:
    """Build an invocation target from freshly resolved private material."""

    request_args = resolved.get("request_args")
    if not isinstance(request_args, Mapping):
        request_args = {}
    wire_protocol = str(resolved.get("wire_protocol") or "chat_completions")
    if wire_protocol not in {"chat_completions", "responses"}:
        raise ValueError(f"unsupported model wire protocol: {wire_protocol}")
    return ModelTarget(
        endpoint_id=_required(resolved, "endpoint_id"),
        provider_kind=_required(resolved, "provider", "provider_kind"),
        model_name=_required(resolved, "model", "model_name"),
        routed_model_name=_required(
            resolved,
            "routed_model_name",
            default=_required(resolved, "model", "model_name"),
        ),
        wire_protocol=wire_protocol,
        base_url=_optional(request_args, "api_base"),
        network_access=str(resolved.get("network_access") or "unrestricted"),
        api_key=_optional(request_args, "api_key"),
        target_revision=_optional(resolved, "target_revision"),
    )


def private_model_snapshot(resolved: Mapping[str, Any]) -> dict[str, Any]:
    """Persist stable model identity and policy, never credential material."""

    request_args = resolved.get("request_args")
    if not isinstance(request_args, Mapping):
        request_args = {}
    return {
        "model_id": resolved.get("model_id"),
        "profile_id": resolved.get("profile_id"),
        "source": resolved.get("source"),
        "capabilities": dict(resolved.get("capabilities") or {}),
        "runtime_strategy": runtime_strategy_from_mapping(
            resolved.get("runtime_strategy")
        ).as_dict(),
        "context_window_tokens": _optional_positive_int(
            resolved.get("context_window_tokens")
        ),
        "target": {
            "endpoint_id": resolved.get("endpoint_id"),
            "provider_kind": resolved.get("provider"),
            "model_name": resolved.get("model"),
            "routed_model_name": resolved.get("routed_model_name"),
            "wire_protocol": resolved.get("wire_protocol") or "chat_completions",
            "base_url": request_args.get("api_base"),
            "target_revision": resolved.get("target_revision"),
            "network_access": resolved.get("network_access") or "unrestricted",
        },
    }


def _required(
    value: Mapping[str, Any],
    *names: str,
    default: str | None = None,
) -> str:
    result = _optional(value, *names) or default
    if not result:
        raise ValueError(f"resolved model target is missing {names[0]}")
    return result


def _optional(value: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        item = value.get(name)
        if isinstance(item, str) and item:
            return item
    return None


def _optional_positive_int(value: Any) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else None
    )


__all__ = [
    "model_target_from_resolved",
    "model_target_from_snapshot",
    "private_model_snapshot",
]

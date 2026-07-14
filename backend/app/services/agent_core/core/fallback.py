from __future__ import annotations

from app.services.agent_core.core.types import LoopResult


FALLBACK_ELIGIBLE_ERROR_CODES = {
    None,
    "model_request_failed",
    "empty_model_response",
}


def build_fallback_model_ids(
    fallback_model_ids: tuple[str, ...],
    *,
    primary_model_id: str | None = None,
) -> tuple[str, ...]:
    seen = {primary_model_id} if primary_model_id else set()
    ordered: list[str] = []
    for model_id in fallback_model_ids:
        normalized = str(model_id)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def should_try_fallback(result: LoopResult) -> bool:
    return (
        result.termination_reason == "model_failed"
        and result.error_code in FALLBACK_ELIGIBLE_ERROR_CODES
        and result.model_replay_safe
    )

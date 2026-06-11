from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from litellm import acompletion
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.agent_core.core.loop as loop_module
from app.config import settings
from app.models.agent_core import AgentTurnStatus
from app.repositories.agent_core_repo import AgentSessionRepository, AgentTurnRepository
from app.repositories.llm_repo import (
    LlmModelProfileRepository,
    LlmModelRepository,
    LlmProviderCredentialRepository,
    LlmProviderRepository,
)
from app.services.agent_core.core import AgentLoopController
from app.services.agent_core.core.fallback import (
    build_fallback_model_ids,
    should_try_fallback,
)
from app.services.agent_core.core.runtime_strategy import (
    RuntimeCapabilities,
    RuntimeStrategy,
    capabilities_from_model,
    resolve_runtime_strategy,
)
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.model_selection import (
    normalize_model_selection,
    session_model_selection_from_metadata,
)
from app.services.llm.provider_templates import normalize_provider_base_url
from app.services.llm.credentials import resolve_credential_material
from app.services.llm.catalog import _provider_requires_credential
from app.services.llm.credentials import credential_available, credential_configured

_ORIGINAL_ACOMPLETION = acompletion


class AgentCoreRuntime:
    def __init__(self, session: AsyncSession):
        self.turn_repo = AgentTurnRepository(session)
        self.session_repo = AgentSessionRepository(session)
        self.ledger = AgentEventLedger(session)
        self.llm_models = LlmModelRepository(session)
        self.llm_profiles = LlmModelProfileRepository(session)
        self.llm_providers = LlmProviderRepository(session)
        self.llm_credentials = LlmProviderCredentialRepository(session)

    async def run_no_tool_turn(self, turn_id: str):
        return await self.run_turn(turn_id)

    async def run_turn(self, turn_id: str):
        turn = await self.turn_repo.get(turn_id)
        if turn is None:
            return None
        if turn.status in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            return turn

        session = await self.session_repo.get(str(turn.session_id))
        if session is None:
            return await self._fail_turn(
                turn,
                error_message="Agent session could not be loaded for this turn.",
                error_code="session_not_found",
            )

        now = datetime.now(timezone.utc)
        turn = await self.turn_repo.update_all(
            turn,
            status=AgentTurnStatus.RUNNING,
            started_at=turn.started_at or now,
            completed_at=None,
            error_code=None,
            error_message=None,
            claimed_at=now,
            lease_until=now + _turn_lease_duration(),
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_STARTED,
            payload={},
        )

        resolved = await self._resolve_model_selection(turn=turn, session=session)
        if resolved is None:
            return await self._fail_turn(
                turn,
                error_message=(
                    "No usable model is configured. Select a provider/model in Settings, "
                    "or configure a deployment default."
                ),
                error_code="model_selection_missing",
            )

        if acompletion is not _ORIGINAL_ACOMPLETION:
            loop_module.acompletion = acompletion
        result = await self._run_model_attempts(turn=turn, session=session, resolved=resolved)
        fresh_turn = await self.turn_repo.get(str(turn.id))
        if fresh_turn is None:
            return None
        return await AgentLoopController(self.turn_repo.session).complete_turn_from_result(
            turn=fresh_turn,
            result=result,
        )

    async def resume_turn_after_action(self, action_id: str):
        from app.repositories.agent_core_repo import AgentActionRepository

        action = await AgentActionRepository(self.turn_repo.session).get(action_id)
        if action is None:
            return None
        turn = await self.turn_repo.get(str(action.turn_id))
        if turn is None:
            return None
        if turn.status in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            return turn

        session = await self.session_repo.get(str(turn.session_id))
        if session is None:
            return await self._fail_turn(
                turn,
                error_message="Agent session could not be loaded for this turn.",
                error_code="session_not_found",
            )

        now = datetime.now(timezone.utc)
        turn = await self.turn_repo.update_all(
            turn,
            status=AgentTurnStatus.RUNNING,
            started_at=turn.started_at or now,
            completed_at=None,
            error_code=None,
            error_message=None,
            claimed_at=now,
            lease_until=now + _turn_lease_duration(),
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_STARTED,
            payload={"resume_action_id": action_id},
        )

        resolved = await self._resolve_model_selection(turn=turn, session=session)
        if resolved is None:
            return await self._fail_turn(
                turn,
                error_message=(
                    "No usable model is configured. Select a provider/model in Settings, "
                    "or configure a deployment default."
                ),
                error_code="model_selection_missing",
            )
        if acompletion is not _ORIGINAL_ACOMPLETION:
            loop_module.acompletion = acompletion
        result = await self._run_model_attempts(
            turn=turn,
            session=session,
            resolved=resolved,
            resume_action_id=action_id,
        )
        fresh_turn = await self.turn_repo.get(str(turn.id))
        if fresh_turn is None:
            return None
        return await AgentLoopController(self.turn_repo.session).complete_turn_from_result(
            turn=fresh_turn,
            result=result,
        )

    async def _resolve_model_selection(self, *, turn, session) -> dict[str, Any] | None:
        snapshot = turn.model_profile_snapshot or {}
        candidates: list[tuple[str, dict[str, str] | None]] = [
            (
                "turn_profile",
                normalize_model_selection(
                    {"profile_id": snapshot.get("requested_model_profile_id")}
                ),
            ),
            ("turn", normalize_model_selection(snapshot.get("requested_model_selection"))),
            (
                "session",
                session_model_selection_from_metadata(
                    getattr(session, "session_metadata", None)
                ),
            ),
            (
                "session_profile",
                normalize_model_selection({"profile_id": session.default_model_profile_id}),
            ),
        ]
        for source, selection in candidates:
            catalog = await self._catalog_selection(
                selection,
                source=source,
                workspace_id=str(session.workspace_id),
                user_id=turn.user_id,
            )
            if catalog:
                return catalog
            if (
                source in {"turn_profile", "turn", "session_profile", "session"}
                and selection
                and (selection.get("model_id") or selection.get("profile_id"))
            ):
                return None
        return await self._catalog_default_selection(
            workspace_id=str(session.workspace_id),
            user_id=turn.user_id,
        )

    async def _catalog_selection(
        self,
        selection: dict[str, str] | None,
        *,
        source: str,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        if not selection:
            return None
        profile_id = selection.get("profile_id")
        model_id = selection.get("model_id")
        profile = None
        if profile_id:
            profile = await self.llm_profiles.get_visible(
                profile_id,
                workspace_id=workspace_id,
                user_id=user_id,
                enabled_only=True,
            )
            if profile is None:
                return None
            model_id = str(profile.primary_model_id)
        if not model_id:
            return None
        model = await self.llm_models.get_visible(
            model_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if model is None:
            return None
        provider = await self.llm_providers.get_visible(
            str(model.provider_id),
            workspace_id=workspace_id,
            user_id=user_id,
            enabled_only=True,
        )
        if provider is None:
            return None
        credential = await self.llm_credentials.get_for_provider(str(provider.id))
        if not credential_available(
            credential,
            credential_required=_provider_requires_credential(provider),
        ):
            return None
        material = resolve_credential_material(credential)
        request_args: dict[str, Any] = {}
        if material.api_key:
            request_args["api_key"] = material.api_key
        if provider.base_url:
            # Per-kind normalization keeps native base URLs intact (Anthropic
            # and Gemini stay at the host root; only OpenAI-compatible providers
            # get the /v1 suffix), so LiteLLM receives a valid api_base.
            request_args["api_base"] = normalize_provider_base_url(
                provider.kind, provider.base_url
            )
        capabilities = capabilities_from_model(model)
        runtime_strategy = resolve_runtime_strategy(
            capabilities=capabilities,
            profile=profile if profile_id else None,
        )
        result = {
            "provider": provider.kind,
            "model": model.model_id,
            "model_id": str(model.id),
            "source": source,
            "capabilities": capabilities.as_dict(),
            "runtime_strategy": runtime_strategy.as_dict(),
            "request_args": request_args,
        }
        if profile_id:
            result["profile_id"] = profile_id
        return result

    async def _catalog_default_selection(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        providers = await self.llm_providers.list_available(
            workspace_id=workspace_id,
            user_id=user_id,
            enabled_only=True,
        )
        for scope in ("user", "workspace", "global"):
            for provider in providers:
                if provider.scope != scope:
                    continue
                credential = await self.llm_credentials.get_for_provider(str(provider.id))
                metadata = provider.provider_metadata or {}
                if scope == "global" and not (
                    metadata.get("envManaged") is True
                    or credential_configured(credential)
                ):
                    continue
                if not credential_available(
                    credential,
                    credential_required=_provider_requires_credential(provider),
                ):
                    continue
                models = await self.llm_models.list_for_provider(str(provider.id))
                if not models:
                    continue
                return await self._catalog_selection(
                    {"model_id": str(models[0].id)},
                    source="catalog_default",
                    workspace_id=workspace_id,
                    user_id=user_id,
                )
        return None

    async def _run_model_attempts(
        self,
        *,
        turn,
        session,
        resolved: dict[str, Any],
        resume_action_id: str | None = None,
    ):
        controller = AgentLoopController(self.turn_repo.session)
        attempts = [resolved, *await self._resolve_fallback_candidates(turn=turn, session=session, resolved=resolved)]
        next_resume_action_id = resume_action_id
        for attempt_index, candidate in enumerate(attempts):
            fresh_turn = await self.turn_repo.get(str(turn.id))
            if fresh_turn is not None:
                turn = fresh_turn
            turn = await self._persist_model_resolution(
                turn,
                candidate,
                attempt_index=attempt_index,
            )
            runtime_strategy = _resolved_runtime_strategy(candidate)
            if attempt_index == 0:
                await self.ledger.append(
                    session_id=str(turn.session_id),
                    turn_id=str(turn.id),
                    type=AgentEventType.MODEL_SELECTED,
                    payload={
                        "provider": candidate["provider"],
                        "model": candidate["model"],
                        "source": candidate["source"],
                    },
                )
            else:
                await self.ledger.append(
                    session_id=str(turn.session_id),
                    turn_id=str(turn.id),
                    type=AgentEventType.MODEL_FALLBACK,
                    payload={
                        "attempt_index": attempt_index + 1,
                        "provider": candidate["provider"],
                        "model": candidate["model"],
                        "source": candidate["source"],
                    },
                )

            if next_resume_action_id is not None:
                result = await controller.resume_turn_from_action(
                    action_id=next_resume_action_id,
                    provider=candidate["provider"],
                    model=candidate["model"],
                    capabilities=_resolved_capabilities(candidate),
                    strategy=runtime_strategy,
                    request_args=candidate["request_args"],
                    max_tokens=runtime_strategy.max_tokens,
                )
                next_resume_action_id = None
            else:
                result = await controller.run_turn(
                    turn_id=str(turn.id),
                    provider=candidate["provider"],
                    model=candidate["model"],
                    capabilities=_resolved_capabilities(candidate),
                    strategy=runtime_strategy,
                    request_args=candidate["request_args"],
                    max_tokens=runtime_strategy.max_tokens,
                )
            if not should_try_fallback(result) or attempt_index == len(attempts) - 1:
                return result
        raise RuntimeError("Agent runtime exhausted model attempts without returning a result.")

    async def _persist_model_resolution(
        self,
        turn,
        resolved: dict[str, Any],
        *,
        attempt_index: int,
    ):
        snapshot = dict(turn.model_profile_snapshot or {})
        attempts = list(snapshot.get("model_attempts") or [])
        attempts.append(
            {
                "attempt_index": attempt_index,
                "provider": resolved["provider"],
                "model": resolved["model"],
                "source": resolved["source"],
                "model_id": resolved.get("model_id"),
            }
        )
        snapshot["model_attempts"] = attempts
        snapshot["resolved_model_selection"] = {
            "provider": resolved["provider"],
            "model": resolved["model"],
        }
        if resolved.get("model_id"):
            snapshot["resolved_model_id"] = resolved["model_id"]
        if resolved.get("profile_id"):
            snapshot["resolved_profile_id"] = resolved["profile_id"]
        snapshot["resolved_model_source"] = resolved["source"]
        snapshot["resolved_model_capabilities"] = resolved.get("capabilities", {})
        snapshot["resolved_runtime_strategy"] = resolved.get("runtime_strategy", {})
        return await self.turn_repo.update_all(
            turn,
            model_profile_snapshot=snapshot,
            claimed_at=turn.claimed_at or datetime.now(timezone.utc),
            lease_until=datetime.now(timezone.utc) + _turn_lease_duration(),
        )

    async def _resolve_fallback_candidates(
        self,
        *,
        turn,
        session,
        resolved: dict[str, Any],
    ) -> list[dict[str, Any]]:
        runtime_strategy = _resolved_runtime_strategy(resolved)
        fallback_model_ids = build_fallback_model_ids(
            runtime_strategy.fallback_model_ids,
            primary_model_id=resolved.get("model_id"),
        )
        candidates: list[dict[str, Any]] = []
        for model_id in fallback_model_ids:
            candidate = await self._catalog_selection(
                {"model_id": model_id},
                source="fallback_model",
                workspace_id=str(session.workspace_id),
                user_id=turn.user_id,
            )
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    async def _fail_turn(self, turn, *, error_message: str, error_code: str):
        completed_at = datetime.now(timezone.utc)
        turn = await self.turn_repo.update_all(
            turn,
            status=AgentTurnStatus.FAILED,
            final_text=None,
            completed_at=completed_at,
            termination_reason="model_failed",
            error_code=error_code,
            error_message=error_message,
            claimed_at=None,
            lease_until=None,
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_FAILED,
            payload={"error_message": error_message, "error_code": error_code},
        )
        return turn


def _resolved_capabilities(resolved: dict[str, Any]) -> RuntimeCapabilities:
    capabilities = resolved.get("capabilities")
    if not isinstance(capabilities, dict):
        return RuntimeCapabilities()
    return RuntimeCapabilities(
        supports_streaming=bool(capabilities.get("supports_streaming", True)),
        supports_reasoning=bool(capabilities.get("supports_reasoning", False)),
        supports_tools=bool(capabilities.get("supports_tools", True)),
    )


def _resolved_runtime_strategy(resolved: dict[str, Any]) -> RuntimeStrategy:
    strategy = resolved.get("runtime_strategy")
    if not isinstance(strategy, dict):
        return RuntimeStrategy()
    fallback_model_ids = strategy.get("fallback_model_ids") or []
    return RuntimeStrategy(
        use_streaming=bool(strategy.get("use_streaming", True)),
        allow_thinking=bool(strategy.get("allow_thinking", True)),
        allow_tools=bool(strategy.get("allow_tools", True)),
        max_tokens=_coerce_optional_int(strategy.get("max_tokens")),
        reasoning_budget=_coerce_optional_int(strategy.get("reasoning_budget")),
        fallback_model_ids=tuple(str(item) for item in fallback_model_ids),
    )


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _turn_lease_duration() -> timedelta:
    seconds = max(int(getattr(settings, "agent_turn_lease_seconds", 300) or 300), 1)
    return timedelta(seconds=seconds)

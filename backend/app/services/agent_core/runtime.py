from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import app.database as app_database
from litellm import acompletion
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from app.services.agent_core.core.lease import (
    LEASE_LOSS_CANCELLATION,
    is_lease_loss_cancellation,
)
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
from app.services.agent_core.metrics import agent_metrics
from app.services.agent_core.model_selection import (
    normalize_model_selection,
    session_model_selection_from_metadata,
)
from app.services.agent_core.observability import truncate_log_value
from app.services.llm.provider_templates import normalize_provider_base_url
from app.services.llm.credentials import resolve_credential_material
from app.services.llm.catalog import (
    _provider_requires_credential,
    validate_provider_transport,
)
from app.services.llm.credentials import credential_available, credential_configured
from app.utils.logging import get_logger

_ORIGINAL_ACOMPLETION = acompletion
logger = get_logger(__name__)


class _TurnLeaseHeartbeat:
    def __init__(self, session: AsyncSession, *, turn_id: str, owner_token: str):
        bind = session.bind
        self._session_factory = (
            async_sessionmaker(bind=bind, expire_on_commit=False, class_=AsyncSession)
            if bind is not None
            else app_database.async_session_maker
        )
        self._turn_id = turn_id
        self._owner_token = owner_token
        self._owner_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self.ownership_lost = False

    async def __aenter__(self):
        self._owner_task = asyncio.current_task()
        self._heartbeat_task = asyncio.create_task(self._run())
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        await self.stop()

    async def stop(self) -> None:
        heartbeat_task = self._heartbeat_task
        self._heartbeat_task = None
        if heartbeat_task is None:
            return
        self._stop_event.set()
        await heartbeat_task

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=_turn_lease_heartbeat_interval(),
                )
                return
            except TimeoutError:
                pass
            try:
                async with self._session_factory() as session:
                    renewed = await AgentTurnRepository(session).renew_execution_lease(
                        self._turn_id,
                        owner_token=self._owner_token,
                        lease_until=datetime.now(timezone.utc) + _turn_lease_duration(),
                    )
            except Exception:
                logger.exception(
                    "agent_core.turn.lease_heartbeat_failed",
                    turn_id=self._turn_id,
                )
                renewed = None
            if renewed is not None:
                continue
            self.ownership_lost = True
            if self._owner_task is not None:
                self._owner_task.cancel(LEASE_LOSS_CANCELLATION)
            return


class AgentCoreRuntime:
    def __init__(self, session: AsyncSession):
        self.turn_repo = AgentTurnRepository(session)
        self.session_repo = AgentSessionRepository(session)
        self.ledger = AgentEventLedger(session)
        self.llm_models = LlmModelRepository(session)
        self.llm_profiles = LlmModelProfileRepository(session)
        self.llm_providers = LlmProviderRepository(session)
        self.llm_credentials = LlmProviderCredentialRepository(session)
        self._execution_owner_token: str | None = None

    async def run_no_tool_turn(self, turn_id: str):
        return await self.run_turn(turn_id)

    async def run_turn(self, turn_id: str):
        turn = await self.turn_repo.get_fresh(turn_id)
        if turn is None:
            return None
        if turn.status in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            return turn

        now = datetime.now(timezone.utc)
        owner_token = str(uuid4())
        turn = await self.turn_repo.claim_execution(
            turn_id,
            owner_token=owner_token,
            claimed_at=now,
            lease_until=now + _turn_lease_duration(),
        )
        if turn is None:
            return await self.turn_repo.get_fresh(turn_id)
        self._execution_owner_token = owner_token
        return await self._run_with_lease_heartbeat(
            turn,
            owner_token=owner_token,
        )

    async def resume_turn_after_action(self, action_id: str):
        from app.repositories.agent_core_repo import AgentActionRepository

        action = await AgentActionRepository(self.turn_repo.session).get(action_id)
        if action is None:
            return None
        turn = await self.turn_repo.get_fresh(str(action.turn_id))
        if turn is None:
            return None
        if turn.status in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            return turn

        now = datetime.now(timezone.utc)
        owner_token = str(uuid4())
        turn = await self.turn_repo.claim_execution(
            str(turn.id),
            owner_token=owner_token,
            claimed_at=now,
            lease_until=now + _turn_lease_duration(),
        )
        if turn is None:
            return await self.turn_repo.get_fresh(str(action.turn_id))
        self._execution_owner_token = owner_token

        return await self._run_with_lease_heartbeat(
            turn,
            owner_token=owner_token,
            resume_action_id=action_id,
        )

    async def _run_with_lease_heartbeat(
        self,
        turn,
        *,
        owner_token: str,
        resume_action_id: str | None = None,
    ):
        turn_id = str(turn.id)
        heartbeat = _TurnLeaseHeartbeat(
            self.turn_repo.session,
            turn_id=turn_id,
            owner_token=owner_token,
        )
        try:
            async with heartbeat:
                return await self._run_claimed_turn(
                    turn,
                    owner_token=owner_token,
                    resume_action_id=resume_action_id,
                    heartbeat=heartbeat,
                )
        except asyncio.CancelledError as exc:
            if not heartbeat.ownership_lost and not is_lease_loss_cancellation(exc):
                raise
            await self.turn_repo.session.rollback()
            return await self.turn_repo.get_fresh(turn_id)
        finally:
            self._execution_owner_token = None

    async def _run_claimed_turn(
        self,
        turn,
        *,
        owner_token: str,
        resume_action_id: str | None,
        heartbeat: _TurnLeaseHeartbeat,
    ):
        now = datetime.now(timezone.utc)
        turn_id = str(turn.id)
        session = await self.session_repo.get(str(turn.session_id))
        if session is None:
            await heartbeat.stop()
            return await self._fail_turn(
                turn,
                error_message="Agent session could not be loaded for this turn.",
                error_code="session_not_found",
            )

        turn = await self.turn_repo.update_claimed_execution(
            turn_id,
            owner_token=owner_token,
            started_at=turn.started_at or now,
            completed_at=None,
            error_code=None,
            error_message=None,
        )
        if turn is None:
            return await self.turn_repo.get_fresh(turn_id)
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_STARTED,
            payload={"resume_action_id": resume_action_id}
            if resume_action_id is not None
            else {},
        )
        log_fields = {
            "session_id": str(turn.session_id),
            "turn_id": str(turn.id),
            "status": turn.status,
        }
        if resume_action_id is not None:
            log_fields["resume_action_id"] = resume_action_id
        logger.info("agent_core.turn.started", **log_fields)
        if resume_action_id is None:
            agent_metrics.increment("turns.started")

        resolved = await self._resolve_model_selection(turn=turn, session=session)
        if resolved is None:
            await heartbeat.stop()
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
            resume_action_id=resume_action_id,
        )
        fresh_turn = await self.turn_repo.get(str(turn.id))
        if fresh_turn is None:
            return None
        await heartbeat.stop()
        return await AgentLoopController(self.turn_repo.session).complete_turn_from_result(
            turn=fresh_turn,
            result=result,
            execution_owner_token=owner_token,
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
        try:
            validate_provider_transport(provider)
        except ValueError:
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
            scoped = sorted(
                (provider for provider in providers if provider.scope == scope),
                key=_default_provider_rank,
            )
            for provider in scoped:
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
        continuation_batch_id: str | None = None
        if resume_action_id is not None:
            from app.repositories.agent_core_repo import AgentActionRepository

            resume_action = await AgentActionRepository(self.turn_repo.session).get(
                resume_action_id
            )
            if resume_action is not None and resume_action.tool_batch_id:
                continuation_batch_id = str(resume_action.tool_batch_id)
        for attempt_index, candidate in enumerate(attempts):
            fresh_turn = await self.turn_repo.get(str(turn.id))
            if fresh_turn is not None:
                turn = fresh_turn
            turn = await self._persist_model_resolution(
                turn,
                candidate,
                attempt_index=attempt_index,
            )
            if turn is None:
                from app.services.agent_core.core.types import LoopResult

                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=0,
                    error_code="execution_claim_lost",
                    error_message="Agent turn execution lease ownership was lost.",
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
                agent_metrics.increment("models.fallbacks")

            if next_resume_action_id is not None:
                result = await controller.resume_turn_from_action(
                    action_id=next_resume_action_id,
                    provider=candidate["provider"],
                    model=candidate["model"],
                    capabilities=_resolved_capabilities(candidate),
                    strategy=runtime_strategy,
                    request_args=candidate["request_args"],
                    max_tokens=runtime_strategy.max_tokens,
                    continuation_failure_mode=(
                        "ready" if attempt_index < len(attempts) - 1 else "failed"
                    ),
                    execution_owner_token=self._execution_owner_token,
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
                    continuation_batch_id=continuation_batch_id,
                    continuation_failure_mode=(
                        "ready" if attempt_index < len(attempts) - 1 else "failed"
                    ),
                    execution_owner_token=self._execution_owner_token,
                )
            if not should_try_fallback(result) or attempt_index == len(attempts) - 1:
                return result
            if result.continuation_batch_id is not None:
                continuation_batch_id = result.continuation_batch_id
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
        if self._execution_owner_token is not None:
            updated = await self.turn_repo.update_claimed_execution(
                str(turn.id),
                owner_token=self._execution_owner_token,
                model_profile_snapshot=snapshot,
                lease_until=datetime.now(timezone.utc) + _turn_lease_duration(),
            )
            return updated
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
        values = dict(
            status=AgentTurnStatus.FAILED,
            final_text=None,
            completed_at=completed_at,
            termination_reason="model_failed",
            error_code=error_code,
            error_message=error_message,
            claimed_at=None,
            lease_until=None,
            lease_owner_token=None,
        )
        if self._execution_owner_token is not None:
            updated = await self.turn_repo.update_claimed_execution(
                str(turn.id),
                owner_token=self._execution_owner_token,
                **values,
            )
            if updated is None:
                return await self.turn_repo.get_fresh(str(turn.id))
            turn = updated
        else:
            turn = await self.turn_repo.update_all(turn, **values)
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_FAILED,
            payload={"error_message": error_message, "error_code": error_code},
        )
        logger.info(
            "agent_core.turn.failed",
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            status=turn.status,
            error_code=error_code,
            error_message=truncate_log_value(error_message),
        )
        agent_metrics.increment("turns.failed")
        return turn


_DEFAULT_PREFERRED_ENV_KINDS = {"vllm", "openai_compatible"}


def _default_provider_rank(provider) -> int:
    """Rank providers for default selection within a single scope.

    An explicitly env-managed OpenAI-compatible endpoint (vLLM or the generic
    openai_compatible template) is what a server deployment configures on
    purpose, so it must win over incidentally-available providers. Stable sort
    keeps the repository's recency ordering within each rank.
    """
    metadata = provider.provider_metadata or {}
    env_managed = metadata.get("envManaged") is True
    if env_managed and provider.kind in _DEFAULT_PREFERRED_ENV_KINDS:
        return 0
    return 1


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


def _turn_lease_heartbeat_interval() -> float:
    return max(_turn_lease_duration().total_seconds() / 3, 0.05)

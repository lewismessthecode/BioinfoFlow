from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.agent_core import AgentActionStatus, AgentTurnStatus
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentSessionRepository,
    AgentTurnRepository,
)
from app.repositories.llm_repo import (
    LlmModelProfileRepository,
    LlmModelRepository,
    LlmProviderCredentialRepository,
    LlmProviderRepository,
)
from app.services.agent_core.core import AgentLoopController, TurnLifecycle
from app.services.agent_core.approval_batches import (
    TERMINAL_ACTION_STATUSES,
    ordered_tool_call_batch,
)
from app.services.agent_core.core.fallback import should_try_fallback
from app.services.agent_core.core.model_resolver import (
    AgentModelResolver,
    default_provider_rank as _default_provider_rank_impl,
    resolved_runtime_strategy,
    target_identity_matches_snapshot as _target_identity_matches_snapshot_impl,
)
from app.services.agent_core.core.runtime_strategy import (
    RuntimeCapabilities,
    RuntimeStrategy,
)
from app.services.agent_core.events import AgentEventType, safe_agent_error_message
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.metrics import agent_metrics
from app.services.agent_core.observability import truncate_log_value
from app.services.agent_core.ownership import (
    TurnOwnership,
    TurnOwnershipLostError,
    new_turn_owner_token,
)
from app.services.agent_core.transcript.messages import (
    RESPONSES_CONTINUATION_METADATA_KEY,
    text_part,
)
from app.services.agent_core.transcript.store import AgentTranscriptStore
from app.services.authorization_service import AuthorizationService
from app.services.model_runtime.contracts import ModelTarget
from app.services.model_runtime.gateway import ModelGateway
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AgentCoreRuntime:
    def __init__(
        self,
        session: AsyncSession,
        *,
        model_gateway: ModelGateway | None = None,
    ):
        self.db = session
        self.turn_repo = AgentTurnRepository(session)
        self.session_repo = AgentSessionRepository(session)
        self.ledger = AgentEventLedger(session)
        self.llm_models = LlmModelRepository(session)
        self.llm_profiles = LlmModelProfileRepository(session)
        self.llm_providers = LlmProviderRepository(session)
        self.llm_credentials = LlmProviderCredentialRepository(session)
        self.authorization = AuthorizationService(session)
        self.model_gateway = model_gateway or ModelGateway()
        self.model_resolver = AgentModelResolver(
            llm_models=self.llm_models,
            llm_profiles=self.llm_profiles,
            llm_providers=self.llm_providers,
            llm_credentials=self.llm_credentials,
            authorization=self.authorization,
        )
        self.lifecycle = TurnLifecycle(
            read_after_ownership_loss=self._read_turn_after_ownership_loss,
            terminalize_unexpected_failure=self._terminalize_unexpected_turn_failure,
        )

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
            await self._release_active_if_terminal(turn)
            return turn

        session = await self.session_repo.get(str(turn.session_id))
        if session is None:
            return await self._fail_turn(
                turn,
                error_message="Agent session could not be loaded for this turn.",
                error_code="session_not_found",
            )
        if not await self.session_repo.claim_active_turn(
            str(turn.session_id),
            str(turn.id),
        ):
            return await self._fail_turn(
                turn,
                error_message="Another turn is already active in this session.",
                error_code="session_turn_in_progress",
            )

        now = datetime.now(timezone.utc)
        owner_token = new_turn_owner_token()
        turn, claimed = await self.turn_repo.claim_run(
            str(turn.id),
            owner_token=owner_token,
            claimed_at=now,
            lease_until=now + _turn_lease_duration(),
        )
        if turn is None or not claimed:
            return turn
        ownership = self._ownership(str(turn.id), owner_token)
        return await self.lifecycle.execute(
            turn_id=turn_id,
            ownership=ownership,
            operation=lambda: self._run_claimed_turn(
                turn=turn,
                session=session,
                ownership=ownership,
            ),
        )

    async def _read_turn_after_ownership_loss(self, turn_id: str):
        await self.turn_repo.session.rollback()
        turn = await self.turn_repo.get_fresh(turn_id)
        await self.turn_repo.session.commit()
        return turn

    async def _run_claimed_turn(self, *, turn, session, ownership: TurnOwnership):
        turn_id = str(turn.id)
        await ownership.ensure_current()
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_STARTED,
            payload={},
            expected_owner_token=ownership.owner_token,
        )
        if session.root_session_id is not None:
            await self._publish_child_running_best_effort(
                session_id=str(turn.session_id),
                turn_id=turn_id,
                expected_owner_token=ownership.owner_token,
            )
        logger.info(
            "agent_core.turn.started",
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            status=turn.status,
        )
        agent_metrics.increment("turns.started")

        resolved = await self._resolve_model_selection(turn=turn, session=session)
        if resolved is None:
            return await self._fail_turn(
                turn,
                error_message=(
                    "No usable model is configured. Select a provider/model in Settings, "
                    "or configure a deployment default."
                ),
                error_code="model_selection_missing",
                ownership=ownership,
            )

        result = await self._run_model_attempts(
            turn=turn,
            session=session,
            resolved=resolved,
            ownership=ownership,
        )
        result = await self._drain_durable_resume_intents(
            turn_id=turn_id,
            session=session,
            resolved=resolved,
            result=result,
            ownership=ownership,
        )
        fresh_turn = await self.turn_repo.get(turn_id)
        if fresh_turn is None:
            return None
        completed = await AgentLoopController(
            self.turn_repo.session,
            model_gateway=self.model_gateway,
            ownership=ownership,
        ).complete_turn_from_result(
            turn=fresh_turn,
            result=result,
        )
        await self._release_active_if_terminal(completed)
        await self._enqueue_persisted_resume_intent(completed)
        return completed

    async def resume_turn_after_action(self, action_id: str):
        action_repo = AgentActionRepository(self.turn_repo.session)
        action = await action_repo.get(action_id)
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
            await self._release_active_if_terminal(turn)
            return turn

        transcript = AgentTranscriptStore(self.turn_repo.session)
        current_batch = await transcript.latest_unresolved_tool_call_batch_ids(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
        )
        pending_call_ids = (turn.loop_state or {}).get("pending_tool_call_ids")
        eligible_call_ids = (
            [str(call_id) for call_id in pending_call_ids]
            if isinstance(pending_call_ids, list)
            else current_batch
        )
        if not action.tool_call_id or action.tool_call_id not in eligible_call_ids:
            return turn
        if action.status not in {
            AgentActionStatus.REQUESTED,
            AgentActionStatus.REJECTED,
        }:
            return turn
        if not await self.session_repo.claim_active_turn(
            str(turn.session_id),
            str(turn.id),
        ):
            return await self._fail_turn(
                turn,
                error_message="Another turn is already active in this session.",
                error_code="session_turn_in_progress",
            )

        now = datetime.now(timezone.utc)
        owner_token = new_turn_owner_token()
        turn, claimed = await self.turn_repo.claim_action_resume(
            str(turn.id),
            owner_token=owner_token,
            expected_resume_batch_token=turn.resume_batch_token,
            claimed_at=now,
            lease_until=now + _turn_lease_duration(),
        )
        if turn is None:
            return None
        if not claimed:
            return turn

        ownership = self._ownership(str(turn.id), owner_token)
        session = await self.session_repo.get(str(turn.session_id))
        if session is None:
            return await self._fail_turn(
                turn,
                error_message="Agent session could not be loaded for this turn.",
                error_code="session_not_found",
                ownership=ownership,
            )

        return await self.lifecycle.execute(
            turn_id=str(turn.id),
            ownership=ownership,
            operation=lambda: self._resume_claimed_turn(
                action_id=action_id,
                action_repo=action_repo,
                action=action,
                turn=turn,
                session=session,
                ownership=ownership,
            ),
        )

    async def _terminalize_unexpected_turn_failure(
        self,
        *,
        turn_id: str,
        ownership: TurnOwnership,
        exc: Exception,
    ):
        await self.db.rollback()
        logger.error(
            "agent_core.turn.unexpected_failure",
            turn_id=turn_id,
            exception_type=type(exc).__name__,
        )
        turn = await self.turn_repo.get_fresh(turn_id)
        if turn is None:
            return None
        if turn.status in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            await self._release_active_if_terminal(turn)
            return turn
        try:
            return await self._fail_turn(
                turn,
                error_message="The agent runtime failed unexpectedly.",
                error_code="agent_runtime_failed",
                ownership=ownership,
            )
        except TurnOwnershipLostError:
            return await self._read_turn_after_ownership_loss(turn_id)

    async def _resume_claimed_turn(
        self,
        *,
        action_id: str,
        action_repo: AgentActionRepository,
        action,
        turn,
        session,
        ownership: TurnOwnership,
    ):
        turn_id = str(turn.id)
        await ownership.ensure_current()
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_STARTED,
            payload={"resume_action_id": action_id},
            expected_owner_token=ownership.owner_token,
        )
        if session.root_session_id is not None:
            await self._publish_child_running_best_effort(
                session_id=str(turn.session_id),
                turn_id=turn_id,
                expected_owner_token=ownership.owner_token,
            )
        logger.info(
            "agent_core.turn.started",
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            status=turn.status,
            resume_action_id=action_id,
        )

        resolved = await self._resolve_resume_model_selection(
            turn=turn, session=session
        )
        if resolved is None:
            await self._close_failed_resume_action(
                action_repo=action_repo,
                action=action,
                turn=turn,
                session=session,
                ownership=ownership,
            )
            return await self._fail_turn(
                turn,
                error_message=(
                    "No usable model is configured. Select a provider/model in Settings, "
                    "or configure a deployment default."
                ),
                error_code="model_selection_missing",
                ownership=ownership,
            )
        result = await self._run_model_attempts(
            turn=turn,
            session=session,
            resolved=resolved,
            resume_action_id=action_id,
            ownership=ownership,
        )
        result = await self._drain_durable_resume_intents(
            turn_id=turn_id,
            session=session,
            resolved=resolved,
            result=result,
            ownership=ownership,
        )
        fresh_turn = await self.turn_repo.get(turn_id)
        if fresh_turn is None:
            return None
        completed = await AgentLoopController(
            self.turn_repo.session,
            model_gateway=self.model_gateway,
            ownership=ownership,
        ).complete_turn_from_result(
            turn=fresh_turn,
            result=result,
        )
        await self._release_active_if_terminal(completed)
        await self._enqueue_persisted_resume_intent(completed)
        return completed

    async def _publish_child_running_best_effort(
        self,
        *,
        session_id: str,
        turn_id: str,
        expected_owner_token: str,
    ) -> None:
        from app.services.agent_core.collaboration.service import (
            AgentCollaborationService,
        )

        error_type: str | None = None
        try:
            session_factory = async_sessionmaker(
                bind=self.db.bind,
                expire_on_commit=False,
                class_=AsyncSession,
            )
            async with session_factory() as event_session:
                try:
                    await AgentCollaborationService(
                        event_session
                    ).publish_child_running(
                        turn_id=turn_id,
                        expected_owner_token=expected_owner_token,
                    )
                except Exception as exc:
                    error_type = type(exc).__name__
                    try:
                        await event_session.rollback()
                    except Exception:
                        pass
        except Exception as exc:
            if error_type is None:
                error_type = type(exc).__name__
        if error_type is not None:
            try:
                logger.warning(
                    "agent_core.child_lifecycle_publish_failed",
                    event_type=AgentEventType.AGENT_RUNNING,
                    session_id=session_id,
                    turn_id=turn_id,
                    error_type=error_type,
                )
            except Exception:
                pass

    async def _drain_durable_resume_intents(
        self,
        *,
        turn_id: str,
        session,
        resolved: dict[str, Any],
        result,
        ownership: TurnOwnership,
    ):
        for _ in range(128):
            if result.termination_reason != "waiting_approval":
                return result
            await ownership.ensure_current()
            turn = await self.turn_repo.get_fresh(turn_id)
            if turn is None:
                return result
            action = await self._next_persisted_resume_action(turn)
            if action is None:
                return result
            result = await self._run_model_attempts(
                turn=turn,
                session=session,
                resolved=resolved,
                resume_action_id=str(action.id),
                ownership=ownership,
            )
        raise RuntimeError("Agent turn exceeded the durable resume drain limit")

    async def _next_persisted_resume_action(self, turn):
        token = str(turn.resume_batch_token or "")
        actions = await AgentActionRepository(self.turn_repo.session).list_open_for_turn(
            str(turn.id)
        )
        candidates = [
            action
            for action in actions
            if action.requires_resume
            and action.status
            in {AgentActionStatus.REQUESTED, AgentActionStatus.REJECTED}
        ]
        if token:
            matching = [
                action
                for action in candidates
                if str(action.tool_batch_id or "") == token
            ]
            if matching:
                candidates = matching
        return candidates[0] if candidates else None

    async def _enqueue_persisted_resume_intent(self, turn) -> None:
        if turn is None or turn.status != AgentTurnStatus.WAITING_APPROVAL:
            return
        action = await self._next_persisted_resume_action(turn)
        if action is None:
            return
        from app.services.agent_core.runner import enqueue_turn_resume

        enqueue_turn_resume(str(action.id), str(turn.id), str(turn.session_id))

    async def _close_failed_resume_action(
        self,
        *,
        action_repo: AgentActionRepository,
        action,
        turn,
        session,
        ownership: TurnOwnership,
    ) -> None:
        transcript = AgentTranscriptStore(
            self.turn_repo.session,
            owned_turn_id=str(turn.id),
            expected_owner_token=ownership.owner_token,
        )
        batch = await ordered_tool_call_batch(
            action_repo=action_repo,
            transcript=transcript,
            action=action,
        )
        config_error = {
            "type": "ModelConfigurationChanged",
            "message": (
                "The model configuration changed while approval was pending; "
                "the tool was not executed."
            ),
        }
        now = datetime.now(timezone.utc)
        for sibling in batch:
            await ownership.ensure_current()
            matching_tool_result = await transcript.find_committed_tool_result(
                session_id=str(session.id),
                turn_id=str(turn.id),
                tool_call_id=sibling.tool_call_id,
            )
            if sibling.status in TERMINAL_ACTION_STATUSES:
                error = sibling.error
                if sibling.status == AgentActionStatus.REJECTED and not error:
                    error = {
                        "type": "UserRejected",
                        "message": "The user rejected this tool call.",
                    }
                if matching_tool_result is None:
                    await self._append_failed_resume_tool_result(
                        transcript=transcript,
                        session=session,
                        turn=turn,
                        action=sibling,
                        status=sibling.status,
                        result=sibling.result,
                        error=error,
                    )
                if sibling.requires_resume or sibling.completed_at is None:
                    updated, owned = await action_repo.update_all_owned(
                        sibling,
                        expected_owner_token=ownership.owner_token,
                        requires_resume=False,
                        completed_at=sibling.completed_at or now,
                    )
                    if not owned or updated is None:
                        raise TurnOwnershipLostError(
                            "Agent turn ownership was replaced"
                        )
                continue

            if matching_tool_result is None:
                await self._append_failed_resume_tool_result(
                    transcript=transcript,
                    session=session,
                    turn=turn,
                    action=sibling,
                    status=AgentActionStatus.FAILED,
                    result=None,
                    error=config_error,
                )
            sibling, owned = await action_repo.update_all_owned(
                sibling,
                expected_owner_token=ownership.owner_token,
                status=AgentActionStatus.FAILED,
                error=config_error,
                completed_at=now,
                requires_resume=False,
            )
            if not owned or sibling is None:
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
            await self.ledger.append(
                session_id=str(sibling.session_id),
                turn_id=str(sibling.turn_id),
                type=AgentEventType.ACTION_FAILED,
                payload={"action_id": str(sibling.id), "error": config_error},
                expected_owner_token=ownership.owner_token,
            )
            agent_metrics.increment("tools.failed")
        await transcript.clear_session_metadata(
            session_id=str(session.id),
            metadata_key=RESPONSES_CONTINUATION_METADATA_KEY,
        )

    async def _append_failed_resume_tool_result(
        self,
        *,
        transcript: AgentTranscriptStore,
        session,
        turn,
        action,
        status: str,
        result,
        error,
    ) -> None:
        await transcript.append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="tool",
            parts=[
                text_part(
                    json.dumps(
                        {
                            "tool": action.name,
                            "status": status,
                            "result": result,
                            "error": error,
                        },
                        separators=(",", ":"),
                        default=str,
                    )
                )
            ],
            metadata={
                "tool_call_id": action.tool_call_id,
                "tool": action.name,
                "is_error": bool(error) or status != AgentActionStatus.COMPLETED,
            },
        )

    async def _resolve_model_selection(self, *, turn, session) -> dict[str, Any] | None:
        return await self.model_resolver.resolve_selection(turn=turn, session=session)

    async def _resolve_resume_model_selection(
        self,
        *,
        turn,
        session,
    ) -> dict[str, Any] | None:
        return await self.model_resolver.resolve_resume_selection(
            turn=turn,
            session=session,
        )

    async def _catalog_selection(
        self,
        selection: dict[str, str] | None,
        *,
        source: str,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        return await self.model_resolver.catalog_selection(
            selection,
            source=source,
            workspace_id=workspace_id,
            user_id=user_id,
        )

    async def _catalog_default_selection(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        return await self.model_resolver.catalog_default_selection(
            workspace_id=workspace_id,
            user_id=user_id,
        )

    async def _run_model_attempts(
        self,
        *,
        turn,
        session,
        resolved: dict[str, Any],
        resume_action_id: str | None = None,
        ownership: TurnOwnership,
    ):
        controller = AgentLoopController(
            self.turn_repo.session,
            model_gateway=self.model_gateway,
            ownership=ownership,
        )
        attempts = [
            resolved,
            *await self._resolve_fallback_candidates(
                turn=turn, session=session, resolved=resolved
            ),
        ]
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
            await ownership.ensure_current()
            fresh_turn = await self.turn_repo.get(str(turn.id))
            if fresh_turn is not None:
                turn = fresh_turn
            turn = await self._persist_model_resolution(
                turn,
                candidate,
                attempt_index=attempt_index,
                ownership=ownership,
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
            runtime_strategy = _resolved_runtime_strategy(candidate, turn=turn)
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
                    expected_owner_token=ownership.owner_token,
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
                    expected_owner_token=ownership.owner_token,
                )
                agent_metrics.increment("models.fallbacks")

            if next_resume_action_id is not None:
                result = await controller.resume_turn_from_action(
                    action_id=next_resume_action_id,
                    target=_model_target(candidate),
                    capabilities=_resolved_capabilities(candidate),
                    strategy=runtime_strategy,
                    max_tokens=runtime_strategy.max_tokens,
                    continuation_failure_mode=(
                        "ready" if attempt_index < len(attempts) - 1 else "failed"
                    ),
                )
                next_resume_action_id = None
            else:
                result = await controller.run_turn(
                    turn_id=str(turn.id),
                    target=_model_target(candidate),
                    capabilities=_resolved_capabilities(candidate),
                    strategy=runtime_strategy,
                    max_tokens=runtime_strategy.max_tokens,
                    continuation_batch_id=continuation_batch_id,
                    continuation_failure_mode=(
                        "ready" if attempt_index < len(attempts) - 1 else "failed"
                    ),
                )
            if not should_try_fallback(result) or attempt_index == len(attempts) - 1:
                return result
            if result.continuation_batch_id is not None:
                continuation_batch_id = result.continuation_batch_id
        raise RuntimeError(
            "Agent runtime exhausted model attempts without returning a result."
        )

    async def _persist_model_resolution(
        self,
        turn,
        resolved: dict[str, Any],
        *,
        attempt_index: int,
        ownership: TurnOwnership,
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
        request_args = resolved.get("request_args") or {}
        snapshot["resolved_model_target"] = {
            "endpoint_id": str(resolved.get("endpoint_id") or ""),
            "provider_kind": resolved["provider"],
            "model_name": resolved["model"],
            "wire_protocol": resolved.get("wire_protocol") or "chat_completions",
            "base_url": request_args.get("api_base"),
        }
        snapshot["_resolved_model_target_revision"] = resolved.get("target_revision")
        if resolved.get("model_id"):
            snapshot["resolved_model_id"] = resolved["model_id"]
        if resolved.get("profile_id"):
            snapshot["resolved_profile_id"] = resolved["profile_id"]
        snapshot["resolved_model_source"] = resolved["source"]
        snapshot["resolved_model_capabilities"] = resolved.get("capabilities", {})
        snapshot["resolved_runtime_strategy"] = _resolved_runtime_strategy(
            resolved,
            turn=turn,
        ).as_dict()
        updated_turn, updated = await self.turn_repo.update_owned(
            str(turn.id),
            expected_owner_token=ownership.owner_token,
            model_profile_snapshot=snapshot,
            lease_until=datetime.now(timezone.utc) + _turn_lease_duration(),
        )
        if not updated or updated_turn is None:
            raise TurnOwnershipLostError("Agent turn ownership was replaced")
        return updated_turn

    async def _resolve_fallback_candidates(
        self,
        *,
        turn,
        session,
        resolved: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return await self.model_resolver.resolve_fallback_candidates(
            turn=turn,
            session=session,
            resolved=resolved,
        )

    async def _fail_turn(
        self,
        turn,
        *,
        error_message: str,
        error_code: str,
        ownership: TurnOwnership | None = None,
    ):
        error_message = safe_agent_error_message(
            error_code,
            error_message,
            allow_non_model_detail=True,
        )
        completed_at = datetime.now(timezone.utc)
        values = {
            "status": AgentTurnStatus.FAILED,
            "accepts_steer": False,
            "final_text": None,
            "completed_at": completed_at,
            "termination_reason": "model_failed",
            "error_code": error_code,
            "error_message": error_message,
            "claimed_at": None,
            "lease_until": None,
            "owner_token": None,
            "resume_batch_token": None,
        }
        if ownership is None:
            turn = await self.turn_repo.update_all(turn, **values)
        else:
            turn, updated = await self.turn_repo.update_owned(
                str(turn.id),
                expected_owner_token=ownership.owner_token,
                **values,
            )
            if not updated or turn is None:
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
        session_factory = async_sessionmaker(
            bind=self.turn_repo.session.bind,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        async with session_factory() as boundary_session:
            await AgentTranscriptStore(boundary_session).cancel_pending_steers(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                reason="model_failed",
            )
        await self._release_active_if_terminal(turn)
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

    async def _release_active_if_terminal(self, turn) -> None:
        if turn is None or turn.status not in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            return
        await self.session_repo.release_active_turn(str(turn.session_id), str(turn.id))
        from app.services.agent_core.collaboration.service import (
            AgentCollaborationService,
        )

        await AgentCollaborationService(
            self.turn_repo.session
        ).publish_child_terminal(turn_id=str(turn.id))

    def _ownership(self, turn_id: str, owner_token: str) -> TurnOwnership:
        bind = self.turn_repo.session.bind
        if bind is None:
            raise RuntimeError("Agent turn ownership requires a bound database session")
        return TurnOwnership(
            bind=bind,
            turn_id=turn_id,
            owner_token=owner_token,
            lease_duration=_turn_lease_duration(),
        )


def _default_provider_rank(provider) -> int:
    """Compatibility delegator for historical runtime tests and callers."""
    return _default_provider_rank_impl(provider)


def _resolved_capabilities(resolved: dict[str, Any]) -> RuntimeCapabilities:
    capabilities = resolved.get("capabilities")
    if not isinstance(capabilities, dict):
        return RuntimeCapabilities()
    return RuntimeCapabilities(
        supports_streaming=bool(capabilities.get("supports_streaming", True)),
        supports_reasoning=bool(capabilities.get("supports_reasoning", False)),
        supports_tools=bool(capabilities.get("supports_tools", True)),
    )


def _resolved_runtime_strategy(
    resolved: dict[str, Any],
    *,
    turn=None,
) -> RuntimeStrategy:
    strategy = resolved_runtime_strategy(resolved)
    reasoning_effort = _turn_reasoning_effort(turn)
    if reasoning_effort is None:
        reasoning_effort = strategy.reasoning_effort
        if reasoning_effort is None and strategy.allow_thinking:
            reasoning_effort = "medium"
    return RuntimeStrategy(
        use_streaming=strategy.use_streaming,
        allow_thinking=strategy.allow_thinking,
        allow_tools=strategy.allow_tools,
        max_tokens=strategy.max_tokens,
        reasoning_budget=strategy.reasoning_budget,
        reasoning_effort=reasoning_effort,
        fallback_model_ids=strategy.fallback_model_ids,
    )


def _turn_reasoning_effort(turn) -> str | None:
    if turn is None:
        return None
    snapshot = getattr(turn, "model_profile_snapshot", None)
    metadata = snapshot.get("metadata") if isinstance(snapshot, dict) else None
    collaboration = metadata.get("collaboration") if isinstance(metadata, dict) else None
    effort = collaboration.get("reasoning_effort") if isinstance(collaboration, dict) else None
    return effort if effort in {"low", "medium", "high"} else None


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _model_target(resolved: dict[str, Any]) -> ModelTarget:
    request_args = resolved.get("request_args") or {}
    return ModelTarget(
        endpoint_id=str(resolved.get("endpoint_id") or resolved.get("model_id") or ""),
        provider_kind=str(resolved["provider"]),
        model_name=str(resolved["model"]),
        routed_model_name=str(resolved["routed_model_name"]),
        wire_protocol=str(resolved.get("wire_protocol") or "chat_completions"),
        base_url=request_args.get("api_base"),
        network_access=str(resolved.get("network_access") or "unrestricted"),
        api_key=request_args.get("api_key"),
        target_revision=resolved.get("target_revision"),
    )


def _target_identity_matches_snapshot(
    resolved: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    expected_target_revision: object,
) -> bool:
    return _target_identity_matches_snapshot_impl(
        resolved,
        snapshot,
        expected_target_revision=expected_target_revision,
    )


def _turn_lease_duration() -> timedelta:
    seconds = max(int(getattr(settings, "agent_turn_lease_seconds", 300) or 300), 1)
    return timedelta(seconds=seconds)

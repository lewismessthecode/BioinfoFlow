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
from app.services.agent_core.core import AgentLoopController
from app.services.agent_core.approval_batches import (
    TERMINAL_ACTION_STATUSES,
    ordered_tool_call_batch,
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
from app.services.llm.access_policy import (
    authorize_server_environment_credential,
    resolve_provider_network_access,
)
from app.services.llm.provider_templates import (
    normalize_provider_base_url,
    route_provider_model_name,
)
from app.services.llm.credentials import (
    derive_model_target_revision,
    resolve_credential_material,
)
from app.services.llm.catalog import (
    _provider_requires_credential,
    validate_provider_transport,
)
from app.services.llm.credentials import credential_available, credential_configured
from app.services.model_runtime.contracts import ModelTarget
from app.services.model_runtime.gateway import ModelGateway
from app.utils.authorization import can_manage_server_integrations
from app.utils.exceptions import PermissionDeniedError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AgentCoreRuntime:
    def __init__(
        self,
        session: AsyncSession,
        *,
        model_gateway: ModelGateway | None = None,
    ):
        self.turn_repo = AgentTurnRepository(session)
        self.session_repo = AgentSessionRepository(session)
        self.ledger = AgentEventLedger(session)
        self.llm_models = LlmModelRepository(session)
        self.llm_profiles = LlmModelProfileRepository(session)
        self.llm_providers = LlmProviderRepository(session)
        self.llm_credentials = LlmProviderCredentialRepository(session)
        self.authorization = AuthorizationService(session)
        self.model_gateway = model_gateway or ModelGateway()

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
        async with ownership.maintain():
            try:
                return await self._run_claimed_turn(
                    turn=turn,
                    session=session,
                    ownership=ownership,
                )
            except TurnOwnershipLostError:
                return await self._read_turn_after_ownership_loss(str(turn.id))

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

        async with ownership.maintain():
            try:
                return await self._resume_claimed_turn(
                    action_id=action_id,
                    action_repo=action_repo,
                    action=action,
                    turn=turn,
                    session=session,
                    ownership=ownership,
                )
            except TurnOwnershipLostError:
                return await self._read_turn_after_ownership_loss(str(turn.id))

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
        snapshot = turn.model_profile_snapshot or {}
        candidates: list[tuple[str, dict[str, str] | None]] = [
            (
                "turn_profile",
                normalize_model_selection(
                    {"profile_id": snapshot.get("requested_model_profile_id")}
                ),
            ),
            (
                "turn",
                normalize_model_selection(snapshot.get("requested_model_selection")),
            ),
            (
                "session",
                session_model_selection_from_metadata(
                    getattr(session, "session_metadata", None)
                ),
            ),
            (
                "session_profile",
                normalize_model_selection(
                    {"profile_id": session.default_model_profile_id}
                ),
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

    async def _resolve_resume_model_selection(
        self,
        *,
        turn,
        session,
    ) -> dict[str, Any] | None:
        snapshot = turn.model_profile_snapshot or {}
        resolved_model_id = snapshot.get("resolved_model_id")
        if not resolved_model_id:
            return await self._resolve_model_selection(turn=turn, session=session)
        candidate = await self._catalog_selection(
            {"model_id": str(resolved_model_id)},
            source="turn_resolved_resume",
            workspace_id=str(session.workspace_id),
            user_id=turn.user_id,
        )
        if candidate is None:
            return None
        resolved_target = snapshot.get("resolved_model_target")
        if isinstance(resolved_target, dict):
            if not _target_identity_matches_snapshot(
                candidate,
                resolved_target,
                expected_target_revision=snapshot.get(
                    "_resolved_model_target_revision"
                ),
            ):
                return None
        capabilities = snapshot.get("resolved_model_capabilities")
        if isinstance(capabilities, dict):
            candidate["capabilities"] = capabilities
        runtime_strategy = snapshot.get("resolved_runtime_strategy")
        if isinstance(runtime_strategy, dict):
            candidate["runtime_strategy"] = runtime_strategy
        return candidate

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
        role = await self.authorization.resolve_workspace_role(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        server_authorized = _provider_has_server_integration_authority(
            provider,
            role=role,
        )
        try:
            network_access = await resolve_provider_network_access(
                provider.base_url,
                private_endpoint_authorized=server_authorized,
                # Untrusted member-owned endpoints get an early DNS check.
                # Trusted/shared configurations still use public_only for
                # public URLs, whose request transport pins and revalidates DNS.
                resolve_dns=not server_authorized,
            )
        except PermissionDeniedError:
            return None
        try:
            validate_provider_transport(provider)
        except ValueError:
            return None
        credential = await self.llm_credentials.get_for_provider(str(provider.id))
        if (
            not server_authorized
            and credential is not None
            and credential.source == "env"
        ):
            try:
                authorize_server_environment_credential(role=role)
            except PermissionDeniedError:
                return None
        if not credential_available(
            credential,
            credential_required=_provider_requires_credential(provider),
        ):
            return None
        material = resolve_credential_material(credential)
        wire_protocol = str(getattr(provider, "wire_protocol", "chat_completions"))
        routed_model_name = route_provider_model_name(
            provider.kind,
            model.model_id,
            wire_protocol=wire_protocol,
        )
        normalized_base_url = (
            normalize_provider_base_url(provider.kind, provider.base_url)
            if provider.base_url
            else None
        )
        target_revision = derive_model_target_revision(
            endpoint_id=str(provider.id),
            provider_kind=str(provider.kind),
            model_name=str(model.model_id),
            wire_protocol=wire_protocol,
            routed_model_name=routed_model_name,
            base_url=normalized_base_url,
            credential_material=material,
        )
        request_args: dict[str, Any] = {}
        if material.api_key:
            request_args["api_key"] = material.api_key
        if normalized_base_url:
            # Per-kind normalization keeps native base URLs intact (Anthropic
            # and Gemini stay at the host root; only OpenAI-compatible providers
            # get the /v1 suffix), so LiteLLM receives a valid api_base.
            request_args["api_base"] = normalized_base_url
        capabilities = capabilities_from_model(model)
        runtime_strategy = resolve_runtime_strategy(
            capabilities=capabilities,
            profile=profile if profile_id else None,
        )
        result = {
            "endpoint_id": str(provider.id),
            "provider": provider.kind,
            "model": model.model_id,
            "routed_model_name": routed_model_name,
            "model_id": str(model.id),
            "source": source,
            "capabilities": capabilities.as_dict(),
            "runtime_strategy": runtime_strategy.as_dict(),
            "request_args": request_args,
            "wire_protocol": wire_protocol,
            "target_revision": target_revision,
            "network_access": network_access,
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
                credential = await self.llm_credentials.get_for_provider(
                    str(provider.id)
                )
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
                for model in models:
                    candidate = await self._catalog_selection(
                        {"model_id": str(model.id)},
                        source="catalog_default",
                        workspace_id=workspace_id,
                        user_id=user_id,
                    )
                    if candidate is not None:
                        return candidate
        return None

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
        snapshot["resolved_runtime_strategy"] = resolved.get("runtime_strategy", {})
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

    async def _fail_turn(
        self,
        turn,
        *,
        error_message: str,
        error_code: str,
        ownership: TurnOwnership | None = None,
    ):
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


def _provider_has_server_integration_authority(provider, *, role: str | None) -> bool:
    return str(getattr(provider, "scope", "user") or "user") in {
        "global",
        "workspace",
    } or can_manage_server_integrations(role)


def _target_identity_matches_snapshot(
    resolved: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    expected_target_revision: object,
) -> bool:
    if not isinstance(expected_target_revision, str) or not expected_target_revision:
        return False
    request_args = resolved.get("request_args") or {}
    return resolved.get("target_revision") == expected_target_revision and {
        "endpoint_id": str(resolved.get("endpoint_id") or ""),
        "provider_kind": resolved.get("provider"),
        "model_name": resolved.get("model"),
        "wire_protocol": resolved.get("wire_protocol") or "chat_completions",
        "base_url": request_args.get("api_base"),
    } == {
        "endpoint_id": snapshot.get("endpoint_id"),
        "provider_kind": snapshot.get("provider_kind"),
        "model_name": snapshot.get("model_name"),
        "wire_protocol": snapshot.get("wire_protocol") or "chat_completions",
        "base_url": snapshot.get("base_url"),
    }


def _turn_lease_duration() -> timedelta:
    seconds = max(int(getattr(settings, "agent_turn_lease_seconds", 300) or 300), 1)
    return timedelta(seconds=seconds)

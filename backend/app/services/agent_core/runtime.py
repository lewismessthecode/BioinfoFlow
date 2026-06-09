from __future__ import annotations

import os
from datetime import datetime, timezone
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
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.model_selection import (
    normalize_model_selection,
    session_model_selection_from_metadata,
)
from app.services.llm.providers import (
    PROVIDER_REGISTRY,
    litellm_model_name,
    normalize_ollama_base_url,
    normalize_openai_compatible_base_url,
)
from app.services.llm.credentials import resolve_credential_material
from app.services.user_settings_service import UserSettingsService

_ORIGINAL_ACOMPLETION = acompletion


class AgentCoreRuntime:
    def __init__(self, session: AsyncSession):
        self.turn_repo = AgentTurnRepository(session)
        self.session_repo = AgentSessionRepository(session)
        self.ledger = AgentEventLedger(session)
        self.user_settings = UserSettingsService(session)
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
            started_at=now,
            error_code=None,
            error_message=None,
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

        snapshot = dict(turn.model_profile_snapshot or {})
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
        turn = await self.turn_repo.update_all(turn, model_profile_snapshot=snapshot)
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.MODEL_SELECTED,
            payload={
                "provider": resolved["provider"],
                "model": resolved["model"],
                "source": resolved["source"],
            },
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.ASSISTANT_THINKING_SUMMARY,
            payload={
                "summary": (
                    f"Routing this turn to {resolved['provider']} / {resolved['model']} "
                    f"from {resolved['source']}."
                )
            },
        )

        if acompletion is not _ORIGINAL_ACOMPLETION:
            loop_module.acompletion = acompletion
        result = await AgentLoopController(self.turn_repo.session).run_turn(
            turn_id=str(turn.id),
            provider=resolved["provider"],
            model=resolved["model"],
            supports_tools=_resolved_supports_tools(resolved),
            request_args=resolved.get("request_args")
            or await self._provider_request_args(
                user_id=turn.user_id,
                provider=resolved["provider"],
                model=resolved["model"],
            ),
        )
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
        result = await AgentLoopController(self.turn_repo.session).resume_turn_from_action(
            action_id=action_id,
            provider=resolved["provider"],
            model=resolved["model"],
            supports_tools=_resolved_supports_tools(resolved),
            request_args=resolved.get("request_args")
            or await self._provider_request_args(
                user_id=turn.user_id,
                provider=resolved["provider"],
                model=resolved["model"],
            ),
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
            ("turn", normalize_model_selection(snapshot.get("requested_model_selection"))),
            (
                "session",
                session_model_selection_from_metadata(
                    getattr(session, "session_metadata", None)
                ),
            ),
            ("user_settings", await self._user_settings_selection(turn.user_id)),
            ("deployment_default", self._deployment_default_selection()),
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
                source in {"turn", "session"}
                and selection
                and (selection.get("model_id") or selection.get("profile_id"))
            ):
                return None
            if selection and selection.get("provider") and selection.get("model"):
                return {
                    "provider": selection["provider"],
                    "model": selection["model"],
                    "source": source,
                }
        return None

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
        material = resolve_credential_material(credential)
        request_args: dict[str, Any] = {}
        if material.api_key:
            request_args["api_key"] = material.api_key
        if provider.base_url:
            if provider.kind == "ollama":
                request_args["api_base"] = normalize_ollama_base_url(provider.base_url)
            else:
                request_args["api_base"] = normalize_openai_compatible_base_url(
                    provider.base_url,
                    prefer_loopback_ip=provider.kind == "vllm",
                )
        result = {
            "provider": provider.kind,
            "model": model.model_id,
            "model_id": str(model.id),
            "source": source,
            "capabilities": {
                "supports_tools": bool(model.supports_tools),
            },
            "request_args": request_args,
        }
        if profile_id:
            result["profile_id"] = profile_id
        return result

    async def _user_settings_selection(self, user_id: str) -> dict[str, str] | None:
        settings_payload = await self.user_settings.get_settings(user_id)
        if not settings_payload.selected_model:
            return None
        return normalize_model_selection(
            {
                "provider": settings_payload.selected_provider,
                "model": settings_payload.selected_model,
            }
        )

    def _deployment_default_selection(self) -> dict[str, str] | None:
        model = str(settings.agent_model or "").strip()
        provider = str(settings.agent_provider or "").strip().lower()
        if not model and provider in PROVIDER_REGISTRY:
            model = PROVIDER_REGISTRY[provider].default_model
        if not model:
            return None
        return normalize_model_selection({"provider": provider, "model": model})

    async def _generate_text(
        self,
        *,
        session,
        turn,
        provider: str,
        model: str,
    ) -> tuple[str, dict[str, Any] | None]:
        request_args = await self._provider_request_args(
            user_id=turn.user_id,
            provider=provider,
            model=model,
        )
        response = await acompletion(
            model=litellm_model_name(provider, model),
            messages=await self._build_messages(session_id=str(session.id), turn=turn),
            max_tokens=settings.agent_max_tokens,
            **request_args,
        )
        final_text = self._extract_response_text(response)
        if not final_text:
            raise RuntimeError(
                "The selected model completed without returning visible text."
            )
        return final_text, self._extract_token_usage(response)

    async def _provider_request_args(
        self,
        *,
        user_id: str,
        provider: str,
        model: str,
    ) -> dict[str, Any]:
        cfg = PROVIDER_REGISTRY.get(provider)
        if cfg is None:
            if provider in {"openai_compatible", "vllm", "ollama"}:
                return {}
            raise RuntimeError(f"Unsupported model provider: {provider}")

        credentials = await self.user_settings.get_raw_credentials(user_id, provider)
        request_args: dict[str, Any] = {}

        api_key = str(credentials.get("api_key") or "").strip()
        if not api_key:
            api_key = str(cfg.static_api_key or "").strip()
        if not api_key and cfg.env_key_var:
            api_key = str(os.getenv(cfg.env_key_var) or "").strip()
        if provider == "anthropic" and not api_key:
            api_key = str(os.getenv("ANTHROPIC_AUTH_TOKEN") or "").strip()
        if api_key:
            request_args["api_key"] = api_key

        base_url = str(credentials.get("base_url") or "").strip()
        if not base_url and cfg.env_base_url_var:
            base_url = str(os.getenv(cfg.env_base_url_var) or "").strip()
        if not base_url:
            base_url = str(cfg.base_url or "").strip()
        if provider == "ollama" and base_url:
            base_url = normalize_ollama_base_url(base_url)
        elif cfg.prefix == "openai/" and base_url:
            base_url = normalize_openai_compatible_base_url(base_url)
        if base_url:
            request_args["api_base"] = base_url

        if provider == "openai" and model.startswith("gpt-5"):
            request_args["reasoning_effort"] = settings.agent_thinking_effort

        return request_args

    async def _build_messages(self, *, session_id: str, turn) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        try:
            prior_turns = await self.turn_repo.list_for_session(session_id)
        except Exception:
            prior_turns = []
        messages.append(
            {
                "role": "system",
                "content": (
                    "You are Bioinfoflow AgentCore, a concise bioinformatics assistant. "
                    "Answer directly, stay accurate, and mention uncertainty plainly."
                ),
            }
        )
        for prior_turn in prior_turns:
            if str(prior_turn.id) == str(turn.id):
                continue
            if prior_turn.input_text:
                messages.append({"role": "user", "content": prior_turn.input_text})
            if prior_turn.final_text:
                messages.append({"role": "assistant", "content": prior_turn.final_text})
        messages.append({"role": "user", "content": turn.input_text})
        return messages

    def _extract_response_text(self, response: Any) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                else:
                    text = getattr(item, "text", None)
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            return "\n".join(parts).strip()
        return ""

    def _extract_token_usage(self, response: Any) -> dict[str, Any] | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        if isinstance(usage, dict):
            return usage
        return {
            key: value
            for key, value in vars(usage).items()
            if not key.startswith("_")
        }

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
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_FAILED,
            payload={"error_message": error_message, "error_code": error_code},
        )
        return turn


def _resolved_supports_tools(resolved: dict[str, Any]) -> bool:
    capabilities = resolved.get("capabilities")
    if not isinstance(capabilities, dict):
        return True
    return bool(capabilities.get("supports_tools", True))

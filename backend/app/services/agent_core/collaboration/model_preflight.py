from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_core.collaboration.contracts import AgentModelChoice
from app.services.llm.catalog import LlmCatalogService


_REASONING_EFFORTS = frozenset({"low", "medium", "high"})


class AgentModelPreflight:
    def __init__(self, session: AsyncSession):
        self.catalog = LlmCatalogService(session)

    async def resolve(
        self,
        *,
        requested_model: str | None,
        parent_model_id: str,
        parent_reasoning_effort: str | None,
        workspace_id: str,
        user_id: str,
        parent_model: str | None = None,
        requested_reasoning_effort: str | None = None,
        parent_supports_reasoning: bool | None = None,
        role: str | None = None,
    ) -> AgentModelChoice:
        parent_name = parent_model or parent_model_id
        if requested_model is None:
            _validate_reasoning_value(requested_reasoning_effort)
            if requested_reasoning_effort is not None:
                supports_reasoning = parent_supports_reasoning
                if supports_reasoning is None:
                    supports_reasoning = (
                        await self.catalog.visible_model_supports_reasoning(
                            parent_model_id,
                            workspace_id=workspace_id,
                            user_id=user_id,
                        )
                    )
                if supports_reasoning is not True:
                    raise ValueError("unsupported_reasoning_effort")
            effort = requested_reasoning_effort or parent_reasoning_effort
            return AgentModelChoice(
                requested_model=None,
                effective_model=parent_name,
                effective_model_id=parent_model_id,
                reasoning_effort=effort,
                fallback=False,
                fallback_reason=None,
            )

        availability = await self.catalog.probe_exact_model(
            requested_model,
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
        )
        if not availability.available:
            return AgentModelChoice(
                requested_model=requested_model,
                effective_model=parent_name,
                effective_model_id=parent_model_id,
                reasoning_effort=parent_reasoning_effort,
                fallback=True,
                fallback_reason="requested_model_unavailable",
            )

        _validate_reasoning_value(requested_reasoning_effort)
        if requested_reasoning_effort and not availability.supports_reasoning:
            raise ValueError("unsupported_reasoning_effort")
        effort = (
            requested_reasoning_effort
            if requested_reasoning_effort is not None
            else parent_reasoning_effort if availability.supports_reasoning else None
        )
        return AgentModelChoice(
            requested_model=requested_model,
            effective_model=availability.model_name or requested_model,
            effective_model_id=availability.model_id or requested_model,
            reasoning_effort=effort,
            fallback=False,
            fallback_reason=None,
        )


def _validate_reasoning_value(value: str | None) -> None:
    if value is not None and value not in _REASONING_EFFORTS:
        raise ValueError("invalid_reasoning_effort")

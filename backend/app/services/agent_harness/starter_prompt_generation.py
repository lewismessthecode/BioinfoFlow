from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol, TypeAlias

from app.services.agent_harness.starter_prompts import (
    StarterPromptGenerationRequest,
    project_prompt_generation_context,
)
from app.services.agent_harness.model_resolver import AgentModelResolver
from app.services.agent_harness.model_target import model_target_from_resolved
from app.repositories.llm_repo import (
    LlmModelProfileRepository,
    LlmModelRepository,
    LlmProviderCredentialRepository,
    LlmProviderRepository,
)
from app.services.authorization_service import AuthorizationService
from app.services.model_runtime.contracts import (
    ModelInvocation,
    ModelTarget,
    ReasoningRequest,
    TextDelta,
    TextPart,
)
from app.services.model_runtime.gateway import ModelGateway


logger = logging.getLogger(__name__)
StarterPromptTargetResolver: TypeAlias = Callable[[], Awaitable[ModelTarget | None]]


class StarterPromptGateway(Protocol):
    def invoke(self, invocation: ModelInvocation): ...


_INSTRUCTIONS = """Generate concise starter prompts for a project assistant.
Return only a JSON array containing exactly three strings in the supplied locale.
Each string must be a natural, actionable user request grounded in the public
project context and no longer than 80 characters. Do not use Markdown, expose
internal identifiers or paths, disclose hidden reasoning, or invent facts."""


class StarterPromptModelGenerator:
    """Generate suggestions without creating a Conversation, Turn, or Run."""

    def __init__(
        self,
        *,
        resolve_target: StarterPromptTargetResolver,
        gateway: StarterPromptGateway | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self._resolve_target = resolve_target
        self._gateway = gateway or ModelGateway()
        self._timeout_seconds = timeout_seconds

    async def __call__(
        self,
        request: StarterPromptGenerationRequest,
    ) -> Sequence[str]:
        try:
            target = await self._resolve_target()
            if target is None:
                return ()
            invocation = ModelInvocation(
                target=target,
                instructions=_INSTRUCTIONS,
                input_items=(
                    TextPart(
                        text=json.dumps(
                            {
                                "locale": request.locale,
                                "project": project_prompt_generation_context(
                                    request.project
                                ),
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                    ),
                ),
                tools=(),
                stream=False,
                max_output_tokens=256,
                reasoning=ReasoningRequest(enabled=False),
            )
            output: list[str] = []
            async with asyncio.timeout(self._timeout_seconds):
                async for event in self._gateway.invoke(invocation):
                    if isinstance(event, TextDelta):
                        output.append(event.text)
            return _parse_prompts("".join(output))
        except Exception:
            logger.info("Starter prompt generation failed", exc_info=True)
            return ()


def _parse_prompts(output: str) -> tuple[str, ...]:
    text = output.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError:
        return ()
    if not isinstance(payload, list):
        return ()
    return tuple(item for item in payload if isinstance(item, str))


def build_starter_prompt_generator(
    db,
    *,
    workspace_id: str,
    user_id: str,
    gateway: StarterPromptGateway | None = None,
) -> StarterPromptModelGenerator:
    resolver = AgentModelResolver(
        llm_models=LlmModelRepository(db),
        llm_profiles=LlmModelProfileRepository(db),
        llm_providers=LlmProviderRepository(db),
        llm_credentials=LlmProviderCredentialRepository(db),
        authorization=AuthorizationService(db),
    )

    async def resolve_target() -> ModelTarget | None:
        resolved = await resolver.catalog_default_selection(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return model_target_from_resolved(resolved) if resolved is not None else None

    return StarterPromptModelGenerator(
        resolve_target=resolve_target,
        gateway=gateway,
    )

from __future__ import annotations

import pytest

from app.services.agent_harness.starter_prompt_generation import (
    StarterPromptModelGenerator,
)
from app.services.agent_harness.starter_prompts import StarterPromptGenerationRequest
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelTarget,
    TextDelta,
)


def _target() -> ModelTarget:
    return ModelTarget(
        endpoint_id="provider-1",
        provider_kind="openai",
        model_name="gpt-5.6-mini",
        routed_model_name="gpt-5.6-mini",
        wire_protocol="responses",
        api_key="secret",
    )


class _Gateway:
    def __init__(self) -> None:
        self.invocations = []

    async def invoke(self, invocation):
        self.invocations.append(invocation)
        yield TextDelta(text='["Inspect inputs", "Review runs",')
        yield TextDelta(text=' "Suggest next steps"]')
        yield CompletionMetadata(response_id="response-1", finish_reason="stop")


@pytest.mark.asyncio
async def test_model_generator_uses_a_non_persisting_tool_free_invocation() -> None:
    gateway = _Gateway()

    async def resolve_target():
        return _target()

    generator = StarterPromptModelGenerator(
        resolve_target=resolve_target,
        gateway=gateway,
        timeout_seconds=1,
    )

    prompts = await generator(
        StarterPromptGenerationRequest(
            fingerprint="f" * 64,
            locale="en",
            project={"name": "RNA demo", "description": "RNA-seq analysis"},
        )
    )

    assert prompts == ("Inspect inputs", "Review runs", "Suggest next steps")
    assert len(gateway.invocations) == 1
    invocation = gateway.invocations[0]
    assert invocation.tools == ()
    assert invocation.stream is False
    assert invocation.reasoning.enabled is False
    assert invocation.max_output_tokens == 256


@pytest.mark.asyncio
async def test_model_generator_skips_invocation_when_no_provider_is_available() -> None:
    gateway = _Gateway()

    async def resolve_target():
        return None

    generator = StarterPromptModelGenerator(
        resolve_target=resolve_target,
        gateway=gateway,
    )

    prompts = await generator(
        StarterPromptGenerationRequest(
            fingerprint="f" * 64,
            locale="zh-CN",
            project={"name": "RNA demo"},
        )
    )

    assert prompts == ()
    assert gateway.invocations == []

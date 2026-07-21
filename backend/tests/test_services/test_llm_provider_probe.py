from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any

import pytest

from app.services.llm.credentials import CredentialMaterial
from app.services.llm.probe import LlmProviderProbe
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelInvocation,
    ResponseStarted,
    TextDelta,
    TextPart,
)
from app.services.model_runtime.errors import ModelError


class FakeGateway:
    def __init__(self, *events: object, error: Exception | None = None) -> None:
        self.events = events
        self.error = error
        self.invocations: list[ModelInvocation] = []

    async def invoke(self, invocation: ModelInvocation) -> AsyncIterator[Any]:
        self.invocations.append(invocation)
        if self.error is not None:
            raise self.error
        for event in self.events:
            yield event


class HangingGateway:
    def __init__(self) -> None:
        self.invocations: list[ModelInvocation] = []

    async def invoke(self, invocation: ModelInvocation) -> AsyncIterator[Any]:
        self.invocations.append(invocation)
        await asyncio.Event().wait()
        if False:  # pragma: no cover - keeps this an async generator
            yield None


def _clock(*values: float):
    iterator = iter(values)
    return lambda: next(iterator)


@pytest.mark.asyncio
@pytest.mark.parametrize("wire_protocol", ["chat_completions", "responses"])
async def test_probe_uses_selected_protocol_with_minimal_canonical_invocation(
    wire_protocol: str,
) -> None:
    secret = "sentinel-probe-secret"
    gateway = FakeGateway(
        ResponseStarted(streaming=False),
        TextDelta(text=f"OK {secret}"),
        CompletionMetadata(response_id="response-raw-id", finish_reason="stop"),
    )
    probe = LlmProviderProbe(gateway=gateway, clock=_clock(10.0, 10.042))

    result = await probe.probe(
        endpoint_id="provider-1",
        provider_kind="openai_compatible",
        model_id="gpt-test",
        wire_protocol=wire_protocol,
        base_url="https://relay.example/v1",
        network_access="public_only",
        credential=CredentialMaterial(api_key=secret, source="stored"),
        credential_required=True,
    )

    assert result.success is True
    assert result.latency_ms == 42
    assert result.wire_protocol == wire_protocol
    assert result.model_id == "gpt-test"
    assert result.error_code is None
    assert len(gateway.invocations) == 1
    invocation = gateway.invocations[0]
    assert invocation.target.wire_protocol == wire_protocol
    assert invocation.target.resolved_api_key() == secret
    assert invocation.target.base_url == "https://relay.example/v1"
    assert invocation.target.network_access == "public_only"
    assert invocation.input_items == (TextPart(text="ping"),)
    assert invocation.instructions == "Reply with OK."
    assert invocation.tools == ()
    assert invocation.stream is False
    assert invocation.max_output_tokens == 16
    assert invocation.reasoning.enabled is False
    rendered = repr(result.to_public_dict()) + repr(result)
    assert secret not in rendered
    assert "response-raw-id" not in rendered


@pytest.mark.asyncio
async def test_probe_reports_missing_required_credential_without_calling_gateway() -> (
    None
):
    gateway = FakeGateway()

    result = await LlmProviderProbe(gateway=gateway).probe(
        endpoint_id="provider-1",
        provider_kind="openai",
        model_id="gpt-test",
        wire_protocol="responses",
        base_url=None,
        network_access="public_only",
        credential=CredentialMaterial(api_key=None, source="env"),
        credential_required=True,
    )

    assert result.success is False
    assert result.latency_ms == 0
    assert result.error_code == "missing_credential"
    assert result.error_message == "Provider credential is required but unavailable."
    assert result.retryable is False
    assert gateway.invocations == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "error_code", "http_status", "retryable"),
    [
        (
            ModelError(
                category="timeout",
                message="The model provider request timed out.",
                http_status=408,
                provider_code="request_timeout",
                retryable=True,
                replay_safe=True,
            ),
            "timeout",
            408,
            True,
        ),
        (
            ModelError(
                category="authentication",
                message="Model provider authentication failed.",
                http_status=401,
                provider_code="invalid_api_key",
                retryable=False,
                replay_safe=True,
            ),
            "authentication",
            401,
            False,
        ),
        (
            ModelError(
                category="service_unavailable",
                message="The model provider is temporarily unavailable.",
                http_status=503,
                provider_code="server_error",
                retryable=True,
                replay_safe=True,
            ),
            "service_unavailable",
            503,
            True,
        ),
    ],
)
async def test_probe_returns_safe_structured_provider_failures(
    error: ModelError,
    error_code: str,
    http_status: int,
    retryable: bool,
) -> None:
    gateway = FakeGateway(error=error)

    result = await LlmProviderProbe(
        gateway=gateway,
        clock=_clock(5.0, 5.125),
    ).probe(
        endpoint_id="provider-1",
        provider_kind="openai_compatible",
        model_id="gpt-test",
        wire_protocol="responses",
        base_url=None,
        network_access="public_only",
        credential=CredentialMaterial(api_key="secret", source="stored"),
        credential_required=True,
    )

    assert result.success is False
    assert result.latency_ms == 125
    assert result.error_code == error_code
    assert result.error_message == error.message
    assert result.http_status == http_status
    assert result.provider_code == error.provider_code
    assert result.retryable is retryable
    assert gateway.invocations[0].target.wire_protocol == "responses"


@pytest.mark.asyncio
async def test_probe_sanitizes_unexpected_failures_without_logging_or_chaining(
    caplog,
) -> None:
    secret = "sentinel-unexpected-probe-secret"
    gateway = FakeGateway(error=RuntimeError(f"raw api_key={secret}"))

    result = await LlmProviderProbe(
        gateway=gateway,
        clock=_clock(1.0, 1.005),
    ).probe(
        endpoint_id="provider-1",
        provider_kind="openai_compatible",
        model_id="gpt-test",
        wire_protocol="chat_completions",
        base_url=None,
        network_access="public_only",
        credential=CredentialMaterial(api_key=secret, source="stored"),
        credential_required=True,
    )

    assert result.success is False
    assert result.error_code == "probe_failed"
    assert result.error_message == "Model provider probe failed."
    assert result.retryable is False
    assert secret not in repr(result)
    assert secret not in repr(result.to_public_dict())
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_probe_deadline_returns_safe_retryable_timeout_for_hanging_gateway(
    caplog,
) -> None:
    secret = "sentinel-hanging-probe-secret"
    gateway = HangingGateway()
    probe = LlmProviderProbe(gateway=gateway, timeout_seconds=0.01)
    started_at = perf_counter()

    result = await asyncio.wait_for(
        probe.probe(
            endpoint_id="provider-1",
            provider_kind="openai_compatible",
            model_id="gpt-test",
            wire_protocol="responses",
            base_url="https://relay.example/v1",
            network_access="public_only",
            credential=CredentialMaterial(api_key=secret, source="stored"),
            credential_required=True,
        ),
        timeout=0.5,
    )

    assert perf_counter() - started_at < 0.5
    assert result.success is False
    assert result.error_code == "timeout"
    assert result.error_message == "The model provider request timed out."
    assert result.retryable is True
    assert result.http_status == 408
    assert result.provider_code == "probe_timeout"
    assert len(gateway.invocations) == 1
    assert secret not in repr(result)
    assert secret not in repr(result.to_public_dict())
    assert secret not in caplog.text


def test_probe_result_public_shape_is_stable_and_json_safe() -> None:
    result = LlmProviderProbe.missing_credential_result(
        wire_protocol="chat_completions",
        model_id="gpt-test",
    )

    assert result.to_public_dict() == {
        "success": False,
        "latency_ms": 0,
        "wire_protocol": "chat_completions",
        "model_id": "gpt-test",
        "error_code": "missing_credential",
        "error_message": "Provider credential is required but unavailable.",
        "retryable": False,
        "http_status": None,
        "provider_code": None,
    }

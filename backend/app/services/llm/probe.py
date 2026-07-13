from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.services.llm.credentials import CredentialMaterial
from app.services.model_runtime.contracts import (
    ModelInvocation,
    ModelTarget,
    TextPart,
    WireProtocol,
)
from app.services.model_runtime.errors import ModelError
from app.services.model_runtime.gateway import ModelGateway


_MISSING_CREDENTIAL_MESSAGE = "Provider credential is required but unavailable."
_PROBE_FAILED_MESSAGE = "Model provider probe failed."
_PROBE_TIMEOUT_MESSAGE = "The model provider request timed out."


@dataclass(frozen=True)
class LlmProviderProbeResult:
    success: bool
    latency_ms: int
    wire_protocol: WireProtocol
    model_id: str
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    http_status: int | None = None
    provider_code: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "latency_ms": self.latency_ms,
            "wire_protocol": self.wire_protocol,
            "model_id": self.model_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "retryable": self.retryable,
            "http_status": self.http_status,
            "provider_code": self.provider_code,
        }


class LlmProviderProbe:
    """Run one non-persisting provider connectivity check through ModelGateway."""

    def __init__(
        self,
        *,
        gateway: ModelGateway | None = None,
        clock: Callable[[], float] = perf_counter,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._gateway = gateway if gateway is not None else ModelGateway()
        self._clock = clock
        self._timeout_seconds = timeout_seconds

    async def probe(
        self,
        *,
        endpoint_id: str,
        provider_kind: str,
        model_id: str,
        wire_protocol: WireProtocol,
        base_url: str | None,
        credential: CredentialMaterial,
        credential_required: bool,
    ) -> LlmProviderProbeResult:
        if credential_required and not credential.api_key:
            return self.missing_credential_result(
                wire_protocol=wire_protocol,
                model_id=model_id,
            )

        invocation = ModelInvocation(
            target=ModelTarget(
                endpoint_id=endpoint_id,
                provider_kind=provider_kind,
                model_name=model_id,
                wire_protocol=wire_protocol,
                base_url=base_url,
                api_key=credential.api_key,
            ),
            instructions="Reply with OK.",
            input_items=(TextPart(text="ping"),),
            tools=(),
            stream=False,
            max_output_tokens=16,
            allow_reasoning=False,
        )
        started_at = self._clock()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async for _event in self._gateway.invoke(invocation):
                    pass
        except TimeoutError:
            return LlmProviderProbeResult(
                success=False,
                latency_ms=self._elapsed_ms(started_at),
                wire_protocol=wire_protocol,
                model_id=model_id,
                error_code="timeout",
                error_message=_PROBE_TIMEOUT_MESSAGE,
                retryable=True,
                http_status=408,
                provider_code="probe_timeout",
            )
        except ModelError as exc:
            return LlmProviderProbeResult(
                success=False,
                latency_ms=self._elapsed_ms(started_at),
                wire_protocol=wire_protocol,
                model_id=model_id,
                error_code=exc.category,
                error_message=exc.message,
                retryable=exc.retryable,
                http_status=exc.http_status,
                provider_code=exc.provider_code,
            )
        except Exception:  # noqa: BLE001 - unexpected provider details stay private
            return LlmProviderProbeResult(
                success=False,
                latency_ms=self._elapsed_ms(started_at),
                wire_protocol=wire_protocol,
                model_id=model_id,
                error_code="probe_failed",
                error_message=_PROBE_FAILED_MESSAGE,
            )

        return LlmProviderProbeResult(
            success=True,
            latency_ms=self._elapsed_ms(started_at),
            wire_protocol=wire_protocol,
            model_id=model_id,
        )

    @staticmethod
    def missing_credential_result(
        *,
        wire_protocol: WireProtocol,
        model_id: str,
    ) -> LlmProviderProbeResult:
        return LlmProviderProbeResult(
            success=False,
            latency_ms=0,
            wire_protocol=wire_protocol,
            model_id=model_id,
            error_code="missing_credential",
            error_message=_MISSING_CREDENTIAL_MESSAGE,
        )

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, round((self._clock() - started_at) * 1000))

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
import logging
from typing import Any, Protocol, TypeVar


logger = logging.getLogger(__name__)
CaptureResult = TypeVar("CaptureResult")


class ModelExchangeObserver(Protocol):
    async def request_prepared(
        self,
        exchange_id: str,
        payload: dict | list,
        *,
        prepared_at: datetime,
    ) -> None: ...

    async def first_byte_received(
        self,
        exchange_id: str,
        *,
        occurred_at: datetime,
    ) -> None: ...

    async def response_received(
        self, exchange_id: str, payload: dict | list
    ) -> None: ...


class ModelExchangeLifecycle(ModelExchangeObserver, Protocol):
    async def start(
        self,
        *,
        session_id: str,
        run_id: str,
        iteration: int,
        attempt: int,
        context_through_sequence: int,
        provider: str,
        model: str,
        wire_protocol: str,
        context_snapshot: dict[str, Any],
    ) -> str: ...

    async def complete(
        self,
        exchange_id: str,
        *,
        usage: dict[str, Any] | None,
        provider_response_id: str | None,
        finish_reason: str | None,
    ) -> None: ...

    async def fail(
        self,
        exchange_id: str,
        *,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None: ...

    async def recover_after_failure(self) -> None: ...


async def capture_exchange_best_effort(
    owner: object,
    operation: str,
    capture: Callable[[], Awaitable[CaptureResult]],
) -> CaptureResult | None:
    try:
        return await capture()
    except Exception as exc:  # noqa: BLE001 - telemetry must remain best-effort
        await _recover_capture_owner(owner)
        logger.warning(
            "Model exchange capture failed during %s (%s).",
            operation,
            type(exc).__name__,
        )
        return None


async def notify_exchange_observer(
    observer: ModelExchangeObserver,
    callback_name: str,
    *args: Any,
    **kwargs: Any,
) -> None:
    callback = getattr(observer, callback_name, None)
    if not callable(callback):
        return
    await capture_exchange_best_effort(
        observer,
        callback_name,
        lambda: callback(*args, **kwargs),
    )


async def _recover_capture_owner(owner: object) -> None:
    recover = getattr(owner, "recover_after_failure", None)
    if not callable(recover):
        return
    try:
        await recover()
    except Exception as exc:  # noqa: BLE001 - recovery is also best-effort
        logger.warning(
            "Model exchange capture recovery failed (%s).",
            type(exc).__name__,
        )


__all__ = [
    "ModelExchangeLifecycle",
    "ModelExchangeObserver",
    "capture_exchange_best_effort",
    "notify_exchange_observer",
]

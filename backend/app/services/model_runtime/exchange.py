from __future__ import annotations

from typing import Protocol


class ModelExchangeObserver(Protocol):
    async def request_prepared(
        self, exchange_id: str, payload: dict | list
    ) -> None: ...

    async def response_received(
        self, exchange_id: str, payload: dict | list
    ) -> None: ...


__all__ = ["ModelExchangeObserver"]

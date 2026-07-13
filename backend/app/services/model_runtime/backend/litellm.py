from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any

import litellm

from app.services.model_runtime.contracts import WireProtocol
from app.services.model_runtime.errors import ModelError


CompletionCallable = Callable[..., Awaitable[Any]]


class LiteLLMBackend:
    """Execute one wire-level LiteLLM request without hidden retry policy."""

    def __init__(self, *, acompletion_fn: CompletionCallable | None = None) -> None:
        self._acompletion = acompletion_fn or litellm.acompletion

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    async def invoke(
        self,
        wire_protocol: WireProtocol,
        request: Mapping[str, Any],
    ) -> Any:
        if wire_protocol != "chat_completions":
            raise ValueError(f"Unsupported wire protocol: {wire_protocol}")

        request_kwargs = dict(request)
        request_kwargs["num_retries"] = 0
        try:
            response = await self._acompletion(**request_kwargs)
        except ModelError:
            raise
        except Exception as exc:
            raise _provider_error(exc, replay_safe=True) from None
        return _safe_stream(response) if hasattr(response, "__aiter__") else response


def _safe_stream(response: Any) -> AsyncIterator[Any]:
    async def iterate() -> AsyncIterator[Any]:
        yielded = False
        try:
            async for item in response:
                yielded = True
                yield item
        except ModelError:
            raise
        except Exception as exc:
            raise _provider_error(exc, replay_safe=not yielded) from None

    return iterate()


def _provider_error(exc: Exception, *, replay_safe: bool) -> ModelError:
    return ModelError(
        category="provider",
        message="Model provider request failed.",
        replay_safe=replay_safe,
        cause=exc,
    )

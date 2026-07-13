from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
import re
from typing import Any

import litellm

from app.services.model_runtime.contracts import WireProtocol
from app.services.model_runtime.errors import ModelError


CompletionCallable = Callable[..., Awaitable[Any]]

_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}")
_PUBLIC_MESSAGES = {
    "authentication": "Model provider authentication failed.",
    "authorization": "Model provider authorization failed.",
    "rate_limit": "The model provider rate limit was exceeded.",
    "timeout": "The model provider request timed out.",
    "connection": "The model provider connection failed.",
    "service_unavailable": "The model provider is temporarily unavailable.",
    "invalid_request": "The model provider rejected the request.",
    "not_found": "The requested model provider resource was not found.",
    "conflict": "The model provider reported a request conflict.",
    "provider": "Model provider request failed.",
}


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
        sensitive_values = _sensitive_values(request_kwargs)
        try:
            response = await self._acompletion(**request_kwargs)
        except ModelError:
            raise
        except Exception as exc:
            raise _provider_error(
                exc,
                replay_safe=True,
                sensitive_values=sensitive_values,
            ) from None
        return (
            _safe_stream(response, sensitive_values=sensitive_values)
            if hasattr(response, "__aiter__")
            else response
        )


def _safe_stream(
    response: Any,
    *,
    sensitive_values: tuple[str, ...],
) -> AsyncIterator[Any]:
    async def iterate() -> AsyncIterator[Any]:
        yielded = False
        try:
            async for item in response:
                yielded = True
                yield item
        except ModelError as exc:
            if yielded and exc.replay_safe:
                raise _copy_model_error(exc, replay_safe=False) from None
            raise
        except Exception as exc:
            raise _provider_error(
                exc,
                replay_safe=not yielded,
                sensitive_values=sensitive_values,
            ) from None

    return iterate()


def _provider_error(
    exc: Exception,
    *,
    replay_safe: bool,
    sensitive_values: tuple[str, ...],
) -> ModelError:
    status_code = _status_code(exc)
    category, retryable = _error_classification(exc, status_code=status_code)
    return ModelError(
        category=category,
        message=_PUBLIC_MESSAGES[category],
        http_status=status_code,
        provider_code=_provider_code(exc, sensitive_values=sensitive_values),
        retryable=retryable,
        replay_safe=replay_safe,
        retry_after_seconds=_retry_after_seconds(exc),
        request_id=_request_id(exc, sensitive_values=sensitive_values),
        cause=exc,
    )


def _error_classification(exc: Exception, *, status_code: int | None) -> tuple[str, bool]:
    if isinstance(exc, litellm.RateLimitError) or status_code == 429:
        return "rate_limit", True
    if isinstance(exc, (litellm.Timeout, TimeoutError)):
        return "timeout", True
    if isinstance(exc, litellm.APIConnectionError):
        return "connection", True
    if isinstance(exc, litellm.ServiceUnavailableError) or status_code in {502, 503, 504}:
        return "service_unavailable", True
    if status_code == 400:
        return "invalid_request", False
    if status_code == 401:
        return "authentication", False
    if status_code == 403:
        return "authorization", False
    if status_code == 404:
        return "not_found", False
    if status_code == 409:
        return "conflict", False
    return "provider", False


def _status_code(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _provider_code(
    exc: Exception,
    *,
    sensitive_values: tuple[str, ...],
) -> str | None:
    candidates = [getattr(exc, "code", None)]
    body = getattr(exc, "body", None)
    candidates.extend(_error_code_candidates(body))
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            candidates.extend(_error_code_candidates(response.json()))
        except Exception:  # noqa: BLE001 - malformed provider bodies are metadata only
            pass
    for candidate in candidates:
        safe = _safe_identifier(candidate, sensitive_values=sensitive_values)
        if safe is not None:
            return safe
    return None


def _error_code_candidates(value: Any) -> list[Any]:
    if not isinstance(value, Mapping):
        return []
    error = value.get("error")
    nested_code = error.get("code") if isinstance(error, Mapping) else None
    return [value.get("code"), nested_code]


def _request_id(
    exc: Exception,
    *,
    sensitive_values: tuple[str, ...],
) -> str | None:
    candidates = [getattr(exc, "request_id", None)]
    response = getattr(exc, "response", None)
    candidates.extend(_header_values(getattr(response, "headers", None), "x-request-id"))
    candidates.extend(_header_values(getattr(response, "headers", None), "request-id"))
    candidates.extend(_header_values(getattr(exc, "headers", None), "x-request-id"))
    for candidate in candidates:
        safe = _safe_identifier(candidate, sensitive_values=sensitive_values)
        if safe is not None:
            return safe
    return None


def _retry_after_seconds(exc: Exception) -> float | None:
    candidates = [getattr(exc, "retry_after", None)]
    response = getattr(exc, "response", None)
    candidates.extend(_header_values(getattr(response, "headers", None), "retry-after"))
    candidates.extend(_header_values(getattr(exc, "headers", None), "retry-after"))
    for candidate in candidates:
        try:
            seconds = float(candidate)
        except (TypeError, ValueError):
            continue
        if seconds >= 0:
            return seconds
    return None


def _header_values(headers: Any, key: str) -> list[Any]:
    if headers is None or not hasattr(headers, "get"):
        return []
    return [headers.get(key)]


def _safe_identifier(
    value: Any,
    *,
    sensitive_values: tuple[str, ...],
) -> str | None:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    text = str(value)
    if any(secret and secret in text for secret in sensitive_values):
        return None
    return text if _SAFE_IDENTIFIER.fullmatch(text) else None


def _sensitive_values(request: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key, value in request.items():
        normalized_key = str(key).lower()
        if not any(token in normalized_key for token in ("key", "token", "secret", "authorization")):
            continue
        if isinstance(value, str) and value:
            values.append(value)
    return tuple(values)


def _copy_model_error(exc: ModelError, *, replay_safe: bool) -> ModelError:
    return ModelError(
        category=exc.category,
        message=exc.message,
        http_status=exc.http_status,
        provider_code=exc.provider_code,
        retryable=exc.retryable,
        replay_safe=replay_safe,
        retry_after_seconds=exc.retry_after_seconds,
        request_id=exc.request_id,
        cause=exc.cause,
    )

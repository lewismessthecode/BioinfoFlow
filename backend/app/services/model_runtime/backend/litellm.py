from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
import re
from typing import Any

import litellm
from openai import AsyncOpenAI

from app.services.model_runtime.backend.litellm_network import PublicNetworkHTTPHandler
from app.services.model_runtime.contracts import NetworkAccessPolicy, WireProtocol
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

    def __init__(
        self,
        *,
        acompletion_fn: CompletionCallable | None = None,
        aresponses_fn: CompletionCallable | None = None,
    ) -> None:
        self._acompletion = acompletion_fn or litellm.acompletion
        self._aresponses = aresponses_fn or litellm.aresponses

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    async def invoke(
        self,
        wire_protocol: WireProtocol,
        request: Mapping[str, Any],
        *,
        network_access: NetworkAccessPolicy = "unrestricted",
    ) -> Any:
        if wire_protocol == "chat_completions":
            operation = self._acompletion
        elif wire_protocol == "responses":
            operation = self._aresponses
        else:
            raise ValueError(f"Unsupported wire protocol: {wire_protocol}")

        request_kwargs = dict(request)
        request_kwargs["num_retries"] = 0
        policy_client = (
            PublicNetworkHTTPHandler() if network_access == "public_only" else None
        )
        provider_client = None
        if policy_client is not None:
            provider_client = _request_scoped_provider_client(
                wire_protocol,
                request_kwargs,
                policy_client,
            )
            request_kwargs["client"] = provider_client
        sensitive_values = _sensitive_values(request_kwargs)
        try:
            response = await operation(**request_kwargs)
        except ModelError:
            await _close_request_clients(policy_client, provider_client)
            raise
        except Exception as exc:
            await _close_request_clients(policy_client, provider_client)
            raise _provider_error(
                exc,
                replay_safe=True,
                sensitive_values=sensitive_values,
            ) from None
        if hasattr(response, "__aiter__"):
            return _safe_stream(
                response,
                sensitive_values=sensitive_values,
                policy_client=policy_client,
                provider_client=provider_client,
            )
        await _close_request_clients(policy_client, provider_client)
        return response


def _safe_stream(
    response: Any,
    *,
    sensitive_values: tuple[str, ...],
    policy_client: PublicNetworkHTTPHandler | None = None,
    provider_client: Any | None = None,
) -> AsyncIterator[Any]:
    async def iterate() -> AsyncIterator[Any]:
        try:
            async for item in response:
                yield item
        except ModelError:
            raise
        except Exception as exc:
            raise _provider_error(
                exc,
                replay_safe=True,
                sensitive_values=sensitive_values,
            ) from None
        finally:
            await _close_request_clients(policy_client, provider_client)

    return iterate()


def _request_scoped_provider_client(
    wire_protocol: WireProtocol,
    request: Mapping[str, Any],
    policy_client: PublicNetworkHTTPHandler,
) -> Any:
    if wire_protocol == "responses":
        return policy_client
    model = str(request.get("model") or "")
    if not model.startswith("openai/"):
        return policy_client
    api_key = str(request.get("api_key") or "not-required")
    base_url = str(request.get("api_base") or "https://api.openai.com/v1")
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=policy_client.client,
    )


async def _close_request_clients(
    policy_client: PublicNetworkHTTPHandler | None,
    provider_client: Any | None,
) -> None:
    if policy_client is None:
        return
    if provider_client is not None and provider_client is not policy_client:
        try:
            await provider_client.close()
        except Exception:
            pass
    try:
        await policy_client.close()
    except Exception:
        return


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


def _error_classification(
    exc: Exception, *, status_code: int | None
) -> tuple[str, bool]:
    if isinstance(exc, litellm.RateLimitError) or status_code == 429:
        return "rate_limit", True
    if isinstance(exc, (litellm.Timeout, TimeoutError)):
        return "timeout", True
    if isinstance(exc, litellm.APIConnectionError):
        return "connection", True
    if isinstance(exc, litellm.ServiceUnavailableError) or status_code in {
        502,
        503,
        504,
    }:
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
    candidates.extend(
        _header_values(getattr(response, "headers", None), "x-request-id")
    )
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
        if not any(
            token in normalized_key
            for token in ("key", "token", "secret", "authorization")
        ):
            continue
        if isinstance(value, str) and value:
            values.append(value)
    return tuple(values)

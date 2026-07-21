from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from app.services.llm.registry import ModelSpec, ProviderSpec
from app.services.model_runtime.contracts import ReasoningRequest, WireProtocol


@dataclass(frozen=True)
class ProviderConnection:
    base_url: str
    api_key: str | None


@dataclass(frozen=True)
class CatalogRequest:
    url: str
    headers: dict[str, str]
    params: dict[str, str | int] | None = None


class ProviderProfile:
    def __init__(self, spec: ProviderSpec):
        self.spec = spec

    def catalog_request(
        self,
        connection: ProviderConnection,
    ) -> CatalogRequest | None:
        if self.spec.catalog.strategy == "bundled":
            return None
        headers: dict[str, str] = {}
        if connection.api_key and not self.spec.catalog.public:
            auth = self.spec.auth
            value = (
                f"{auth.scheme} {connection.api_key}"
                if auth.scheme
                else connection.api_key
            )
            headers[auth.header] = value
        return CatalogRequest(
            url=_compose_catalog_url(
                connection.base_url,
                self.spec.catalog.path or "/models",
            ),
            headers=headers,
        )

    def parse_catalog(self, payload: dict[str, Any]) -> tuple[ModelSpec, ...]:
        items = payload.get("data")
        if not isinstance(items, list):
            return ()
        models = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            model_id = item["id"].strip()
            if model_id:
                models.append(ModelSpec(model_id, item.get("name") or model_id))
        return tuple(models)

    def invocation_options(
        self,
        model_name: str,
        reasoning: ReasoningRequest,
    ) -> dict[str, Any]:
        del model_name
        if not reasoning.enabled:
            return {}
        return {"reasoning_effort": reasoning.effort or "medium"}

    def compile_request(
        self,
        request: dict[str, Any],
        *,
        model_name: str,
        wire_protocol: WireProtocol,
        reasoning: ReasoningRequest,
    ) -> dict[str, Any]:
        del wire_protocol
        compiled = copy.deepcopy(request)
        compiled.update(self.invocation_options(model_name, reasoning))
        return compiled


def _compose_catalog_url(base_url: str, path: str) -> str:
    base = base_url.strip().rstrip("/")
    normalized_path = "/" + path.strip("/")
    if base.endswith(normalized_path):
        return base
    if normalized_path.startswith("/v1/") and base.endswith("/v1"):
        return base + normalized_path[len("/v1") :]
    if base.endswith("/models"):
        return base
    return base + normalized_path

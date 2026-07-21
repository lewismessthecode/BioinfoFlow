from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import httpx
import pytest
import socket

from app.models.llm import LlmModel, LlmProvider, LlmProviderCredential
from app.services.llm.bootstrap import sync_environment_llm_catalog
from app.services.llm.catalog import LlmCatalogService, _validate_provider_base_url
from app.services.llm.provider_templates import (
    ProviderRegistry,
    ProviderTemplate,
    get_provider_template,
    list_provider_templates,
    normalize_provider_base_url,
    provider_template_for_provider,
)
from app.utils.exceptions import PermissionDeniedError


def _network_client_factory(client_type):
    @asynccontextmanager
    async def factory(**kwargs):
        client = client_type(timeout=kwargs.get("timeout"))
        async with client:
            yield client

    return factory


async def _noop_discovery(self, provider, **kwargs):
    del kwargs
    return []


def test_provider_templates_expose_explicit_supported_and_default_protocols() -> None:
    openai = get_provider_template("openai")
    compatible = get_provider_template("openai-compatible")
    anthropic = get_provider_template("anthropic")

    assert openai is not None
    assert compatible is not None
    assert anthropic is not None
    assert openai.supported_wire_protocols == ("chat_completions", "responses")
    assert compatible.supported_wire_protocols == ("chat_completions", "responses")
    assert openai.default_wire_protocol == "chat_completions"
    assert anthropic.supported_wire_protocols == ("chat_completions",)
    assert anthropic.default_wire_protocol == "chat_completions"
    assert openai.as_dict()["supported_wire_protocols"] == [
        "chat_completions",
        "responses",
    ]
    assert [field["name"] for field in anthropic.as_dict()["fields"]] == ["api_key"]


def test_common_provider_templates_are_key_first_and_provider_neutral() -> None:
    templates = {template.id: template for template in list_provider_templates()}
    assert set(templates) == {
        "openai",
        "anthropic",
        "openrouter",
        "fireworks",
        "qwen",
        "deepseek",
        "xai",
        "zai",
        "kimi-code",
        "minimax",
        "huggingface",
        "gemini",
    }

    for template_id in templates:
        fields = templates[template_id].as_dict()["fields"]
        assert fields[-1]["name"] == "api_key", template_id
        assert fields[-1]["placeholder"] == "Paste API key"

    assert templates["kimi-code"].env_api_key_vars == (
        "KIMI_API_KEY",
        "KIMI_CODE_API_KEY",
    )
    assert templates["kimi-code"].default_base_url == "https://api.kimi.com/coding/v1"

    serialized_templates = repr([template.as_dict() for template in templates.values()])
    assert "".join(("c", "ch")) not in serialized_templates.lower()
    assert ".".join(("8", "129", "13", "231")) not in serialized_templates
    assert "-".join(("claude", "sonnet", "5")) not in serialized_templates


def test_legacy_kimi_china_endpoint_resolves_to_china_template() -> None:
    provider = LlmProvider(
        name="Kimi",
        kind="kimi",
        base_url="https://api.moonshot.cn/v1",
        scope="user",
        workspace_id="00000000-0000-0000-0000-000000000001",
        user_id="user-1",
        enabled=True,
        provider_metadata={"providerTemplate": "kimi"},
    )

    template = provider_template_for_provider(provider)

    assert template is not None
    assert template.id == "kimi-cn"
    assert template.kind == "kimi_cn"


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://anthropic-gateway.example", "https://anthropic-gateway.example"),
        ("https://anthropic-gateway.example/v1", "https://anthropic-gateway.example"),
        (
            "https://anthropic-gateway.example/v1/messages",
            "https://anthropic-gateway.example",
        ),
        (
            "https://relay.example.com/anthropic/v1/messages",
            "https://relay.example.com/anthropic",
        ),
    ],
)
def test_anthropic_base_url_normalizes_to_messages_api_root(
    base_url,
    expected,
) -> None:
    assert normalize_provider_base_url("anthropic", base_url) == expected


def test_custom_provider_template_can_declare_responses_support() -> None:
    template = ProviderTemplate(
        id="custom-vllm",
        name="Custom vLLM",
        kind="custom_vllm",
        docs_url="https://docs.example.com/custom-vllm",
        discovery="openai_models",
        supported_wire_protocols=("chat_completions", "responses"),
    )
    registry = ProviderRegistry((template,))

    assert registry.validate_configuration("custom_vllm", "responses") == (
        "custom_vllm",
        "responses",
    )


def test_provider_registry_rejects_unknown_or_unsupported_configuration() -> None:
    template = ProviderTemplate(
        id="custom-vllm",
        name="Custom vLLM",
        kind="custom_vllm",
        docs_url="https://docs.example.com/custom-vllm",
        discovery="openai_models",
    )
    registry = ProviderRegistry((template,))

    with pytest.raises(ValueError, match="Unsupported LLM provider kind"):
        registry.validate_configuration("unknown_provider", "chat_completions")
    with pytest.raises(ValueError, match="does not support wire protocol"):
        registry.validate_configuration("custom_vllm", "responses")


@pytest.mark.asyncio
async def test_openai_compatible_environment_bootstrap_persists_explicit_protocol(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://relay.example/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "gpt-test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_WIRE_PROTOCOL", "responses")
    monkeypatch.setattr(
        "app.services.llm.bootstrap.LlmCatalogService.discover_models_unchecked",
        _noop_discovery,
    )

    await sync_environment_llm_catalog(db_session)

    provider = (
        await db_session.execute(
            LlmProvider.__table__.select().where(
                LlmProvider.kind == "openai_compatible"
            )
        )
    ).mappings().one()
    assert provider["wire_protocol"] == "responses"


@pytest.mark.asyncio
async def test_environment_bootstrap_defaults_missing_protocol_to_chat(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://relay.example/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "gpt-test")
    monkeypatch.delenv("OPENAI_COMPATIBLE_WIRE_PROTOCOL", raising=False)
    monkeypatch.setattr(
        "app.services.llm.bootstrap.LlmCatalogService.discover_models_unchecked",
        _noop_discovery,
    )

    await sync_environment_llm_catalog(db_session)

    provider = (
        await db_session.execute(
            LlmProvider.__table__.select().where(
                LlmProvider.kind == "openai_compatible"
            )
        )
    ).mappings().one()
    assert provider["wire_protocol"] == "chat_completions"


@pytest.mark.asyncio
async def test_anthropic_environment_bootstrap_accepts_https_custom_base_url(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://anthropic-gateway.example/v1")
    monkeypatch.setattr(
        "app.services.llm.bootstrap.LlmCatalogService.discover_models_unchecked",
        _noop_discovery,
    )

    await sync_environment_llm_catalog(db_session)

    provider = (
        await db_session.execute(
            LlmProvider.__table__.select().where(LlmProvider.kind == "anthropic")
        )
    ).mappings().one()
    assert provider["base_url"] == "https://anthropic-gateway.example"
    assert provider["allow_insecure_http"] is False
    assert provider["wire_protocol"] == "chat_completions"
    assert provider["metadata"]["providerTemplate"] == "anthropic"


@pytest.mark.asyncio
async def test_kimi_environment_bootstrap_uses_kimi_code_endpoint(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("KIMI_API_KEY", "kimi-code-key")
    monkeypatch.setattr(
        "app.services.llm.bootstrap.LlmCatalogService.discover_models_unchecked",
        _noop_discovery,
    )

    await sync_environment_llm_catalog(db_session)

    provider = (
        await db_session.execute(
            LlmProvider.__table__.select().where(LlmProvider.kind == "kimi_code")
        )
    ).mappings().one()
    assert provider["base_url"] == "https://api.kimi.com/coding/v1"
    assert provider["metadata"]["providerTemplate"] == "kimi-code"

    credential = (
        await db_session.execute(
            LlmProviderCredential.__table__.select().where(
                LlmProviderCredential.provider_id == provider["id"]
            )
        )
    ).mappings().one()
    assert credential["env_var_name"] == "KIMI_API_KEY"


@pytest.mark.asyncio
async def test_kimi_environment_bootstrap_ignores_legacy_moonshot_key(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "legacy-kimi-cn-key")
    monkeypatch.setattr(
        "app.services.llm.bootstrap.LlmCatalogService.discover_models_unchecked",
        _noop_discovery,
    )

    await sync_environment_llm_catalog(db_session)

    providers = (
        await db_session.execute(
            LlmProvider.__table__.select().where(LlmProvider.kind == "kimi_cn")
        )
    ).mappings().all()
    assert providers == []


@pytest.mark.asyncio
async def test_environment_bootstrap_rejects_invalid_explicit_protocol(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://relay.example/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_WIRE_PROTOCOL", "guess")

    with pytest.raises(ValueError, match="wire protocol"):
        await sync_environment_llm_catalog(db_session)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com/v1",
        "http://localhost:8000/v1",
        "http://127.0.0.1:8000/v1",
        "http://[::1]:8000/v1",
        "http://10.49.35.231:8000/v1",  # private IP
        "http://192.168.1.20:11434",
        "http://deepseek-v4:8000/v1",  # Docker service (single-label)
        "http://vllm.default.svc:8000/v1",  # Kubernetes service
        "http://host.docker.internal:8000/v1",
        "http://gateway.local/v1",
    ],
)
def test_validate_provider_base_url_accepts_secure_and_internal_endpoints(base_url):
    # Should not raise.
    _validate_provider_base_url(base_url)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.openai.com/v1",  # public FQDN over plain HTTP
        "http://example.com:8000/v1",
        "ftp://localhost/v1",  # non-HTTP scheme
        "not-a-url",
    ],
)
def test_validate_provider_base_url_rejects_public_http_and_malformed(base_url):
    with pytest.raises(ValueError):
        _validate_provider_base_url(base_url)


def test_validate_provider_base_url_allows_public_http_with_explicit_opt_in():
    _validate_provider_base_url(
        "http://public-relay.example:8079/v1",
        allow_insecure_http=True,
    )


def test_validate_provider_base_url_allows_empty():
    # An unset endpoint is valid (provider may use a template default).
    _validate_provider_base_url(None)
    _validate_provider_base_url("")


@pytest.mark.asyncio
async def test_model_discovery_rejects_unapproved_public_http_before_network(
    db_session,
    monkeypatch,
):
    network_called = False

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, *args, **kwargs):
            nonlocal network_called
            network_called = True
            return httpx.Response(
                200,
                json={"data": []},
                request=httpx.Request("GET", str(args[0])),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )
    provider = LlmProvider(
        name="Unapproved public relay",
        kind="openai_compatible",
        base_url="http://public-relay.example:8079/v1",
        allow_insecure_http=False,
        scope="user",
        workspace_id=None,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()

    with pytest.raises(ValueError, match="explicitly allow insecure HTTP"):
        await LlmCatalogService(db_session).discover_models_unchecked(
            provider,
            network_access="public_only",
        )

    assert network_called is False


@pytest.mark.asyncio
async def test_public_only_discovery_ignores_proxy_env_and_rejects_rebound_dns(
    db_session,
    monkeypatch,
):
    requests = 0

    async def handle(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        nonlocal requests
        await reader.readuntil(b"\r\n\r\n")
        requests += 1
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 11\r\n"
            b"Connection: close\r\n\r\n"
            b'{"data":[]}'
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    proxy_url = f"http://127.0.0.1:{port}"
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(name, proxy_url)
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))
        ],
    )
    provider = LlmProvider(
        name="Rebinding discovery relay",
        kind="openai_compatible",
        base_url=f"http://relay.example.com:{port}/v1",
        allow_insecure_http=True,
        scope="user",
        workspace_id=None,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()

    try:
        with pytest.raises(PermissionDeniedError, match="public address"):
            await LlmCatalogService(db_session).discover_models_unchecked(
                provider,
                network_access="public_only",
            )
    finally:
        server.close()
        await server.wait_closed()

    assert requests == 0


@pytest.mark.asyncio
async def test_simple_vllm_environment_profile_bootstraps_catalog(
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm.internal.test:8000/v1")
    monkeypatch.setenv("VLLM_API_KEY", "vllm")
    monkeypatch.setenv("VLLM_MODEL", "deepseek_v4")
    monkeypatch.delenv("OPENAI_COMPATIBLE_PROVIDERS", raising=False)
    monkeypatch.setattr(
        "app.services.llm.bootstrap.LlmCatalogService.discover_models_unchecked",
        _noop_discovery,
    )

    result = await sync_environment_llm_catalog(db_session)

    assert result.created_or_updated >= 1

    providers = [
        provider
        for provider in (await db_session.execute(LlmProvider.__table__.select())).mappings()
        if provider["kind"] == "vllm"
    ]
    assert len(providers) == 1
    provider = providers[0]
    assert provider["name"] == "vLLM"
    assert provider["base_url"] == "http://vllm.internal.test:8000/v1"
    assert provider["scope"] == "global"
    assert provider["metadata"]["envManaged"] is True
    assert provider["metadata"]["providerTemplate"] == "vllm"

    credential = (
        await db_session.execute(LlmProviderCredential.__table__.select())
    ).mappings().one()
    assert credential["provider_id"] == provider["id"]
    assert credential["source"] == "env"
    assert credential["env_var_name"] == "VLLM_API_KEY"
    assert credential["masked_hint"] == "env:VLLM_API_KEY"

    model = (await db_session.execute(LlmModel.__table__.select())).mappings().one()
    assert model["provider_id"] == provider["id"]
    assert model["model_id"] == "deepseek_v4"
    assert model["display_name"] == "deepseek_v4"


@pytest.mark.asyncio
async def test_environment_bootstrap_does_not_overwrite_user_configured_provider(
    db_session,
    monkeypatch,
):
    user_provider = LlmProvider(
        name="vLLM",
        kind="vllm",
        base_url="http://ui.example.test/v1",
        scope="user",
        workspace_id="00000000-0000-0000-0000-000000000001",
        user_id="user-1",
        enabled=True,
        provider_metadata={"providerTemplate": "vllm"},
    )
    db_session.add(user_provider)
    await db_session.commit()

    monkeypatch.setenv("VLLM_BASE_URL", "http://env.example.test/v1")
    monkeypatch.setenv("VLLM_API_KEY", "env-key")
    monkeypatch.setenv("VLLM_MODEL", "env-model")
    monkeypatch.setattr(
        "app.services.llm.bootstrap.LlmCatalogService.discover_models_unchecked",
        _noop_discovery,
    )

    await sync_environment_llm_catalog(db_session)

    await db_session.refresh(user_provider)
    assert user_provider.base_url == "http://ui.example.test/v1"

    providers = (
        await db_session.execute(LlmProvider.__table__.select())
    ).mappings().all()
    assert any(
        provider["scope"] == "global"
        and provider["base_url"] == "http://env.example.test/v1"
        for provider in providers
    )


@pytest.mark.asyncio
async def test_environment_bootstrap_runs_live_discovery(db_session, monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm.internal.test:8000/v1")
    monkeypatch.setenv("VLLM_API_KEY", "vllm")
    monkeypatch.delenv("VLLM_MODEL", raising=False)

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers=None, params=None):
            return httpx.Response(
                200,
                json={"data": [{"id": "bootstrap-model", "object": "model"}]},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )

    await sync_environment_llm_catalog(db_session)

    models = (await db_session.execute(LlmModel.__table__.select())).mappings().all()
    assert any(model["model_id"] == "bootstrap-model" for model in models)


@pytest.mark.asyncio
async def test_cohere_template_discovers_models_from_native_models_api(
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("COHERE_API_KEY", "cohere-key")
    requested: list[tuple[str, dict | None]] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers=None, params=None):
            assert params == {"page_size": 1000, "endpoint": "chat"}
            requested.append((url, headers))
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "command-a-03-2025",
                            "endpoints": ["chat"],
                            "context_length": 256000,
                        }
                    ]
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )
    provider = LlmProvider(
        name="Cohere",
        kind="cohere",
        base_url="https://api.cohere.ai/compatibility/v1",
        scope="user",
        workspace_id=None,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "cohere"},
    )
    credential = LlmProviderCredential(
        provider=provider,
        source="env",
        env_var_name="COHERE_API_KEY",
        masked_hint="env:COHERE_API_KEY",
    )
    db_session.add(provider)
    db_session.add(credential)
    await db_session.commit()

    discovered = await LlmCatalogService(db_session).discover_models_unchecked(
        provider,
        network_access="unrestricted",
    )

    assert requested == [
        (
            "https://api.cohere.com/v1/models",
            {"Authorization": "Bearer cohere-key"},
        )
    ]
    assert [model.model_id for model in discovered] == ["command-a-03-2025"]
    assert discovered[0].context_length == 256000


@pytest.mark.asyncio
async def test_cohere_discovery_honors_custom_provider_base_url(
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("COHERE_API_KEY", "cohere-key")
    requested: list[str] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers=None, params=None):
            del headers, params
            requested.append(url)
            return httpx.Response(
                200,
                json={"models": [{"name": "gateway-command", "endpoints": ["chat"]}]},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )
    provider = LlmProvider(
        name="Cohere gateway",
        kind="cohere",
        base_url="https://cohere-gateway.example/v1",
        scope="user",
        workspace_id=None,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "cohere"},
    )
    credential = LlmProviderCredential(
        provider=provider,
        source="env",
        env_var_name="COHERE_API_KEY",
        masked_hint="env:COHERE_API_KEY",
    )
    db_session.add(provider)
    db_session.add(credential)
    await db_session.commit()

    discovered = await LlmCatalogService(db_session).discover_models_unchecked(
        provider,
        network_access="unrestricted",
    )

    assert requested == ["https://cohere-gateway.example/v1/models"]
    assert [model.model_id for model in discovered] == ["gateway-command"]


@pytest.mark.asyncio
async def test_perplexity_template_uses_static_models(
    db_session,
):
    provider = LlmProvider(
        name="Perplexity",
        kind="perplexity",
        base_url="https://api.perplexity.ai",
        scope="user",
        workspace_id=None,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "perplexity"},
    )
    db_session.add(provider)
    await db_session.commit()

    discovered = await LlmCatalogService(db_session).discover_models_unchecked(
        provider,
        network_access="unrestricted",
    )

    assert [model.model_id for model in discovered] == [
        "sonar",
        "sonar-pro",
        "sonar-reasoning-pro",
        "sonar-deep-research",
    ]
    assert discovered[2].supports_reasoning is True


@pytest.mark.asyncio
async def test_environment_bootstrap_swallows_discovery_errors_without_logging_secrets(
    db_session,
    monkeypatch,
    caplog,
):
    secret = "sentinel-bootstrap-gemini-secret"
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm.internal.test:8000/v1")
    monkeypatch.setenv("VLLM_API_KEY", secret)
    monkeypatch.setenv("VLLM_MODEL", "deepseek_v4")

    async def _boom(self, provider, **kwargs):
        del self, provider, kwargs
        request = httpx.Request(
            "GET",
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": secret},
        )
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError(
            "provider rejected discovery",
            request=request,
            response=response,
        )

    monkeypatch.setattr(
        "app.services.llm.bootstrap.LlmCatalogService.discover_models_unchecked",
        _boom,
    )

    # Discovery failure must not break startup bootstrap.
    await sync_environment_llm_catalog(db_session)

    model = (await db_session.execute(LlmModel.__table__.select())).mappings().one()
    assert model["model_id"] == "deepseek_v4"
    assert secret not in caplog.text

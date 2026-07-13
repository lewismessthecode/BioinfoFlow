from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
import os
from urllib.parse import urlsplit

import pytest

from app.config import settings
from app.models.llm import (
    LlmCredentialSource,
    LlmModel,
    LlmProvider,
    LlmProviderCredential,
)
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.agent_core.transcript import AgentTranscriptStore, parts_to_text
from app.services.llm.credentials import encrypt_secret
from app.services.llm.provider_templates import normalize_provider_base_url
from app.workspace import DEFAULT_WORKSPACE_ID


_LIVE_TEST_ENV = "BIOINFOFLOW_LIVE_RELAY"
_REQUIRED_ENV = (
    "BIOINFOFLOW_RELAY_BASE_URL",
    "BIOINFOFLOW_RELAY_API_KEY",
    "BIOINFOFLOW_RELAY_MODEL",
)
_ALLOW_INSECURE_HTTP_ENV = "BIOINFOFLOW_RELAY_ALLOW_INSECURE_HTTP"


@dataclass(frozen=True)
class RelayConfig:
    base_url: str
    model: str
    api_key: str = field(repr=False)


def load_relay_config(environ: Mapping[str, str]) -> RelayConfig:
    if environ.get(_LIVE_TEST_ENV) != "1":
        pytest.skip(f"Set {_LIVE_TEST_ENV}=1 to enable the live relay test.")

    missing = [name for name in _REQUIRED_ENV if not environ.get(name)]
    if missing:
        pytest.skip(
            "Missing required relay environment variables: " + ", ".join(missing)
        )

    base_url = environ["BIOINFOFLOW_RELAY_BASE_URL"].strip().rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Relay base URL must be an absolute HTTP(S) URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(
            "Relay base URL must not contain credentials, a query, or a fragment."
        )
    if parsed.scheme == "http" and environ.get(_ALLOW_INSECURE_HTTP_ENV) != "1":
        raise ValueError(
            f"Plain HTTP requires explicit {_ALLOW_INSECURE_HTTP_ENV}=1 opt-in."
        )
    if parsed.path.rstrip("/").endswith("/responses"):
        raise ValueError(
            "Relay base URL must be the API root (usually ending in /v1), not the "
            "/responses endpoint."
        )

    return RelayConfig(
        base_url=base_url,
        api_key=environ["BIOINFOFLOW_RELAY_API_KEY"],
        model=environ["BIOINFOFLOW_RELAY_MODEL"].strip(),
    )


def test_live_relay_config_requires_explicit_http_opt_in() -> None:
    with pytest.raises(ValueError, match="Plain HTTP requires explicit"):
        load_relay_config(
            {
                _LIVE_TEST_ENV: "1",
                "BIOINFOFLOW_RELAY_BASE_URL": "http://relay.example/v1",
                "BIOINFOFLOW_RELAY_API_KEY": "sentinel-secret",
                "BIOINFOFLOW_RELAY_MODEL": "gpt-test",
            }
        )


def test_live_relay_config_repr_redacts_api_key() -> None:
    secret = "sentinel-secret-never-render"
    config = load_relay_config(
        {
            _LIVE_TEST_ENV: "1",
            "BIOINFOFLOW_RELAY_BASE_URL": "https://relay.example/v1",
            "BIOINFOFLOW_RELAY_API_KEY": secret,
            "BIOINFOFLOW_RELAY_MODEL": "gpt-test",
        }
    )

    assert secret not in repr(config)


def test_secret_leak_guard_reports_a_fixed_redacted_message() -> None:
    secret = "sentinel-secret-never-report"
    with pytest.raises(pytest.fail.Exception) as caught:
        _fail_if_secret_present(secret, f"unsafe surface: {secret}")

    assert str(caught.value) == "Sensitive relay credential leaked into test evidence."
    assert secret not in str(caught.value)


@pytest.mark.asyncio
async def test_responses_relay_contract_completes_full_agentcore_path(
    db_session,
    monkeypatch,
    caplog,
) -> None:
    secret = "sentinel-mock-relay-secret"
    caplog.set_level("INFO")
    monkeypatch.setattr(settings, "agent_retry_max_attempts", 1)
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    async with _mock_responses_server() as (base_url, requests):
        model = await _seed_relay_model(
            db_session,
            name="Mock Responses relay",
            base_url=base_url,
            model_name="gpt-5.4-mini",
            api_key=secret,
            allow_insecure_http=True,
        )
        service = AgentCoreService(db_session)
        session = await service.create_session(
            project_id=None,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            title="Mock Responses relay",
            model_selection={"model_id": str(model.id)},
        )
        turn = await service.create_turn_record(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Reply exactly MOCK_RELAY_OK.",
        )
        completed = await service.runtime.run_turn(str(turn.id))

    assert completed.status == "completed"
    assert completed.final_text == "MOCK_RELAY_OK"
    assert len(requests) == 1
    request = requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "/v1/responses"
    assert request["headers"]["authorization"] == f"Bearer {secret}"
    payload = json.loads(request["body"])
    assert payload["store"] is False
    assert payload["include"] == ["reasoning.encrypted_content"]

    events = await service.list_events_for_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    messages = await AgentTranscriptStore(db_session).list_messages(str(session.id))
    _assert_secret_absent(
        secret,
        turn=completed,
        events=events,
        messages=messages,
        logs=caplog.text,
    )
    assert "MOCK_RELAY_OK" in parts_to_text(messages[-1].content_parts or [])
    assert events[-1].type == "turn.completed"


@pytest.mark.live_relay
@pytest.mark.asyncio
async def test_live_responses_relay_completes_agentcore_and_redacts_secrets(
    db_session,
    monkeypatch,
    caplog,
) -> None:
    config = load_relay_config(os.environ)
    caplog.set_level("INFO")
    monkeypatch.setattr(settings, "agent_retry_base_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "agent_retry_max_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "agent_retry_max_attempts", 1)

    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    await db_session.commit()
    model = await _seed_relay_model(
        db_session,
        name="Live Responses relay",
        base_url=config.base_url,
        model_name=config.model,
        api_key=config.api_key,
        allow_insecure_http=urlsplit(config.base_url).scheme == "http",
    )

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Live Responses relay",
        model_selection={"model_id": str(model.id)},
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text=(
            "Do not call tools. Reply with exactly LIVE_RELAY_OK and no other text."
        ),
    )

    async with asyncio.timeout(90):
        completed = await service.runtime.run_turn(str(turn.id))

    events = await service.list_events_for_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    messages = await AgentTranscriptStore(db_session).list_messages(str(session.id))
    _assert_secret_absent(
        config.api_key,
        turn=completed,
        events=events,
        messages=messages,
        logs=caplog.text,
    )

    if completed.status != "completed":
        assert completed.error_code == "model_request_failed"
        pytest.fail(
            "The configured relay did not complete the Responses turn: "
            f"{completed.error_message}"
        )

    assert "LIVE_RELAY_OK" in (completed.final_text or "")
    expected_base_url = normalize_provider_base_url(
        "openai_compatible", config.base_url
    )
    assert completed.model_profile_snapshot["resolved_model_target"] == {
        "endpoint_id": str(model.provider_id),
        "provider_kind": "openai_compatible",
        "model_name": config.model,
        "wire_protocol": "responses",
        "base_url": expected_base_url,
    }
    assert [message.role for message in messages] == ["user", "assistant"]
    assert "LIVE_RELAY_OK" in parts_to_text(messages[-1].content_parts or [])
    event_types = [event.type for event in events]
    assert "model.selected" in event_types
    assert "assistant.text.completed" in event_types
    assert event_types[-1] == "turn.completed"

    failing_model = await _seed_relay_model(
        db_session,
        name="Failing Responses relay",
        base_url="http://127.0.0.1:1/v1",
        model_name=config.model,
        api_key=config.api_key,
        allow_insecure_http=True,
    )
    failing_session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Failing Responses relay",
        model_selection={"model_id": str(failing_model.id)},
    )
    failing_turn = await service.create_turn_record(
        session_id=str(failing_session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="This request must fail safely.",
    )

    async with asyncio.timeout(30):
        failed = await service.runtime.run_turn(str(failing_turn.id))

    failed_events = await service.list_events_for_turn(
        turn_id=str(failing_turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    failed_messages = await AgentTranscriptStore(db_session).list_messages(
        str(failing_session.id)
    )
    _assert_secret_absent(
        config.api_key,
        turn=failed,
        events=failed_events,
        messages=failed_messages,
        logs=caplog.text,
    )
    assert failed.status == "failed"
    assert failed.error_code == "model_request_failed"
    assert failed.error_message
    assert failed_events[-1].type == "turn.failed"


async def _seed_relay_model(
    db_session,
    *,
    name: str,
    base_url: str,
    model_name: str,
    api_key: str,
    allow_insecure_http: bool,
) -> LlmModel:
    provider = LlmProvider(
        name=name,
        kind="openai_compatible",
        wire_protocol="responses",
        base_url=base_url,
        allow_insecure_http=allow_insecure_http,
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    db_session.add(
        LlmProviderCredential(
            provider_id=str(provider.id),
            source=LlmCredentialSource.STORED,
            encrypted_secret=encrypt_secret(api_key),
            masked_hint="configured for live test",
            updated_by="dev",
        )
    )
    model = LlmModel(
        provider_id=str(provider.id),
        model_id=model_name,
        display_name=model_name,
        supports_tools=False,
        supports_streaming=True,
        supports_reasoning=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


def _assert_secret_absent(
    secret: str,
    *,
    turn,
    events,
    messages,
    logs: str,
) -> None:
    persisted = json.dumps(
        {
            "turn": {
                "status": turn.status,
                "final_text": turn.final_text,
                "error_code": turn.error_code,
                "error_message": turn.error_message,
                "model_profile_snapshot": turn.model_profile_snapshot,
            },
            "events": [event.payload for event in events],
            "messages": [
                {
                    "role": message.role,
                    "content_parts": message.content_parts,
                    "message_metadata": message.message_metadata,
                }
                for message in messages
            ],
        },
        default=str,
        sort_keys=True,
    )
    _fail_if_secret_present(secret, persisted, logs)


def _fail_if_secret_present(secret: str, *surfaces: str) -> None:
    if secret and any(secret in surface for surface in surfaces):
        pytest.fail(
            "Sensitive relay credential leaked into test evidence.",
            pytrace=False,
        )


def _mock_responses_sse() -> bytes:
    message = {
        "id": "message-mock-relay",
        "type": "message",
        "role": "assistant",
        "phase": "final_answer",
        "content": [{"type": "output_text", "text": "MOCK_RELAY_OK"}],
    }
    events = [
        {
            "type": "response.created",
            "response": {
                "id": "resp-mock-relay",
                "object": "response",
                "created_at": 1,
                "model": "gpt-5.4-mini",
                "status": "in_progress",
                "output": [],
            },
        },
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {**message, "content": []},
        },
        {
            "type": "response.output_text.delta",
            "item_id": message["id"],
            "output_index": 0,
            "delta": "MOCK_RELAY_OK",
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": message,
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp-mock-relay",
                "object": "response",
                "created_at": 1,
                "model": "gpt-5.4-mini",
                "status": "completed",
                "output": [message],
            },
        },
    ]
    body = "".join(
        f"data: {json.dumps(event, separators=(',', ':'))}\n\n" for event in events
    )
    return f"{body}data: [DONE]\n\n".encode()


@asynccontextmanager
async def _mock_responses_server():
    requests: list[dict] = []

    async def handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        method, path, _version = lines[0].split(" ", 2)
        headers = {
            name.strip().lower(): value.strip()
            for line in lines[1:]
            if ":" in line
            for name, value in [line.split(":", 1)]
        }
        content_length = int(headers.get("content-length", "0"))
        body = await reader.readexactly(content_length) if content_length else b""
        requests.append(
            {
                "method": method,
                "path": path,
                "headers": headers,
                "body": body,
            }
        )
        response_body = _mock_responses_sse()
        writer.write(
            (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/event-stream\r\n"
                "Cache-Control: no-cache\r\n"
                "Connection: close\r\n"
                f"Content-Length: {len(response_body)}\r\n"
                "\r\n"
            ).encode("ascii")
            + response_body
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}/v1", requests
    finally:
        server.close()
        await server.wait_closed()

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.models.llm import (
    LlmCredentialSource,
    LlmModel,
    LlmModelProfile,
    LlmProvider,
    LlmProviderCredential,
)
from app.services.agent_harness.contracts import (
    InputTextPart,
    MessageCommand,
    OpenSessionRequest,
)
from app.services.agent_harness.factory import (
    harness_for_database,
    resolve_model_snapshot,
)
from app.services.agent_harness.model_target import (
    model_target_from_snapshot,
    private_model_snapshot,
)
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelEvent,
    TextDelta,
)
from app.services.model_runtime.errors import ModelError
from app.utils.exceptions import AppError


WORKSPACE_ID = "30000000-0000-0000-0000-000000000001"


def _message(command_id: str, text: str) -> MessageCommand:
    return MessageCommand(
        command_id=command_id,
        parts=[InputTextPart(text=text)],
    )


class RecordingModel:
    def __init__(self) -> None:
        self.invocations = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        yield TextDelta(text="done")
        yield CompletionMetadata(response_id="response-1", finish_reason="stop")


class FailingRecordingModel:
    def __init__(self) -> None:
        self.invocations = []

    async def invoke(self, invocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        raise ModelError(
            category="provider",
            message="primary model failed",
            retryable=False,
            replay_safe=True,
        )
        yield  # pragma: no cover - keep this an async generator


@pytest.mark.asyncio
async def test_model_snapshot_uses_a_stable_error_when_no_model_is_available(
    harness_db,
) -> None:
    with pytest.raises(AppError) as exc_info:
        await resolve_model_snapshot(
            harness_db,
            workspace_id=WORKSPACE_ID,
            user_id="user-1",
            selection=None,
        )

    assert exc_info.value.code == "AGENT_MODEL_REQUIRED"
    assert exc_info.value.status_code == 422


def test_private_model_snapshot_discards_legacy_fallback_strategy() -> None:
    snapshot = private_model_snapshot(
        {
            "runtime_strategy": {
                "use_streaming": False,
                "allow_thinking": True,
                "allow_tools": True,
                "max_tokens": 1024,
                "fallback_model_ids": ["legacy-fallback-model"],
            }
        }
    )

    assert snapshot["runtime_strategy"] == {
        "use_streaming": False,
        "allow_thinking": True,
        "allow_tools": True,
        "max_tokens": 1024,
        "reasoning_effort": None,
    }
    assert "fallback" not in repr(snapshot).lower()
    assert "reasoning_budget" not in repr(snapshot)


@pytest.mark.parametrize(
    "snapshot",
    [
        {
            "endpoint_id": "endpoint-1",
            "provider_kind": "openai",
            "model_name": "gpt-test",
            "routed_model_name": "openai/gpt-test",
            "wire_protocol": "responses",
        },
        {
            "target": {
                "endpoint_id": "endpoint-1",
                "provider": "openai",
                "model": "gpt-test",
                "routed_model_name": "openai/gpt-test",
                "wire_protocol": "responses",
                "api_base": "https://example.test/v1",
            }
        },
    ],
)
def test_model_target_rejects_legacy_flat_or_aliased_snapshot(snapshot) -> None:
    with pytest.raises(ValueError, match="current target structure"):
        model_target_from_snapshot(snapshot)


def test_model_target_accepts_current_private_snapshot_structure() -> None:
    target = model_target_from_snapshot(
        {
            "target": {
                "endpoint_id": "endpoint-1",
                "provider_kind": "openai",
                "model_name": "gpt-test",
                "routed_model_name": "openai/gpt-test",
                "wire_protocol": "responses",
                "base_url": "https://example.test/v1",
                "network_access": "public_only",
                "target_revision": "revision-1",
            }
        }
    )

    assert target.endpoint_id == "endpoint-1"
    assert target.provider_kind == "openai"
    assert target.model_name == "gpt-test"
    assert target.resolved_model_name() == "openai/gpt-test"
    assert target.base_url == "https://example.test/v1"


@pytest.mark.asyncio
@pytest.mark.parametrize("selection_kind", ["provider_model", "model_id", "profile_id"])
async def test_model_snapshot_resolves_each_api_selection_without_persisting_secret(
    harness_db,
    monkeypatch,
    selection_kind: str,
) -> None:
    provider, model, profile = await _catalog(
        harness_db,
        monkeypatch,
        api_key="session-secret",
    )
    selections = {
        "provider_model": {
            "provider": str(provider.id),
            "model": model.model_id,
        },
        "model_id": {"model_id": str(model.id)},
        "profile_id": {"profile_id": str(profile.id)},
    }

    snapshot = await resolve_model_snapshot(
        harness_db,
        workspace_id=WORKSPACE_ID,
        user_id="user-1",
        selection=selections[selection_kind],
    )

    assert snapshot["model_id"] == str(model.id)
    assert snapshot["target"] == {
        "endpoint_id": str(provider.id),
        "provider_kind": "anthropic",
        "model_name": "claude-test",
        "routed_model_name": "anthropic/claude-test",
        "wire_protocol": "chat_completions",
        "base_url": None,
        "target_revision": snapshot["target"]["target_revision"],
        "network_access": "public_only",
    }
    assert snapshot["capabilities"] == {
        "supports_streaming": False,
        "supports_reasoning": True,
        "supports_tools": False,
        "supports_vision": False,
    }
    assert "api_key" not in repr(snapshot)
    assert "session-secret" not in repr(snapshot)


@pytest.mark.asyncio
async def test_model_snapshot_preserves_openai_responses_runtime(
    harness_db,
    monkeypatch,
) -> None:
    provider, model, _profile = await _catalog(
        harness_db,
        monkeypatch,
        api_key="openai-secret",
        provider_kind="openai",
        wire_protocol="responses",
        model_name="gpt-test",
    )

    snapshot = await resolve_model_snapshot(
        harness_db,
        workspace_id=WORKSPACE_ID,
        user_id="user-1",
        selection={"provider": str(provider.id), "model": model.model_id},
    )

    assert snapshot["target"]["provider_kind"] == "openai"
    assert snapshot["target"]["wire_protocol"] == "responses"
    assert snapshot["target"]["routed_model_name"] == "openai/gpt-test"
    assert "openai-secret" not in repr(snapshot)


@pytest.mark.asyncio
async def test_model_snapshot_preserves_vision_capability(
    harness_db,
    monkeypatch,
) -> None:
    provider, model, _profile = await _catalog(
        harness_db,
        monkeypatch,
        api_key="vision-secret",
        supports_vision=True,
    )

    snapshot = await resolve_model_snapshot(
        harness_db,
        workspace_id=WORKSPACE_ID,
        user_id="user-1",
        selection={"provider": str(provider.id), "model": model.model_id},
    )

    assert snapshot["capabilities"]["supports_vision"] is True
    assert "vision-secret" not in repr(snapshot)


@pytest.mark.asyncio
async def test_harness_resolves_current_credential_for_every_model_invocation(
    harness_db,
    monkeypatch,
    tmp_path,
) -> None:
    _provider, model, _profile = await _catalog(
        harness_db,
        monkeypatch,
        api_key="session-secret",
    )
    snapshot = await resolve_model_snapshot(
        harness_db,
        workspace_id=WORKSPACE_ID,
        user_id="user-1",
        selection={"model_id": str(model.id)},
    )
    recording = RecordingModel()
    harness = harness_for_database(harness_db, model_gateway=recording)
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            prompt_snapshot={"content": "Help the user."},
            model=snapshot,
            workspace={"root": str(tmp_path), "runtime": "local"},
        )
    )
    persisted = await harness.repository.get_session(str(opened.session.id))
    assert persisted is not None
    assert "session-secret" not in repr(persisted.model_snapshot)
    assert "api_key" not in repr(persisted.model_snapshot)

    await harness.dispatch(
        str(opened.session.id),
        _message("message-1", "Use the first credential."),
    )
    monkeypatch.setenv("TEST_AGENT_MODEL_KEY", "rotated-secret")
    await harness.dispatch(
        str(opened.session.id),
        _message("message-2", "Use the rotated credential."),
    )

    assert len(recording.invocations) == 2
    assert recording.invocations[0].target.resolved_api_key() == "session-secret"
    assert recording.invocations[1].target.resolved_api_key() == "rotated-secret"


@pytest.mark.asyncio
async def test_harness_rejects_legacy_resolved_model_id_snapshot(
    harness_db,
    monkeypatch,
    tmp_path,
) -> None:
    _provider, model, _profile = await _catalog(
        harness_db,
        monkeypatch,
        api_key="legacy-secret",
    )
    recording = RecordingModel()
    harness = harness_for_database(harness_db, model_gateway=recording)
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            prompt_snapshot={"content": "Reject old model snapshots."},
            model={"resolved_model_id": str(model.id)},
            workspace={"root": str(tmp_path), "runtime": "local"},
        )
    )

    await harness.dispatch(
        str(opened.session.id),
        _message("legacy-model", "Do not invoke the provider."),
    )

    snapshot = await harness.snapshot(str(opened.session.id))
    assert recording.invocations == []
    assert snapshot.runs[-1].status == "failed"
    assert snapshot.runs[-1].error is not None
    assert snapshot.runs[-1].error.model_dump() == {
        "code": "agent_failed",
        "message": "The Agent run failed.",
    }


@pytest.mark.asyncio
async def test_harness_applies_resolved_model_capabilities_and_profile_strategy(
    harness_db,
    monkeypatch,
    tmp_path,
) -> None:
    _provider, _model, profile = await _catalog(
        harness_db,
        monkeypatch,
        api_key="runtime-secret",
    )
    snapshot = await resolve_model_snapshot(
        harness_db,
        workspace_id=WORKSPACE_ID,
        user_id="user-1",
        selection={"profile_id": str(profile.id)},
    )
    recording = RecordingModel()
    harness = harness_for_database(harness_db, model_gateway=recording)
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            prompt_snapshot={"content": "Help the user."},
            model=snapshot,
            workspace={"root": str(tmp_path), "runtime": "local"},
        )
    )

    await harness.dispatch(
        str(opened.session.id),
        _message("message-1", "Respect the model profile."),
    )

    invocation = recording.invocations[0]
    assert invocation.stream is False
    assert invocation.tools == ()
    assert invocation.max_output_tokens == 321
    assert invocation.reasoning.enabled is False
    assert invocation.reasoning.effort is None


@pytest.mark.asyncio
async def test_harness_profile_uses_only_primary_model_without_fallback_snapshot(
    harness_db,
    monkeypatch,
    tmp_path,
) -> None:
    provider, primary_model, profile = await _catalog(
        harness_db,
        monkeypatch,
        api_key="primary-secret",
    )
    fallback_model = LlmModel(
        provider_id=str(provider.id),
        model_id="claude-fallback",
        display_name="claude-fallback",
        supports_tools=True,
        supports_streaming=True,
        supports_reasoning=False,
        max_output_tokens=2048,
    )
    harness_db.add(fallback_model)
    await harness_db.flush()
    profile.fallback_model_ids = [str(fallback_model.id)]
    await harness_db.commit()

    snapshot = await resolve_model_snapshot(
        harness_db,
        workspace_id=WORKSPACE_ID,
        user_id="user-1",
        selection={"profile_id": str(profile.id)},
    )

    assert profile.fallback_model_ids == [str(fallback_model.id)]
    assert snapshot["model_id"] == str(primary_model.id)
    assert "fallback" not in repr(snapshot).lower()

    recording = FailingRecordingModel()
    harness = harness_for_database(harness_db, model_gateway=recording)
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            prompt_snapshot={"content": "Use only the selected primary model."},
            model=snapshot,
            workspace={"root": str(tmp_path), "runtime": "local"},
        )
    )
    await harness.dispatch(
        str(opened.session.id),
        _message("message-1", "Complete this request."),
    )

    assert len(recording.invocations) == 1
    assert recording.invocations[0].target.model_name == primary_model.model_id
    failed = await harness.snapshot(str(opened.session.id))
    assert failed.runs[-1].status == "failed"
    assert failed.runs[-1].error is not None
    assert failed.runs[-1].error.model_dump() == {
        "code": "agent_failed",
        "message": "The Agent run failed.",
    }


async def _catalog(
    harness_db,
    monkeypatch,
    *,
    api_key: str,
    provider_kind: str = "anthropic",
    wire_protocol: str = "chat_completions",
    model_name: str = "claude-test",
    supports_vision: bool = False,
):
    monkeypatch.setenv("TEST_AGENT_MODEL_KEY", api_key)
    provider = LlmProvider(
        name=f"{provider_kind} test",
        kind=provider_kind,
        wire_protocol=wire_protocol,
        scope="global",
        enabled=True,
    )
    harness_db.add(provider)
    await harness_db.flush()
    harness_db.add(
        LlmProviderCredential(
            provider_id=str(provider.id),
            source=LlmCredentialSource.ENV,
            env_var_name="TEST_AGENT_MODEL_KEY",
        )
    )
    model = LlmModel(
        provider_id=str(provider.id),
        model_id=model_name,
        display_name=model_name,
        supports_tools=False,
        supports_streaming=False,
        supports_vision=supports_vision,
        supports_reasoning=True,
        max_output_tokens=4096,
    )
    harness_db.add(model)
    await harness_db.flush()
    profile = LlmModelProfile(
        name="No tools",
        task_type="agent",
        primary_model_id=str(model.id),
        max_tokens=321,
        prefer_streaming=True,
        allow_thinking=False,
        allow_tools=True,
        scope="global",
        enabled=True,
    )
    harness_db.add(profile)
    await harness_db.commit()
    return provider, model, profile

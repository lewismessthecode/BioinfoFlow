from __future__ import annotations

import asyncio
import json
import sys

import pytest

from app.config import Settings, settings
from app.models.agent_core import AgentActionStatus
from app.models.llm import LlmModel, LlmModelProfile, LlmProvider
from app.repositories.agent_core_repo import AgentActionRepository, AgentEventRepository
from app.services.agent_core import AgentCoreService
from app.services.agent_core.context import AgentContextAssembler
from app.services.agent_core.core.loop import _max_iterations
from app.services.agent_core.tools.executor import ToolExecutionResult
from app.services.agent_core.runtime import AgentCoreRuntime
import app.services.agent_core.runner as runner_module
from app.workspace import DEFAULT_WORKSPACE_ID
from app.models.workspace import Workspace


async def _workspace(db_session) -> Workspace:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    return workspace


async def _seed_catalog_model(
    db_session,
    *,
    model_id: str,
    provider: LlmProvider | None = None,
) -> LlmModel:
    if provider is None:
        provider = LlmProvider(
            name=f"{model_id} provider",
            kind="openai_compatible",
            base_url="https://models.internal.example/v1",
            scope="user",
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            enabled=True,
            provider_metadata={"providerTemplate": "openai-compatible"},
        )
        db_session.add(provider)
        await db_session.commit()
        await db_session.refresh(provider)
    model = LlmModel(
        provider_id=str(provider.id),
        model_id=model_id,
        display_name=model_id,
        supports_tools=True,
        supports_streaming=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


def test_agent_max_iterations_prefers_explicit_setting(monkeypatch):
    monkeypatch.setattr(settings, "agent_max_iterations", 120)

    assert _max_iterations() == 120


@pytest.mark.asyncio
async def test_runtime_rejects_unapproved_public_http_provider(db_session):
    await _workspace(db_session)
    provider = LlmProvider(
        name="Unapproved public relay",
        kind="openai_compatible",
        base_url="http://8.129.13.231:8079/v1",
        allow_insecure_http=False,
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()
    model = await _seed_catalog_model(
        db_session,
        model_id="gpt-5.6-sol",
        provider=provider,
    )

    resolved = await AgentCoreRuntime(db_session)._catalog_selection(
        {"model_id": str(model.id)},
        source="test",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert resolved is None


@pytest.mark.asyncio
async def test_runtime_allows_explicit_public_http_provider(db_session):
    await _workspace(db_session)
    provider = LlmProvider(
        name="Approved public relay",
        kind="openai_compatible",
        base_url="http://8.129.13.231:8079/v1",
        allow_insecure_http=True,
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()
    model = await _seed_catalog_model(
        db_session,
        model_id="gpt-5.6-sol",
        provider=provider,
    )

    resolved = await AgentCoreRuntime(db_session)._catalog_selection(
        {"model_id": str(model.id)},
        source="test",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert resolved is not None
    assert resolved["request_args"]["api_base"] == "http://8.129.13.231:8079/v1"


def test_agent_max_rounds_legacy_setting_is_removed(monkeypatch):
    monkeypatch.delenv("AGENT_MAX_ROUNDS", raising=False)
    isolated_settings = Settings(_env_file=None)

    assert not hasattr(isolated_settings, "agent_max_rounds")
    assert not hasattr(settings, "agent_max_rounds")


def test_agent_max_iterations_defaults_to_90(monkeypatch):
    monkeypatch.delenv("AGENT_MAX_ITERATIONS", raising=False)

    assert Settings(_env_file=None).agent_max_iterations == 90


@pytest.mark.asyncio
async def test_runtime_approval_resume_uses_remaining_turn_budget(
    db_session, monkeypatch
):
    model_calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal model_calls
        model_calls += 1

        usage_values = {
            1: {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            2: {"prompt_tokens": 7, "completion_tokens": 11, "total_tokens": 18},
        }

        class FakeUsage:
            def model_dump(self):
                return usage_values.get(model_calls, {})

        class FakeResponse:
            usage = FakeUsage()

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        class FakeFunction:
            if model_calls == 1:
                name = "bash"
                arguments = json.dumps(
                    {
                        "command": f"{sys.executable} -c 'print(\"approved\")'",
                        "cwd": str(settings.bioinfoflow_home),
                    }
                )
            else:
                name = "projects__list"
                arguments = "{}"

        class FakeToolCall:
            id = f"tool-call-{model_calls}"
            function = FakeFunction()

        message = FakeMessage()
        if model_calls <= 2:
            message.content = ""
            message.tool_calls = [FakeToolCall()]
        else:
            message.content = "A third model call must not fit in this turn budget."
            message.tool_calls = None
        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr(settings, "agent_max_iterations", 2)
    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="approval-budget-model")

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    session = await service.session_repo.update_all(
        session,
        toolset_policy={"name": "execution"},
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Run the approved tool within one bounded turn.",
    )

    waiting_turn = await service.runtime.run_turn(str(turn.id))
    assert waiting_turn.status == "waiting_approval"
    monkeypatch.setattr(settings, "agent_max_iterations", 5)
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    resumed_turn = await service.runtime.resume_turn_after_action(str(actions[0].id))

    assert model_calls == 2
    assert resumed_turn.status == "failed"
    assert resumed_turn.error_code == "iteration_budget_exhausted"
    assert resumed_turn.iteration_count == 2
    assert resumed_turn.budget_snapshot == {
        "used_iterations": 2,
        "max_iterations": 2,
    }
    assert resumed_turn.token_usage == {
        "prompt_tokens": 9,
        "completion_tokens": 14,
        "total_tokens": 23,
    }


def test_agent_max_rounds_legacy_env_is_rejected(monkeypatch):
    monkeypatch.delenv("AGENT_MAX_ITERATIONS", raising=False)
    monkeypatch.setenv("AGENT_MAX_ROUNDS", "12")

    with pytest.raises(ValueError, match="AGENT_MAX_ROUNDS"):
        Settings(_env_file=None)


@pytest.mark.asyncio
async def test_context_replays_committed_transcript_messages(db_session, monkeypatch):
    async def fake_completion(*args, **kwargs):
        class FakeMessage:
            content = "Committed assistant reply."
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="replay-model")

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Replay this transcript.",
    )
    completed_turn = await service.runtime.run_turn(str(turn.id))

    messages = await AgentContextAssembler(db_session).provider_messages(
        agent_session=session,
        turn=completed_turn,
    )

    assert [message["role"] for message in messages] == ["system", "user", "assistant"]
    assert messages[1]["content"] == "Replay this transcript."
    assert messages[2]["content"] == "Committed assistant reply."


@pytest.mark.asyncio
async def test_runtime_retries_transient_model_failure_and_records_event(
    db_session, monkeypatch
):
    attempts = 0

    async def flaky_completion(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("Provider timed out")

        class FakeMessage:
            content = "Succeeded after retry."
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", flaky_completion)
    monkeypatch.setattr(settings, "agent_retry_base_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "agent_retry_max_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "agent_retry_max_attempts", 2)
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="retry-model")

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Retry this request.",
    )
    completed_turn = await service.runtime.run_turn(str(turn.id))
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))

    assert attempts == 2
    assert completed_turn.status == "completed"
    assert completed_turn.final_text == "Succeeded after retry."
    assert any(event.type == "model.retrying" for event in events)


@pytest.mark.asyncio
async def test_runtime_falls_back_to_profile_model(db_session, monkeypatch):
    async def fallback_completion(*args, **kwargs):
        model_name = str(kwargs["model"])
        if "primary-model" in model_name:
            raise RuntimeError("Provider timed out")

        class FakeMessage:
            content = "Answered from fallback."
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    monkeypatch.setattr(
        "app.services.agent_core.runtime.acompletion", fallback_completion
    )
    monkeypatch.setattr(settings, "agent_retry_base_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "agent_retry_max_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "agent_retry_max_attempts", 2)
    await _workspace(db_session)
    provider = LlmProvider(
        name="fallback provider",
        kind="openai_compatible",
        base_url="https://models.internal.example/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    primary = await _seed_catalog_model(
        db_session, model_id="primary-model", provider=provider
    )
    fallback = await _seed_catalog_model(
        db_session, model_id="fallback-model", provider=provider
    )
    profile = LlmModelProfile(
        name="Fallback profile",
        task_type="agent",
        primary_model_id=str(primary.id),
        fallback_model_ids=[str(fallback.id)],
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        default_model_profile_id=str(profile.id),
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Use the fallback model if needed.",
    )
    completed_turn = await service.runtime.run_turn(str(turn.id))
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))

    assert completed_turn.status == "completed"
    assert completed_turn.final_text == "Answered from fallback."
    assert completed_turn.model_profile_snapshot["resolved_model_id"] == str(
        fallback.id
    )
    assert any(event.type == "model.fallback" for event in events)


@pytest.mark.asyncio
async def test_runtime_stops_on_repeated_tool_calls_without_progress(
    db_session, monkeypatch
):
    calls = 0

    async def looping_completion(*args, **kwargs):
        nonlocal calls
        calls += 1

        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        class FakeFunction:
            name = "projects__list"
            arguments = "{}"

        class FakeToolCall:
            id = f"tool-call-{calls}"
            function = FakeFunction()

        message = FakeMessage()
        message.content = ""
        message.tool_calls = [FakeToolCall()]
        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr(
        "app.services.agent_core.runtime.acompletion", looping_completion
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="no-progress-model")

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Keep calling the same tool.",
    )
    failed_turn = await service.runtime.run_turn(str(turn.id))
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))

    assert calls == 3
    assert failed_turn.status == "failed"
    assert failed_turn.termination_reason == "no_progress"
    assert failed_turn.error_code == "no_progress_detected"
    assert events[-1].type == "turn.no_progress"


@pytest.mark.asyncio
async def test_runtime_allows_repeated_tool_polling_when_results_change(
    db_session, monkeypatch
):
    calls = 0
    tool_executions = 0

    async def polling_completion(*args, **kwargs):
        nonlocal calls
        calls += 1

        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        if calls <= 3:

            class FakeMessage:
                pass

            class FakeFunction:
                name = "projects__list"
                arguments = "{}"

            class FakeToolCall:
                id = f"tool-call-{calls}"
                function = FakeFunction()

            message = FakeMessage()
            message.content = ""
            message.tool_calls = [FakeToolCall()]
        else:

            class FakeMessage:
                content = "The repeated status check completed."
                tool_calls = None

            message = FakeMessage()

        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    async def changing_tool_result(*args, **kwargs):
        nonlocal tool_executions
        tool_executions += 1
        return ToolExecutionResult(
            action_id=f"action-{tool_executions}",
            status="completed",
            result={"state": f"running-{tool_executions}"},
        )

    monkeypatch.setattr(
        "app.services.agent_core.runtime.acompletion", polling_completion
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.executor.AgentToolExecutor.execute",
        changing_tool_result,
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="polling-model")

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Poll until the tool result settles.",
    )
    completed_turn = await service.runtime.run_turn(str(turn.id))
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))

    assert calls == 4
    assert tool_executions == 3
    assert completed_turn.status == "completed"
    assert completed_turn.final_text == "The repeated status check completed."
    assert not any(event.type == "turn.no_progress" for event in events)


@pytest.mark.asyncio
async def test_runtime_resets_repeat_grace_when_tool_results_change(
    db_session, monkeypatch
):
    model_calls = 0
    tool_executions = 0
    states = ["running-1", "running-2", "running-3", "running-3"]

    async def polling_completion(*args, **kwargs):
        nonlocal model_calls
        model_calls += 1

        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        if model_calls <= len(states):

            class FakeMessage:
                pass

            class FakeFunction:
                name = "projects__list"
                arguments = "{}"

            class FakeToolCall:
                id = f"tool-call-{model_calls}"
                function = FakeFunction()

            message = FakeMessage()
            message.content = ""
            message.tool_calls = [FakeToolCall()]
        else:

            class FakeMessage:
                content = "Polling completed after one stable observation."
                tool_calls = None

            message = FakeMessage()

        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    async def changing_then_stable_result(*args, **kwargs):
        nonlocal tool_executions
        tool_executions += 1
        return ToolExecutionResult(
            action_id=f"action-{tool_executions}",
            status="completed",
            result={"state": states[tool_executions - 1]},
        )

    monkeypatch.setattr(
        "app.services.agent_core.runtime.acompletion", polling_completion
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.executor.AgentToolExecutor.execute",
        changing_then_stable_result,
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="stable-polling-model")

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Poll until the result has been stable long enough.",
    )
    completed_turn = await service.runtime.run_turn(str(turn.id))

    assert model_calls == 5
    assert tool_executions == 4
    assert completed_turn.status == "completed"
    assert (
        completed_turn.final_text == "Polling completed after one stable observation."
    )


@pytest.mark.asyncio
async def test_runtime_fails_visibly_when_model_calls_unexposed_tool(
    db_session, monkeypatch
):
    async def fake_completion(*args, **kwargs):
        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        class FakeFunction:
            name = "bash"
            arguments = json.dumps({"command": "echo should-not-run"})

        class FakeToolCall:
            id = "tool-call-unexposed"
            function = FakeFunction()

        message = FakeMessage()
        message.content = ""
        message.tool_calls = [FakeToolCall()]
        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="unexposed-tool-model")

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    session = await service.session_repo.update_all(
        session, toolset_policy={"name": "plan"}
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Try an unexposed tool.",
    )

    failed_turn = await service.runtime.run_turn(str(turn.id))
    events = await AgentEventRepository(db_session).list_for_turn(turn_id=str(turn.id))

    assert failed_turn.status == "failed"
    assert failed_turn.termination_reason == "tool_failed"
    assert failed_turn.error_code == "tool_not_exposed"
    assert "not exposed" in (failed_turn.error_message or "")
    assert events[-1].type == "turn.failed"
    assert events[-1].payload["error_code"] == "tool_not_exposed"


@pytest.mark.asyncio
async def test_recovery_reenqueues_requested_tool_actions(db_session, monkeypatch):
    calls = 0
    resumed: list[tuple[str, str]] = []

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        calls += 1

        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        message = FakeMessage()
        if calls == 1:

            class FakeFunction:
                name = "bash"
                arguments = json.dumps(
                    {
                        "command": f"{sys.executable} -c 'print(\"recover\")'",
                        "cwd": str(settings.bioinfoflow_home),
                    }
                )

            class FakeToolCall:
                id = "tool-call-recover"
                function = FakeFunction()

            message.content = ""
            message.tool_calls = [FakeToolCall()]
        else:
            message.content = "Recovered."
            message.tool_calls = None

        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume",
        lambda action_id, turn_id, _session_id=None: resumed.append(
            (action_id, turn_id)
        ),
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="recovery-model")

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    session = await service.session_repo.update_all(
        session, toolset_policy={"name": "execution"}
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Approve and recover this action.",
    )
    waiting_turn = await service.runtime.run_turn(str(turn.id))
    action = (await AgentActionRepository(db_session).list_for_turn(str(turn.id)))[0]

    assert waiting_turn.status == "waiting_approval"
    decided = await service.decide_action(
        action_id=str(action.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    assert decided.status == AgentActionStatus.REQUESTED

    resumed.clear()
    summary = await service.recover_orphaned_turns()

    assert summary["enqueued"] == 1
    assert resumed == [(str(action.id), str(turn.id))]


@pytest.mark.asyncio
async def test_enqueue_turn_resume_waits_for_running_task_to_finish(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[tuple[str, str]] = []

    async def fake_run_turn_once(turn_id: str):
        calls.append(("run", turn_id))
        started.set()
        await release.wait()
        return "ran"

    async def fake_resume_turn_once(action_id: str):
        calls.append(("resume", action_id))
        return "resumed"

    runner_module._RUNNING_TURNS.clear()
    runner_module._PENDING_TURN_TASK_FACTORIES.clear()
    monkeypatch.setattr(runner_module, "run_turn_once", fake_run_turn_once)
    monkeypatch.setattr(runner_module, "resume_turn_once", fake_resume_turn_once)

    runner_module.enqueue_turn_run("turn-1")
    await started.wait()
    runner_module.enqueue_turn_resume("action-1", "turn-1")

    assert calls == [("run", "turn-1")]
    assert "turn-1" in runner_module._PENDING_TURN_TASK_FACTORIES

    release.set()
    for _ in range(20):
        if len(calls) == 2 and "turn-1" not in runner_module._RUNNING_TURNS:
            break
        await asyncio.sleep(0)

    assert calls == [("run", "turn-1"), ("resume", "action-1")]
    assert "turn-1" not in runner_module._RUNNING_TURNS
    assert "turn-1" not in runner_module._PENDING_TURN_TASK_FACTORIES


@pytest.mark.asyncio
async def test_runner_failure_log_uses_safe_metadata(monkeypatch):
    records: list[tuple[str, str, dict]] = []

    class SpyLogger:
        def error(self, event: str, **fields):
            records.append(("error", event, fields))

        def info(self, event: str, **fields):
            records.append(("info", event, fields))

    monkeypatch.setattr(runner_module, "logger", SpyLogger())
    task = asyncio.get_running_loop().create_future()
    task.set_exception(RuntimeError("secret prompt and provider payload"))

    runner_module._log_task_result("turn-1", "session-1", task)

    assert records == [
        (
            "error",
            "agent_core.runner.failed",
            {
                "session_id": "session-1",
                "turn_id": "turn-1",
                "exception_type": "RuntimeError",
            },
        )
    ]

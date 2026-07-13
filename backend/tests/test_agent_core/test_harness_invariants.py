from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

import app.services.agent_core.ledger as ledger_module
from app.config import settings
from app.models.llm import LlmModel, LlmProvider
from app.models.project import Project
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentEventRepository,
    AgentMessageRepository,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core import service as service_module
from app.services.agent_core.context.system_prompt import (
    default_system_prompt_snapshot,
    resolve_system_prompt_prefix,
)
from app.services.agent_core.execution_target import session_metadata_with_execution_target
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolSpec,
    build_default_tool_registry,
)
from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.agent_core.tools.toolsets import ToolsetExposure
from app.utils.exceptions import BadRequestError, PermissionDeniedError
from app.workspace import DEFAULT_WORKSPACE_ID


async def _workspace(db_session) -> Workspace:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    return workspace


async def _project(db_session) -> Project:
    project = Project(
        name="Harness Project",
        description="Agent harness invariant tests",
        user_id="dev",
        created_by_user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


class _FakeFilesystemPolicy:
    def require_allowed_path(self, path, *, must_exist=True, allow_directory=False):
        target = Path(path)
        if must_exist:
            assert target.exists()
        if not allow_directory:
            assert target.is_file()
        return target


async def _seed_catalog_model(
    db_session, *, model_id: str = "harness-model"
) -> LlmModel:
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


@pytest.mark.asyncio
async def test_session_can_start_without_project_and_keeps_prompt_snapshot(db_session):
    await _workspace(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Workspace triage",
    )

    assert session.project_id is None
    assert session.runtime_mode == "api"
    assert session.prompt_snapshot["id"] == "bioinfoflow-agent-v8"
    assert session.toolset_policy["name"] == "execution"


def test_v8_system_prompt_is_a_compact_provider_neutral_agent_core():
    snapshot = default_system_prompt_snapshot()

    assert snapshot.id == "bioinfoflow-agent-v8"
    assert len(snapshot.content) < 6000
    assert "You are an agent operating through" in snapshot.content
    assert "latest user request" in snapshot.content
    assert "target context" in snapshot.content
    assert "observe" in snapshot.content.lower()
    assert "act" in snapshot.content.lower()
    assert "verify" in snapshot.content.lower()
    assert "reasonable assumptions" in snapshot.content
    assert "smallest sufficient dedicated tool" in snapshot.content
    assert "shell" in snapshot.content
    assert "schemas and identifiers exactly" in snapshot.content
    assert "independent read-only work" in snapshot.content
    assert "Do not repeat unchanged failures" in snapshot.content
    assert "Approval authorizes an action" in snapshot.content
    assert "read-back" in snapshot.content
    assert "Preserve unrelated user changes" in snapshot.content
    assert "Keep communication concise" in snapshot.content
    assert "Bioinfoflow platform workflow" not in snapshot.content
    assert "Before submitting a run" not in snapshot.content


def test_old_prompt_snapshot_resolves_to_live_v8_prompt():
    resolved = resolve_system_prompt_prefix(
        {"id": "bioinfoflow-agent-v6", "content": "old prompt"}
    )

    assert resolved == default_system_prompt_snapshot().content


@pytest.mark.asyncio
async def test_first_turn_generates_session_title(db_session):
    await _workspace(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Summarize this very long workflow request with many details",
    )

    updated = await service.require_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert updated.title == "Summarize this very long"


@pytest.mark.asyncio
async def test_first_turn_does_not_overwrite_existing_session_title(db_session):
    await _workspace(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Manual title",
    )
    await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Generate a different title",
    )

    updated = await service.require_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert updated.title == "Manual title"


@pytest.mark.asyncio
async def test_invalid_file_ref_does_not_commit_queued_turn(
    db_session, tmp_path, monkeypatch
):
    await _workspace(db_session)
    secret = tmp_path / ".env"
    secret.write_text("TOKEN=secret", encoding="utf-8")
    monkeypatch.setattr(
        service_module, "FilesystemPolicy", lambda: _FakeFilesystemPolicy()
    )

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    with pytest.raises(PermissionDeniedError):
        await service.create_turn_record(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Use this file.",
            input_parts=[{"kind": "file_ref", "path": str(secret), "label": ".env"}],
        )

    assert await service.turn_repo.list_for_session(str(session.id)) == []


@pytest.mark.asyncio
async def test_invalid_workflow_ref_does_not_commit_queued_turn(db_session):
    await _workspace(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    with pytest.raises(BadRequestError):
        await service.create_turn_record(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Draft a run plan.",
            input_parts=[
                {"type": "text", "text": "Draft a run plan."},
                {"kind": "workflow_ref", "scope": "admin"},
            ],
        )

    assert await service.turn_repo.list_for_session(str(session.id)) == []


@pytest.mark.asyncio
async def test_workflow_ref_writes_canonical_user_message(db_session):
    await _workspace(db_session)

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
        input_text="Draft a run plan.",
        input_parts=[
            {"type": "text", "text": "Draft a run plan."},
            {"kind": "workflow_ref", "scope": "global"},
        ],
    )

    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assert str(messages[0].turn_id) == str(turn.id)
    text = "\n".join(part["text"] for part in messages[0].content_parts)
    assert "Draft a run plan." in text
    assert "Workflow context: All registered workflows" in text
    assert "Scope: all registered workflows" in text


@pytest.mark.asyncio
async def test_file_ref_without_text_part_keeps_user_prompt(
    db_session, tmp_path, monkeypatch
):
    await _workspace(db_session)
    workflow = tmp_path / "workflow.wdl"
    workflow.write_text("version 1.0\nworkflow demo {}", encoding="utf-8")
    monkeypatch.setattr(
        service_module, "FilesystemPolicy", lambda: _FakeFilesystemPolicy()
    )

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
        input_text="Summarize this workflow.",
        input_parts=[
            {"kind": "file_ref", "path": str(workflow), "label": "workflow.wdl"}
        ],
    )

    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assert str(messages[0].turn_id) == str(turn.id)
    text = "\n".join(part["text"] for part in messages[0].content_parts)
    assert "Summarize this workflow." in text
    assert "workflow demo" in text


@pytest.mark.asyncio
async def test_turn_writes_canonical_user_and_assistant_messages(
    db_session, monkeypatch
):
    async def fake_completion(*args, **kwargs):
        class FakeUsage:
            def model_dump(self):
                return {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}

        class FakeMessage:
            content = "Use hg38 for this project."
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = FakeUsage()

        return FakeResponse()

    monkeypatch.setattr(
        "app.services.agent_core.core.loop.acompletion", fake_completion
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

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
        input_text="Remember that we use hg38.",
    )
    turn = await service.runtime.run_turn(str(turn.id))

    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assert turn.termination_reason == "assistant_final"
    assert [(message.role, message.status) for message in messages] == [
        ("user", "committed"),
        ("assistant", "committed"),
    ]
    assert messages[0].content_parts == [
        {"type": "text", "text": "Remember that we use hg38."}
    ]
    assert messages[1].content_parts == [
        {"type": "text", "text": "Use hg38 for this project."}
    ]


@pytest.mark.asyncio
async def test_event_sequence_is_session_scoped_across_turns(db_session, monkeypatch):
    async def fake_completion(*args, **kwargs):
        class FakeMessage:
            content = "ok"
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    monkeypatch.setattr(
        "app.services.agent_core.core.loop.acompletion", fake_completion
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    for text in ["first", "second"]:
        turn = await service.create_turn_record(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text=text,
        )
        await service.runtime.run_turn(str(turn.id))

    events = await AgentEventRepository(db_session).list_for_session(
        session_id=str(session.id)
    )
    assert [event.seq for event in events] == list(range(1, len(events) + 1))


@pytest.mark.asyncio
async def test_event_ledger_serializes_concurrent_sequence_allocation():
    class FakeSessionRepository:
        async def lock_for_update(self, session_id: str):
            assert session_id == "session-1"
            return object()

    class FakeSession:
        async def rollback(self):
            return None

    class FakeEvent:
        def __init__(self, seq: int):
            self.seq = seq

    class RacingEventRepository:
        session = FakeSession()

        def __init__(self):
            self.current = 0

        async def next_seq(self, session_id: str) -> int:
            assert session_id == "session-1"
            next_seq = self.current + 1
            await asyncio.sleep(0)
            return next_seq

        async def create(self, **payload):
            await asyncio.sleep(0)
            seq = payload["seq"]
            if seq != self.current + 1:
                raise AssertionError("event sequence allocation raced")
            self.current = seq
            return FakeEvent(seq)

    ledger = AgentEventLedger.__new__(AgentEventLedger)
    ledger.event_repo = RacingEventRepository()
    ledger.session_repo = FakeSessionRepository()

    first, second = await asyncio.gather(
        ledger.append(
            session_id="session-1",
            turn_id="turn-1",
            type="turn.created",
        ),
        ledger.append(
            session_id="session-1",
            turn_id="turn-2",
            type="turn.created",
        ),
    )

    assert sorted([first.seq, second.seq]) == [1, 2]


@pytest.mark.asyncio
async def test_event_ledger_logs_event_append_at_debug(monkeypatch):
    records: list[tuple[str, str, dict]] = []

    class FakeSessionRepository:
        async def lock_for_update(self, session_id: str):
            assert session_id == "session-1"
            return object()

    class SpyLogger:
        def info(self, event: str, **fields):
            records.append(("info", event, fields))

        def debug(self, event: str, **fields):
            records.append(("debug", event, fields))

    class FakeSession:
        async def rollback(self):
            return None

    class FakeEvent:
        def __init__(self, seq: int):
            self.seq = seq

    class FakeEventRepository:
        session = FakeSession()

        async def next_seq(self, session_id: str) -> int:
            assert session_id == "session-1"
            return 7

        async def create(self, **payload):
            return FakeEvent(payload["seq"])

    monkeypatch.setattr(ledger_module, "logger", SpyLogger())
    ledger = AgentEventLedger.__new__(AgentEventLedger)
    ledger.event_repo = FakeEventRepository()
    ledger.session_repo = FakeSessionRepository()

    await ledger.append(
        session_id="session-1",
        turn_id="turn-1",
        type="assistant.text.completed",
        payload={"content": "large reply", "status": "completed"},
    )

    assert not [
        record
        for record in records
        if record[:2] == ("info", "agent_core.event.appended")
    ]
    debug_logs = [
        fields
        for level, event_name, fields in records
        if level == "debug" and event_name == "agent_core.event.appended"
    ]
    assert debug_logs == [
        {
            "session_id": "session-1",
            "turn_id": "turn-1",
            "seq": 7,
            "event_type": "assistant.text.completed",
            "status": "completed",
        }
    ]


def test_toolset_exposure_does_not_expose_shell_by_default():
    registry = build_default_tool_registry()

    default_tools = ToolsetExposure(registry).exposed_specs(
        policy={"name": "default"},
        role="orchestrator",
    )
    elevated_tools = ToolsetExposure(registry).exposed_specs(
        policy={"name": "execution"},
        role="orchestrator",
    )

    assert "bash" not in {tool.name for tool in default_tools}
    assert "bash" in {tool.name for tool in elevated_tools}


def test_platform_tool_exposure_keeps_read_tools_available_and_mutations_gated():
    registry = build_default_tool_registry()
    exposure = ToolsetExposure(registry)

    plan_tools = exposure.exposed_names(policy={"name": "plan"})
    default_tools = exposure.exposed_names(policy={"name": "default"})
    execution_tools = exposure.exposed_names(policy={"name": "execution"})

    read_tools = {
        "projects.list",
        "projects.get",
        "projects.workflows.list",
        "workflows.list",
        "workflows.get",
        "workflows.form_spec",
        "workflows.dag",
        "workflows.source",
        "images.list",
        "images.get",
        "runs.list",
        "runs.get",
        "runs.logs",
        "runs.outputs",
        "runs.dag",
        "runs.audit",
        "scheduler.status",
        "scheduler.resources",
    }
    mutating_tools = {
        "projects.create",
        "projects.update",
        "projects.delete",
        "projects.workflows.bind",
        "projects.workflows.unbind",
        "projects.workflows.pin",
        "workflows.create",
        "workflows.update",
        "workflows.delete",
        "images.pull",
        "images.build",
        "images.delete",
        "runs.submit",
        "runs.cancel",
        "runs.retry",
        "runs.resume",
        "runs.cleanup",
        "runs.delete",
    }

    assert read_tools <= plan_tools
    assert read_tools <= default_tools
    assert read_tools <= execution_tools
    assert mutating_tools.isdisjoint(plan_tools)
    assert mutating_tools.isdisjoint(default_tools)
    assert mutating_tools <= execution_tools


@pytest.mark.asyncio
async def test_worker_tool_call_is_rechecked_against_worker_exposure(
    db_session, monkeypatch
):
    async def fake_completion(*args, **kwargs):
        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        class FakeFunction:
            name = "ask_user"
            arguments = json.dumps(
                {
                    "questions": [
                        {
                            "question": "Should the worker pause?",
                            "header": "Pause",
                            "options": [
                                {"label": "Yes", "description": "Pause."},
                                {"label": "No", "description": "Continue."},
                            ],
                        }
                    ]
                }
            )

        class FakeToolCall:
            id = "worker-ask-user"
            function = FakeFunction()

        class FakeMessage:
            content = ""
            tool_calls = [FakeToolCall()]

        choice = FakeChoice()
        choice.message = FakeMessage()
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr(
        "app.services.agent_core.core.loop.acompletion", fake_completion
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        role_profile="worker",
        toolset_policy={"name": "execution"},
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Worker should not ask user.",
    )

    completed_turn = await service.runtime.run_turn(str(turn.id))

    assert completed_turn.termination_reason == "tool_failed"
    assert completed_turn.error_code == "tool_not_exposed"
    assert await AgentActionRepository(db_session).list_for_turn(str(turn.id)) == []


@pytest.mark.asyncio
async def test_unexposed_tool_is_denied_before_argument_validation(db_session):
    await _workspace(db_session)
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
        input_text="Try hidden tool.",
    )

    executor = AgentToolExecutor(db_session, build_default_tool_registry())
    with pytest.raises(PermissionDeniedError, match="not exposed"):
        await executor.execute(
            tool_name="bash",
            input={},
            context=AgentToolContext(
                db=db_session,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                session_id=str(session.id),
                turn_id=str(turn.id),
            ),
            toolset_policy={"name": "default"},
        )


@pytest.mark.asyncio
async def test_remote_ssh_executor_rejects_stale_local_tool_call(db_session):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        metadata={
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": "conn-1",
            }
        },
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Try stale local shell.",
    )

    executor = AgentToolExecutor(db_session, build_default_tool_registry())
    with pytest.raises(PermissionDeniedError, match="not exposed"):
        await executor.execute(
            tool_name="bash",
            input={"command": "pwd"},
            context=AgentToolContext(
                db=db_session,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                session_id=str(session.id),
                turn_id=str(turn.id),
            ),
            toolset_policy={"name": "execution"},
            execution_target={"type": "remote_ssh", "connection_id": "conn-1"},
        )

    assert await AgentActionRepository(db_session).list_for_turn(str(turn.id)) == []


@pytest.mark.asyncio
async def test_executor_prefers_persisted_session_target_over_explicit_argument(
    db_session,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        metadata={
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": "conn-1",
            }
        },
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Try stale local shell with explicit local override.",
    )

    executor = AgentToolExecutor(db_session, build_default_tool_registry())
    with pytest.raises(PermissionDeniedError, match="not exposed"):
        await executor.execute(
            tool_name="bash",
            input={"command": "pwd"},
            context=AgentToolContext(
                db=db_session,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                session_id=str(session.id),
                turn_id=str(turn.id),
            ),
            toolset_policy={"name": "execution"},
            execution_target={"type": "local"},
        )


@pytest.mark.asyncio
async def test_approval_resume_executes_tool_and_continues_turn(
    db_session, monkeypatch
):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        calls += 1

        class FakeUsage:
            def model_dump(self):
                return {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

        class FakeResponse:
            usage = FakeUsage()

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
                        "command": f"{sys.executable} -c 'print(\"approved-tool\")'",
                        "cwd": str(settings.bioinfoflow_home),
                    }
                )

            class FakeToolCall:
                id = "tool-call-1"
                function = FakeFunction()

            message.content = ""
            message.tool_calls = [FakeToolCall()]
        else:
            messages = kwargs["messages"]
            assistant_tool_call = next(
                message for message in messages if message.get("tool_calls")
            )
            tool_result = next(
                message for message in messages if message["role"] == "tool"
            )
            canonical_call_id = assistant_tool_call["tool_calls"][0]["id"]
            assert canonical_call_id.startswith("tc_")
            assert assistant_tool_call["tool_calls"][0]["function"]["name"] == "bash"
            assert tool_result["tool_call_id"] == canonical_call_id
            message.content = "Final after approved tool."
            message.tool_calls = None

        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

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
        input_text="Run approved shell and report back.",
    )

    waiting_turn = await service.runtime.run_turn(str(turn.id))
    assert waiting_turn.status == "waiting_approval"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert actions[0].status == "waiting_decision"
    assert actions[0].exposure_policy["execution_target"] == {"type": "local"}

    decided = await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    assert decided.status == "requested"

    resumed_turn = await service.runtime.resume_turn_after_action(str(actions[0].id))
    assert resumed_turn.status == "completed"
    assert resumed_turn.final_text == "Final after approved tool."

    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assert [message.role for message in messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert "approved-tool" in messages[2].content_parts[0]["text"]


@pytest.mark.asyncio
async def test_rejected_tool_decision_continues_turn_with_tool_result(
    db_session, monkeypatch
):
    calls = 0

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
                        "command": f"{sys.executable} -c 'print(\"should-not-run\")'",
                        "cwd": str(settings.bioinfoflow_home),
                    }
                )

            class FakeToolCall:
                id = "tool-call-rejected"
                function = FakeFunction()

            message.content = ""
            message.tool_calls = [FakeToolCall()]
        else:
            tool_result = next(
                item for item in kwargs["messages"] if item["role"] == "tool"
            )
            assert tool_result["tool_call_id"].startswith("tc_")
            assert "UserRejected" in tool_result["content"]
            message.content = "I will continue without running that tool."
            message.tool_calls = None

        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

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
        input_text="Try shell only if approved.",
    )

    waiting_turn = await service.runtime.run_turn(str(turn.id))
    assert waiting_turn.status == "waiting_approval"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))

    decided = await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="reject",
    )
    assert decided.status == "rejected"

    resumed_turn = await service.runtime.resume_turn_after_action(str(actions[0].id))
    assert resumed_turn.status == "completed"
    assert resumed_turn.final_text == "I will continue without running that tool."


@pytest.mark.asyncio
async def test_tool_batch_stops_at_first_interaction_and_defers_later_calls(
    db_session,
    monkeypatch,
):
    model_calls = 0
    turn_id = ""

    async def fake_completion(*args, **kwargs):
        nonlocal model_calls
        model_calls += 1

        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        message = FakeMessage()
        if model_calls == 1:

            class AskFunction:
                name = "ask_user"
                arguments = json.dumps(
                    {
                        "questions": [
                            {
                                "question": "Which option should be used?",
                                "header": "Choice",
                                "options": [
                                    {"label": "A", "description": "Use option A."},
                                    {"label": "B", "description": "Use option B."},
                                ],
                            }
                        ]
                    }
                )

            class ListFunction:
                name = "projects__list"
                arguments = "{}"

            class AskCall:
                id = "tool-call-question"
                function = AskFunction()

            class ListCall:
                id = "tool-call-projects"
                function = ListFunction()

            message.content = ""
            message.tool_calls = [AskCall(), ListCall()]
        else:
            persisted_turn = await service.turn_repo.get(turn_id)
            progress = persisted_turn.loop_state["progress"]
            assert [
                json.loads(signature)["name"]
                for signature in progress["previous_tool_calls"]
            ] == ["ask_user", "projects__list"]
            assert [
                json.loads(signature)["status"]
                for signature in progress["previous_tool_results"]
            ] == ["completed", "deferred"]
            assert progress["repeat_count"] == 1
            assert "pending_observation" not in progress
            emitted_ids = [
                call["id"]
                for item in kwargs["messages"]
                for call in item.get("tool_calls", [])
            ]
            result_ids = [
                item.get("tool_call_id")
                for item in kwargs["messages"]
                if item.get("role") == "tool"
            ]
            assert result_ids == emitted_ids
            message.content = "Continued after the answer."
            message.tool_calls = None

        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="interaction-batch-model")

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
        input_text="Ask one question before doing anything else.",
    )
    turn_id = str(turn.id)

    waiting_turn = await service.runtime.run_turn(str(turn.id))
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )

    assert waiting_turn.status == "waiting_approval"
    assert [action.name for action in actions] == ["ask_user"]
    progress = waiting_turn.loop_state["progress"]
    pending = progress["pending_observation"]
    assert [json.loads(signature)["name"] for signature in pending["tool_calls"]] == [
        "ask_user",
        "projects__list",
    ]
    pending_results = [json.loads(signature) for signature in pending["tool_results"]]
    assert [result["status"] for result in pending_results] == ["pending", "deferred"]
    assert pending_results[0]["tool_call_id"] == actions[0].tool_call_id
    assert pending_results[0]["tool_call_id"].startswith("tc_")
    assert progress["repeat_count"] == 0
    assert not any(message.role == "tool" for message in messages)

    await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="answer",
        answer={"Choice": "A"},
    )
    resumed_turn = await service.runtime.resume_turn_after_action(str(actions[0].id))

    assert model_calls == 2
    assert resumed_turn.status == "completed"
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    tool_messages = [message for message in messages if message.role == "tool"]
    assistant_call_ids = [
        call["id"]
        for message in messages
        if message.role == "assistant"
        for part in message.content_parts
        if part.get("type") == "tool_calls"
        for call in part.get("tool_calls") or []
    ]
    assert [
        message.message_metadata["tool_call_id"] for message in tool_messages
    ] == assistant_call_ids
    assert "DeferredToolCall" in tool_messages[1].content_parts[0]["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_repeated_approval_results_contribute_to_no_progress_history(
    db_session,
    monkeypatch,
    decision,
):
    model_calls = 0

    async def repeated_approval_completion(*args, **kwargs):
        nonlocal model_calls
        del args, kwargs
        model_calls += 1

        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        class FakeFunction:
            name = "bash"
            arguments = json.dumps(
                {
                    "command": f"{sys.executable} -c 'print(\"stable\")'",
                    "cwd": str(settings.bioinfoflow_home),
                }
            )

        class FakeToolCall:
            id = f"tool-call-approval-{model_calls}"
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
        "app.services.agent_core.runtime.acompletion",
        repeated_approval_completion,
    )
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id=f"repeated-{decision}-model")

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
        input_text="Repeat the same approval-gated observation.",
    )

    current_turn = await service.runtime.run_turn(str(turn.id))
    for repeat_index in range(3):
        assert current_turn.status == "waiting_approval"
        actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
        pending_action = next(
            action for action in actions if action.status == "waiting_decision"
        )
        await service.decide_action(
            action_id=str(pending_action.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            decision=decision,
        )
        current_turn = await service.runtime.resume_turn_after_action(
            str(pending_action.id)
        )
        if repeat_index < 2:
            assert current_turn.status == "waiting_approval"

    assert model_calls == 3
    assert current_turn.status == "failed"
    assert current_turn.termination_reason == "no_progress"
    assert current_turn.error_code == "no_progress_detected"
    assert current_turn.loop_state["progress"]["repeat_count"] == 3


@pytest.mark.asyncio
async def test_ask_each_action_static_reads_execute_once_and_close_all_call_ids(
    db_session,
    monkeypatch,
):
    model_calls = 0

    async def read_batch_completion(*args, **kwargs):
        nonlocal model_calls
        model_calls += 1

        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        message = FakeMessage()
        if model_calls == 1:
            class ProjectsFunction:
                name = "projects__list"
                arguments = "{}"

            class WorkflowsFunction:
                name = "workflows__list"
                arguments = "{}"

            class ProjectsCall:
                id = "tool-call-static-projects"
                function = ProjectsFunction()

            class WorkflowsCall:
                id = "tool-call-static-workflows"
                function = WorkflowsFunction()

            message.content = ""
            message.tool_calls = [ProjectsCall(), WorkflowsCall()]
        else:
            emitted_ids = {
                call["id"]
                for item in kwargs["messages"]
                for call in item.get("tool_calls", [])
            }
            result_ids = {
                item.get("tool_call_id")
                for item in kwargs["messages"]
                if item.get("role") == "tool"
            }
            assert emitted_ids == result_ids
            message.content = "Both static reads completed."
            message.tool_calls = None

        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr(
        "app.services.agent_core.runtime.acompletion", read_batch_completion
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="ask-each-read-model")

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="ask_each_action",
    )
    session = await service.session_repo.update_all(
        session,
        toolset_policy={"name": "execution"},
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Read projects and workflows once.",
    )

    completed_turn = await service.runtime.run_turn(str(turn.id))
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))

    assert completed_turn.status == "completed"
    assert model_calls == 2
    assert sorted(action.name for action in actions) == ["projects.list", "workflows.list"]
    assert all(action.status == "completed" for action in actions)
    result_call_ids = {
        message.message_metadata.get("tool_call_id")
        for message in messages
        if message.role == "tool"
    }
    assert len(result_call_ids) == 2
    assert all(call_id.startswith("tc_") for call_id in result_call_ids)


@pytest.mark.asyncio
async def test_dynamic_risk_read_tool_does_not_join_concurrent_batch(
    db_session,
    monkeypatch,
):
    class DynamicRiskReadTool:
        spec = AgentToolSpec(
            name="dynamic.read",
            description="A read-shaped tool whose input can elevate its risk.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"type": "object"},
            risk_level="read",
        )

        def assess_risk(self, input):
            del input
            return "act_high"

        async def run(self, input, context):
            del input, context
            return {"executed": True}

    registry = build_default_tool_registry()
    registry.register(DynamicRiskReadTool())
    monkeypatch.setattr(
        "app.services.agent_core.core.loop.build_default_tool_registry",
        lambda: registry,
    )

    async def fake_completion(*args, **kwargs):
        del args, kwargs

        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        class DynamicFunction:
            name = "dynamic__read"
            arguments = "{}"

        class ListFunction:
            name = "projects__list"
            arguments = "{}"

        class DynamicCall:
            id = "tool-call-dynamic"
            function = DynamicFunction()

        class ListCall:
            id = "tool-call-projects-after-dynamic"
            function = ListFunction()

        message = FakeMessage()
        message.content = ""
        message.tool_calls = [DynamicCall(), ListCall()]
        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="dynamic-risk-batch-model")

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
        input_text="Run the dynamic read before listing projects.",
    )

    waiting_turn = await service.runtime.run_turn(str(turn.id))
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))

    assert waiting_turn.status == "waiting_approval"
    assert [action.name for action in actions] == ["dynamic.read"]
    assert not any(message.role == "tool" for message in messages)


@pytest.mark.asyncio
async def test_tool_batch_stops_at_first_approval_and_defers_later_mutation(
    db_session,
    monkeypatch,
    tmp_path,
):
    model_calls = 0
    deferred_path = tmp_path / "must-not-be-written.txt"

    async def fake_completion(*args, **kwargs):
        nonlocal model_calls
        model_calls += 1

        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        message = FakeMessage()
        if model_calls == 1:

            class BashFunction:
                name = "bash"
                arguments = json.dumps(
                    {
                        "command": f"{sys.executable} -c 'print(\"approved\")'",
                        "cwd": str(settings.bioinfoflow_home),
                    }
                )

            class WriteFunction:
                name = "files__write"
                arguments = json.dumps(
                    {"path": str(deferred_path), "content": "must not be written"}
                )

            class BashCall:
                id = "tool-call-bash"
                function = BashFunction()

            class WriteCall:
                id = "tool-call-write"
                function = WriteFunction()

            message.content = ""
            message.tool_calls = [BashCall(), WriteCall()]
        else:
            emitted_ids = [
                call["id"]
                for item in kwargs["messages"]
                for call in item.get("tool_calls", [])
            ]
            result_ids = [
                item.get("tool_call_id")
                for item in kwargs["messages"]
                if item.get("role") == "tool"
            ]
            assert result_ids == emitted_ids
            message.content = "Continued without the deferred mutation."
            message.tool_calls = None

        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="mutation-batch-model")

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
        input_text="Run one approved command, but do not batch later mutations.",
    )

    waiting_turn = await service.runtime.run_turn(str(turn.id))
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )

    assert waiting_turn.status == "waiting_approval"
    assert [action.name for action in actions] == ["bash"]
    assert not deferred_path.exists()
    assert not any(message.role == "tool" for message in messages)

    await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    resumed_turn = await service.runtime.resume_turn_after_action(str(actions[0].id))

    assert model_calls == 2
    assert resumed_turn.status == "completed"
    assert not deferred_path.exists()
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    tool_messages = [message for message in messages if message.role == "tool"]
    assistant_call_ids = [
        call["id"]
        for message in messages
        if message.role == "assistant"
        for part in message.content_parts
        if part.get("type") == "tool_calls"
        for call in part.get("tool_calls") or []
    ]
    assert [
        message.message_metadata["tool_call_id"] for message in tool_messages
    ] == assistant_call_ids
    assert "DeferredToolCall" in tool_messages[1].content_parts[0]["text"]


@pytest.mark.asyncio
async def test_resume_stale_local_tool_for_remote_session_records_failed_result(
    db_session,
    monkeypatch,
):
    async def fake_completion(*args, **kwargs):
        del args, kwargs

        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        class FakeFunction:
            name = "bash"
            arguments = json.dumps({"command": "pwd"})

        class FakeToolCall:
            id = "tool-call-stale"
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
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="ask_each_action",
    )
    session = await service.session_repo.update_all(
        session, toolset_policy={"name": "execution"}
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Request local shell, then target becomes remote.",
    )

    waiting_turn = await service.runtime.run_turn(str(turn.id))
    assert waiting_turn.status == "waiting_approval"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert actions[0].status == "waiting_decision"

    await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    current_session = await service.session_repo.get_fresh(str(session.id))
    await service.session_repo.update_all(
        current_session,
        session_metadata=session_metadata_with_execution_target(
            current_session.session_metadata,
            {"type": "remote_ssh", "connection_id": "conn-1"},
        ),
    )

    resumed_turn = await service.runtime.resume_turn_after_action(str(actions[0].id))

    assert resumed_turn.status == "failed"
    assert resumed_turn.error_code == "tool_resume_failed"
    updated_actions = await AgentActionRepository(db_session).list_for_turn(
        str(turn.id)
    )
    assert updated_actions[0].status == "failed"
    assert updated_actions[0].error["type"] == "ExecutionTargetMismatch"
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    tool_message = next(message for message in messages if message.role == "tool")
    tool_payload = json.loads(tool_message.content_parts[0]["text"])
    assert tool_payload["status"] == "failed"
    assert tool_payload["error"]["type"] == "ExecutionTargetMismatch"
    persisted_turn = await service.turn_repo.get(str(turn.id))
    assert "pending_observation" not in persisted_turn.loop_state["progress"]
    followup = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Continue after the failed stale action.",
    )
    assert followup.status == "queued"


@pytest.mark.asyncio
async def test_interrupt_marks_turn_with_named_termination_reason(db_session):
    await _workspace(db_session)
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
        input_text="Stop before running.",
    )

    interrupted = await service.interrupt_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert interrupted.status == "cancelled"
    assert interrupted.termination_reason == "interrupted"
    assert interrupted.interrupt_requested_at is not None

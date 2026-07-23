from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.services.agent_core.ledger as ledger_module
from app.config import settings
from app.models.llm import LlmModel, LlmProvider
from app.models.agent_core import AgentActionStatus
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
from app.services.agent_core.execution_target import (
    session_metadata_with_execution_target,
)
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.tools import AgentToolContext, build_default_tool_registry
from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.agent_core.tools.toolsets import ToolsetExposure
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelEvent,
    ModelInvocation,
    TextDelta,
    ToolCallDelta,
    ToolCallPart,
    ToolResultPart,
    UsageReport,
)
from app.utils.exceptions import BadRequestError, PermissionDeniedError
from app.workspace import DEFAULT_WORKSPACE_ID


def test_model_gateway_has_no_responses_specific_continuation_assembly() -> None:
    source = (
        Path(__file__).parents[2] / "app/services/model_runtime/gateway.py"
    ).read_text()

    assert "_merge_replay_input" not in source
    assert "_stable_replay_key" not in source
    assert 'wire_protocol == "responses"' not in source
    assert "ResponsesContinuation" not in source


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


class _FakeModelGateway:
    def __init__(self, *responses: tuple[ModelEvent, ...]) -> None:
        self.responses = list(responses)
        self.invocations: list[ModelInvocation] = []

    async def invoke(self, invocation: ModelInvocation) -> AsyncIterator[ModelEvent]:
        self.invocations.append(invocation)
        for event in self.responses.pop(0):
            yield event


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


def test_old_prompt_snapshot_is_returned_verbatim():
    resolved = resolve_system_prompt_prefix(
        {"id": "bioinfoflow-agent-v6", "content": "old prompt"}
    )

    assert resolved == "old prompt"


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
async def test_turn_writes_canonical_user_and_assistant_messages(db_session):
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    service.runtime.model_gateway = _FakeModelGateway(
        (
            TextDelta(text="Use hg38 for this project."),
            UsageReport(input_tokens=3, output_tokens=5, total_tokens=8),
            CompletionMetadata(response_id="chatcmpl-hg38", finish_reason="stop"),
        )
    )
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
async def test_event_sequence_is_session_scoped_across_turns(db_session):
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    service.runtime.model_gateway = _FakeModelGateway(
        (
            TextDelta(text="ok"),
            CompletionMetadata(response_id="chatcmpl-first", finish_reason="stop"),
        ),
        (
            TextDelta(text="ok"),
            CompletionMetadata(response_id="chatcmpl-second", finish_reason="stop"),
        ),
    )
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
    ledger.owned_turn_id = None
    ledger.expected_owner_token = None

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
    ledger.owned_turn_id = None
    ledger.expected_owner_token = None

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
    db_session,
):
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    service.runtime.model_gateway = _FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="worker-ask-user",
                name="ask_user",
                arguments_delta=json.dumps(
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
                ),
            ),
            CompletionMetadata(
                response_id="chatcmpl-worker",
                finish_reason="tool_calls",
            ),
        )
    )
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
    repaired_actions = await AgentActionRepository(db_session).list_for_turn(
        str(turn.id)
    )
    assert len(repaired_actions) == 1
    assert repaired_actions[0].status == AgentActionStatus.FAILED
    assert repaired_actions[0].error["type"] == "BatchPreparationError"


@pytest.mark.asyncio
async def test_unexposed_tool_is_denied_before_argument_validation(db_session):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    session = await service.update_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        updates={"mode": "plan"},
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
async def test_loop_refreshes_permission_context_before_each_model_iteration(
    db_session,
    db_engine,
):
    calls = 0
    session_id = ""

    class RefreshingGateway:
        async def invoke(
            self,
            invocation: ModelInvocation,
        ) -> AsyncIterator[ModelEvent]:
            nonlocal calls
            calls += 1
            tool_names = {tool.name for tool in invocation.tools}
            system_text = invocation.instructions
            if calls == 1:
                assert "bash" in tool_names
                assert "Role profile: bioinformatician" in system_text
                sessions = async_sessionmaker(
                    db_engine,
                    expire_on_commit=False,
                    class_=AsyncSession,
                )
                async with sessions() as update_db:
                    await AgentCoreService(update_db).update_session(
                        session_id=session_id,
                        workspace_id=DEFAULT_WORKSPACE_ID,
                        user_id="dev",
                        updates={
                            "mode": "plan",
                            "role_profile": "worker",
                        },
                    )
                yield ToolCallDelta(
                    index=0,
                    call_id="tool-call-refresh",
                    name="memory.list",
                    arguments_delta="{}",
                )
                yield CompletionMetadata(
                    response_id="chatcmpl-refresh-tool",
                    finish_reason="tool_calls",
                )
            else:
                assert "bash" not in tool_names
                assert "Role profile: worker" in system_text
                assert "Toolset policy: plan" in system_text
                yield TextDelta(text="Refreshed policy observed.")
                yield CompletionMetadata(
                    response_id="chatcmpl-refresh-final",
                    finish_reason="stop",
                )

    await _workspace(db_session)
    await _seed_catalog_model(db_session)
    service = AgentCoreService(db_session)
    service.runtime.model_gateway = RefreshingGateway()
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="bypass",
    )
    session_id = str(session.id)
    turn = await service.create_turn_record(
        session_id=session_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Refresh permissions between iterations.",
    )

    completed = await service.runtime.run_turn(str(turn.id))

    assert completed.status == "completed"
    assert completed.final_text == "Refreshed policy observed."
    assert calls == 2


@pytest.mark.asyncio
async def test_approval_resume_executes_tool_and_continues_turn(
    db_session, monkeypatch
):
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    gateway = _FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="tool-call-1",
                name="bash",
                arguments_delta=json.dumps(
                    {
                        "command": f"{sys.executable} -c 'print(\"approved-tool\")'",
                        "cwd": str(settings.bioinfoflow_home),
                    }
                ),
            ),
            UsageReport(input_tokens=1, output_tokens=1, total_tokens=2),
            CompletionMetadata(
                response_id="chatcmpl-tool-call",
                finish_reason="tool_calls",
            ),
        ),
        (
            TextDelta(text="Final after approved tool."),
            UsageReport(input_tokens=1, output_tokens=1, total_tokens=2),
            CompletionMetadata(response_id="chatcmpl-final", finish_reason="stop"),
        ),
    )
    service.runtime.model_gateway = gateway
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

    resumed_invocation = gateway.invocations[1]
    tool_call = next(
        item
        for item in resumed_invocation.input_items
        if isinstance(item, ToolCallPart)
    )
    tool_result = next(
        item
        for item in resumed_invocation.input_items
        if isinstance(item, ToolResultPart)
    )
    assert tool_call.call_id == "tool-call-1"
    assert tool_call.name == "bash"
    assert tool_result.call_id == "tool-call-1"

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
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    gateway = _FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="tool-call-rejected",
                name="bash",
                arguments_delta=json.dumps(
                    {
                        "command": f"{sys.executable} -c 'print(\"should-not-run\")'",
                        "cwd": str(settings.bioinfoflow_home),
                    }
                ),
            ),
            CompletionMetadata(
                response_id="chatcmpl-rejected-tool",
                finish_reason="tool_calls",
            ),
        ),
        (
            TextDelta(text="I will continue without running that tool."),
            CompletionMetadata(
                response_id="chatcmpl-rejected-final",
                finish_reason="stop",
            ),
        ),
    )
    service.runtime.model_gateway = gateway
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
    tool_result = next(
        item
        for item in gateway.invocations[1].input_items
        if isinstance(item, ToolResultPart)
    )
    assert tool_result.call_id == "tool-call-rejected"
    assert "UserRejected" in tool_result.output


@pytest.mark.asyncio
async def test_resume_stale_local_tool_for_remote_session_records_failed_result(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    service.runtime.model_gateway = _FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="tool-call-stale",
                name="bash",
                arguments_delta=json.dumps({"command": "pwd"}),
            ),
            CompletionMetadata(
                response_id="chatcmpl-stale-tool",
                finish_reason="tool_calls",
            ),
        )
    )
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
    mutable_session = await service.session_repo.get_fresh(str(session.id))
    await service.session_repo.update_all(
        mutable_session,
        session_metadata=session_metadata_with_execution_target(
            mutable_session.session_metadata,
            {
                "type": "remote_ssh",
                "connection_id": "conn-1",
            },
        ),
    )

    resumed_turn = await service.runtime.resume_turn_after_action(str(actions[0].id))

    assert resumed_turn.status == "failed"
    assert resumed_turn.error_code == "tool_resume_failed"
    updated_actions = await AgentActionRepository(db_session).list_for_turn(
        str(turn.id)
    )
    assert updated_actions[0].status == "failed"
    assert updated_actions[0].error["type"] == "PermissionDeniedError"
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    tool_message = next(message for message in messages if message.role == "tool")
    tool_payload = json.loads(tool_message.content_parts[0]["text"])
    assert tool_payload["status"] == "failed"
    assert tool_payload["error"]["type"] == "PermissionDeniedError"


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

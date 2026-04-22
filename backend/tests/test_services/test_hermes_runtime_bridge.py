from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from unittest.mock import AsyncMock, patch

from app.database import Base
from app.models.agent_approval_handle import AgentApprovalHandleStatus
from app.models.agent_response_handle import AgentResponseHandle, AgentResponseStatus
from app.models.conversation import Conversation, ConversationStorageBackend
from app.models.project import Project
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.run import Run, RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.services.hermes_service import runner as runner_module
from app.services.hermes_service import service as service_module
from app.services.hermes_service import session_store as session_store_module
from app.services.hermes_service import tool_bridge as tool_bridge_module
from app.services.hermes_service.service import HermesConversationService
from app.services.hermes_service.tool_bridge import HermesToolRuntimeContext, bind_tool_context


@pytest_asyncio.fixture(autouse=True)
async def _reset_hermes_runtime_bridge_tables(db_session):
    for table in reversed(Base.metadata.sorted_tables):
        await db_session.execute(table.delete())
    await db_session.commit()


def test_get_hermes_session_store_uses_managed_default_path(tmp_path, monkeypatch):
    expected_path = tmp_path / "bioinfoflow-home" / "hermes" / "state.db"
    created_paths: list[Path] = []

    class FakeSessionDB:
        def __init__(self, path: Path):
            created_paths.append(Path(path))

    monkeypatch.setattr(session_store_module, "SessionDB", FakeSessionDB)
    monkeypatch.setattr(
        session_store_module,
        "resolve_hermes_state_db_path",
        lambda db_path=None: expected_path,
    )
    monkeypatch.setattr(session_store_module, "_SESSION_STORE", None, raising=False)
    monkeypatch.setattr(session_store_module, "_SESSION_STORES", {}, raising=False)

    first = session_store_module.get_hermes_session_store()
    second = session_store_module.get_hermes_session_store()

    assert first is second
    assert created_paths == [expected_path]
    assert expected_path.parent.exists()


def test_get_hermes_session_store_sets_managed_home_and_runtime_dirs(tmp_path, monkeypatch):
    expected_home = tmp_path / "bioinfoflow-home" / "hermes"
    expected_path = expected_home / "state.db"

    class FakeSessionDB:
        def __init__(self, path: Path):
            self.path = Path(path)

    monkeypatch.setattr(session_store_module, "SessionDB", FakeSessionDB)
    monkeypatch.setattr(session_store_module, "_SESSION_STORE", None, raising=False)
    monkeypatch.setattr(session_store_module, "_SESSION_STORES", {}, raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)

    store = session_store_module.get_hermes_session_store(expected_path)

    assert getattr(store, "path", None) == expected_path
    assert os.environ["HERMES_HOME"] == str(expected_home)
    assert (expected_home / "sessions").is_dir()
    assert (expected_home / "logs").is_dir()
    assert (expected_home / "cache").is_dir()
    assert (expected_home / "memories").is_dir()


@pytest.mark.asyncio
async def test_service_initializes_session_store_with_configured_path(
    db_session,
    monkeypatch,
    tmp_path,
):
    expected_home = tmp_path / "bioinfoflow-home" / "hermes"
    expected_path = tmp_path / "bioinfoflow-home" / "hermes" / "state.db"
    captured: dict[str, str | None] = {}

    def fake_get_hermes_session_store(db_path=None):
        captured["db_path"] = str(db_path) if db_path is not None else None
        return object()

    monkeypatch.setattr(service_module, "get_hermes_session_store", fake_get_hermes_session_store)
    monkeypatch.setattr(
        service_module.settings,
        "agent_hermes_home",
        str(expected_home),
    )
    monkeypatch.setattr(
        service_module.settings,
        "agent_hermes_state_db",
        str(expected_path),
    )
    monkeypatch.delenv("HERMES_HOME", raising=False)

    service = HermesConversationService(db_session)

    assert service.session_store is not None
    assert captured["db_path"] == str(expected_path)
    assert os.environ["HERMES_HOME"] == str(expected_home)


@pytest.mark.asyncio
async def test_runner_emits_explicit_tool_events_and_preserves_structured_results(monkeypatch):
    captured: dict[str, object] = {}
    published_events: list[dict] = []
    terminal_approvals: list[object] = []

    class FakeSessionStore:
        def get_messages_as_conversation(self, session_id: str):
            return [{"role": "assistant", "content": "previous"}]

    class FakeAIAgent:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def run_conversation(self, prompt: str, conversation_history=None):
            kwargs = captured["kwargs"]
            captured["history"] = conversation_history
            kwargs["tool_start_callback"](
                "tool-1",
                "submit_run",
                '{"workflow_name":"nf-core/rnaseq"}',
            )
            kwargs["tool_progress_callback"](
                "requires_approval",
                "submit_run",
                "Waiting for approval",
                '{"workflow_name":"nf-core/rnaseq"}',
            )
            kwargs["tool_complete_callback"](
                "tool-1",
                "submit_run",
                '{"workflow_name":"nf-core/rnaseq"}',
                {"run_id": "run_demo_001", "status": "queued"},
            )
            return {
                "final_response": "Queued the workflow run.",
                "usage": {"input_tokens": 12, "output_tokens": 8},
            }

    async def on_event(event: dict):
        published_events.append(event)

    monkeypatch.setattr(runner_module, "AIAgent", FakeAIAgent)
    monkeypatch.setattr(
        runner_module,
        "set_terminal_approval_callback",
        lambda callback: terminal_approvals.append(callback),
        raising=False,
    )

    result = await runner_module.HermesRunner().run_response(
        session_id="sess-1",
        prompt="Run rnaseq",
        model="claude-sonnet-4-6",
        cwd="/tmp/workspace",
        session_store=FakeSessionStore(),
        clarify_callback=lambda question, choices=None: "approve",
        approval_callback=lambda request: "once",
        on_event=on_event,
    )

    kwargs = captured["kwargs"]
    assert "enabled_toolsets" in kwargs
    assert "bioinfoflow" in kwargs["enabled_toolsets"]
    assert "tool_progress_callback" in kwargs
    assert "ephemeral_system_prompt" in kwargs
    assert "workflow_catalog" in str(kwargs["ephemeral_system_prompt"])
    assert "preview_run_profile" in str(kwargs["ephemeral_system_prompt"])
    assert "workflow_validate" not in str(kwargs["ephemeral_system_prompt"])
    assert "submit_run" in str(kwargs["ephemeral_system_prompt"])
    assert "explain_run_results" in str(kwargs["ephemeral_system_prompt"])
    assert "Do not ask for a separate text confirmation" in str(kwargs["ephemeral_system_prompt"])
    assert "Do as much work as possible with tools before asking the user for help." in str(
        kwargs["ephemeral_system_prompt"]
    )
    assert "Translate logs, parameters, and artifacts into plain-language explanations" in str(
        kwargs["ephemeral_system_prompt"]
    )
    assert terminal_approvals and callable(terminal_approvals[0])
    assert captured["history"] == [{"role": "assistant", "content": "previous"}]

    tool_progress = next(event for event in published_events if event["type"] == "tool_call_progress")
    assert tool_progress["metadata"]["preview"] == "Waiting for approval"
    assert tool_progress["metadata"]["status"] == "requires_approval"

    tool_end = next(event for event in published_events if event["type"] == "tool_call_end")
    assert json.loads(tool_end["metadata"]["result"]) == {
        "run_id": "run_demo_001",
        "status": "queued",
    }
    assert tool_end["metadata"]["result_json"] == {
        "run_id": "run_demo_001",
        "status": "queued",
    }

    assert result.final_text == "Queued the workflow run."
    assert result.usage == {"input_tokens": 12, "output_tokens": 8}


def test_real_sdk_registration_exposes_bioinfoflow_toolset_definitions(monkeypatch):
    registry_module = pytest.importorskip("tools.registry")
    model_tools = pytest.importorskip("model_tools")

    monkeypatch.setattr(tool_bridge_module, "_toolset_registered", False)

    tool_bridge_module.ensure_bioinfoflow_toolset_registered()

    registry = registry_module.registry
    assert "bioinfoflow" in registry.get_registered_toolset_names()
    assert {
        "project_enable_workflow",
        "workflow_catalog",
        "workflow_schema",
        "preview_run_profile",
        "submit_run",
        "run_status",
        "run_logs",
        "list_artifacts",
        "run_results_overview",
        "explain_run_results",
    }.issubset(set(registry.get_tool_names_for_toolset("bioinfoflow")))

    definitions = model_tools.get_tool_definitions(
        enabled_toolsets=["bioinfoflow"],
        quiet_mode=True,
    )
    definition_names = {
        item["function"]["name"]
        for item in definitions
        if item.get("type") == "function" and isinstance(item.get("function"), dict)
    }
    assert "workflow_catalog" in definition_names
    assert "submit_run" in definition_names


@pytest.mark.asyncio
async def test_project_enable_workflow_tool_binds_workflow_to_active_project(
    db_session,
    tmp_path,
):
    project = Project(
        name="Hermes Workflow Enable Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="dev",
    )
    workflow = Workflow(
        name="RNAseq Enablement",
        description="Workflow for enablement testing",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0-enable",
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    context = HermesToolRuntimeContext(
        session_factory=session_factory,
        project_id=str(project.id),
        user_id="dev",
        workspace_root=str(tmp_path / "workspace"),
    )

    with bind_tool_context(context):
        payload = json.loads(
            tool_bridge_module.project_enable_workflow(workflow_id=str(workflow.id))
        )

    binding = await db_session.scalar(
        ProjectWorkflowBinding.__table__.select()
        .where(ProjectWorkflowBinding.project_id == str(project.id))
        .where(ProjectWorkflowBinding.workflow_id == str(workflow.id))
        .limit(1)
    )

    assert payload["enabled"] is True
    assert payload["workflow"]["id"] == str(workflow.id)
    assert binding is not None


@pytest.mark.asyncio
async def test_preview_run_profile_tool_returns_form_spec_payload(
    db_session,
    tmp_path,
):
    workspace_root = tmp_path / "workspace-root"
    workspace_root.mkdir()
    workspace = workspace_root / "project-ws"
    workspace.mkdir()

    reads_dir = workspace / "reads"
    reads_dir.mkdir()
    (reads_dir / "S1_R1.fastq.gz").write_text("@r1\nACGT\n+\n!!!!\n")
    (reads_dir / "S1_R2.fastq.gz").write_text("@r2\nTGCA\n+\n!!!!\n")

    ref_dir = workspace / "ref"
    ref_dir.mkdir()
    (ref_dir / "NC_045512.2.fasta").write_text(">ref\nACGT\n")
    (workspace / "samplesheet.csv").write_text(
        "sample,fastq_1,fastq_2\nS1,reads/S1_R1.fastq.gz,reads/S1_R2.fastq.gz\n"
    )

    project = Project(
        name="Hermes Preview Project",
        storage_mode="external",
        external_root_path=str(workspace_root),
        user_id="dev",
    )
    workflow = Workflow(
        name="variant-fanout-mini",
        description="Workflow for run-profile preview",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0-preview",
        form_spec={
            "fields": [
                {
                    "id": "samplesheet",
                    "type": "file",
                    "label": "Samplesheet",
                    "required": True,
                },
                {
                    "id": "reference",
                    "type": "file",
                    "label": "Reference",
                    "required": True,
                },
            ]
        },
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    db_session.add(
        ProjectWorkflowBinding(
            project_id=str(project.id),
            workflow_id=str(workflow.id),
        )
    )
    await db_session.commit()

    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    context = HermesToolRuntimeContext(
        session_factory=session_factory,
        project_id=str(project.id),
        user_id="dev",
        workspace_root=str(workspace_root),
    )

    with bind_tool_context(context):
        payload = json.loads(
            tool_bridge_module.preview_run_profile(
                workflow_id=str(workflow.id),
                workspace="project-ws",
            )
        )

    assert payload["summary"] == "Loaded form spec for variant-fanout-mini"
    assert payload["form_spec"]["fields"] == [
        {
            "id": "samplesheet",
            "type": "file",
            "label": "Samplesheet",
            "required": True,
        },
        {
            "id": "reference",
            "type": "file",
            "label": "Reference",
            "required": True,
        },
    ]
    assert payload["resolved_params"] == {}
    assert payload["detected_inputs"] == {}
    assert payload["sample_rows"] == []


@pytest.mark.asyncio
async def test_submit_run_tool_uses_values_envelope_and_run_compiler(
    db_session,
    tmp_path,
):
    workspace_root = tmp_path / "submit-workspace"
    workspace_root.mkdir()

    project = Project(
        name="Hermes Submit Project",
        storage_mode="external",
        external_root_path=str(workspace_root),
        user_id="dev",
    )
    workflow = Workflow(
        name="submit-workflow",
        description="Workflow for submit tool testing",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0-submit",
        form_spec={
            "fields": [
                {
                    "id": "reads",
                    "type": "file",
                    "label": "Reads",
                    "required": True,
                }
            ]
        },
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    db_session.add(
        ProjectWorkflowBinding(
            project_id=str(project.id),
            workflow_id=str(workflow.id),
        )
    )
    await db_session.commit()

    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    context = HermesToolRuntimeContext(
        session_factory=session_factory,
        project_id=str(project.id),
        user_id="dev",
        workspace_root=str(workspace_root),
    )

    with bind_tool_context(context):
        with patch(
            "app.services.hermes_service.tool_bridge.RunCompiler"
        ) as compiler_class:
            compiler = compiler_class.return_value
            compiler.create_run = AsyncMock(
                return_value=SimpleNamespace(run_id="run_submit_001", status="queued")
            )

            payload = json.loads(
                tool_bridge_module.submit_run(
                    workflow_id=str(workflow.id),
                    values={"reads": "reads/sample.fastq.gz"},
                    options={"profile": "docker"},
                )
            )

    compiler.create_run.assert_awaited_once()
    create_payload = compiler.create_run.await_args.args[0]
    assert str(create_payload.project_id) == str(project.id)
    assert str(create_payload.workflow_id) == str(workflow.id)
    assert create_payload.values == {"reads": "reads/sample.fastq.gz"}
    assert create_payload.options is not None
    assert create_payload.options.profile == "docker"
    assert payload["approved"] is True
    assert payload["run_id"] == "run_submit_001"


@pytest.mark.asyncio
async def test_submit_run_tool_reports_invalid_values(
    db_session,
    tmp_path,
):
    workspace_root = tmp_path / "validation-workspace"
    workspace_root.mkdir()

    project = Project(
        name="Hermes Validation Project",
        storage_mode="external",
        external_root_path=str(workspace_root),
        user_id="dev",
    )
    workflow = Workflow(
        name="validation-workflow",
        description="Workflow with schema for validation testing",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0-validation",
        form_spec={
            "fields": [
                {
                    "id": "input",
                    "label": "Input",
                    "section": "data",
                    "kind": "file",
                    "required": True,
                    "allow_roots": ["project_data"],
                },
                {
                    "id": "profile",
                    "label": "Profile",
                    "section": "params",
                    "kind": "select",
                    "options": [
                        {"label": "Docker", "value": "docker"},
                        {"label": "Conda", "value": "conda"},
                    ],
                },
            ]
        },
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)
    db_session.add(
        ProjectWorkflowBinding(
            project_id=str(project.id),
            workflow_id=str(workflow.id),
        )
    )
    await db_session.commit()

    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    context = HermesToolRuntimeContext(
        session_factory=session_factory,
        project_id=str(project.id),
        user_id="dev",
        workspace_root=str(workspace_root),
    )

    with bind_tool_context(context):
        payload = json.loads(
            tool_bridge_module.submit_run(
                workflow_id=str(workflow.id),
                values={"input": 123, "profile": "invalid-profile"},
            )
        )

    assert payload["approved"] is True
    assert payload["submitted"] is False
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "INVALID_FORM_VALUES"
    assert payload["error"]["message"] == "Input has an invalid value"


@pytest.mark.asyncio
async def test_run_results_overview_tool_returns_status_logs_and_artifacts(
    db_session,
    tmp_path,
):
    workspace_root = tmp_path / "results-workspace"
    workspace_root.mkdir()
    results_dir = workspace_root / "results"
    results_dir.mkdir()
    (results_dir / "summary.tsv").write_text("gene\tlogFC\nTP53\t2.1\n")

    log_dir = workspace_root / ".bioinfoflow" / "run_demo_001"
    log_dir.mkdir(parents=True)
    (log_dir / "run.log").write_text("step 1 completed\nstep 2 completed\nworkflow finished\n")

    project = Project(
        name="Hermes Results Project",
        storage_mode="external",
        external_root_path=str(workspace_root),
        user_id="dev",
    )
    workflow = Workflow(
        name="results-workflow",
        description="Workflow for results overview testing",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0-results",
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    run = Run(
        run_id="run_demo_001",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED,
        config={
            "params": {"outdir": "results"},
            "log_path": ".bioinfoflow/run_demo_001/run.log",
            "resolved_runspec": {
                "workspace": str(workspace_root),
                "params": {"outdir": "results"},
            },
        },
        samples_count=2,
        tasks_total=3,
        tasks_completed=3,
        current_task=None,
    )
    db_session.add(run)
    await db_session.commit()

    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    context = HermesToolRuntimeContext(
        session_factory=session_factory,
        project_id=str(project.id),
        user_id="dev",
        workspace_root=str(workspace_root),
    )

    with bind_tool_context(context):
        payload = json.loads(
            tool_bridge_module.run_results_overview(
                run_id="run_demo_001",
                tail=2,
                artifact_limit=10,
            )
        )

    assert payload["run"]["status"] == "completed"
    assert payload["run"]["run_id"] == "run_demo_001"
    assert payload["output_path"] == str(results_dir)
    assert payload["artifacts"]["count"] >= 1
    assert payload["artifacts"]["files"][0]["name"] == "summary.tsv"
    assert payload["logs"][-1]["message"] == "workflow finished"


@pytest.mark.asyncio
async def test_explain_run_results_tool_reads_artifacts_and_prepares_plain_language_summary(
    db_session,
    tmp_path,
):
    workspace_root = tmp_path / "explain-results-workspace"
    workspace_root.mkdir()
    results_dir = workspace_root / "results"
    results_dir.mkdir()
    (results_dir / "summary.tsv").write_text(
        "gene\tlogFC\nTP53\t2.1\nBRCA1\t-1.4\n",
        encoding="utf-8",
    )
    (results_dir / "report.md").write_text(
        "# RNAseq QC\n\nAll samples passed basic QC.\n",
        encoding="utf-8",
    )

    log_dir = workspace_root / ".bioinfoflow" / "run_explain_001"
    log_dir.mkdir(parents=True)
    (log_dir / "run.log").write_text(
        "step 1 completed\nstep 2 completed\nworkflow finished\n",
        encoding="utf-8",
    )

    project = Project(
        name="Hermes Explain Results Project",
        storage_mode="external",
        external_root_path=str(workspace_root),
        user_id="dev",
    )
    workflow = Workflow(
        name="results-explain-workflow",
        description="Workflow for results explanation testing",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0-explain",
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    run = Run(
        run_id="run_explain_001",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED,
        config={
            "params": {"outdir": "results"},
            "log_path": ".bioinfoflow/run_explain_001/run.log",
            "resolved_runspec": {
                "workspace": str(workspace_root),
                "params": {"outdir": "results"},
            },
        },
        samples_count=2,
        tasks_total=3,
        tasks_completed=3,
        current_task=None,
    )
    db_session.add(run)
    await db_session.commit()

    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    context = HermesToolRuntimeContext(
        session_factory=session_factory,
        project_id=str(project.id),
        user_id="dev",
        workspace_root=str(workspace_root),
    )

    with bind_tool_context(context):
        payload = json.loads(
            tool_bridge_module.explain_run_results(
                run_id="run_explain_001",
                artifact_limit=5,
                preview_chars=240,
            )
        )

    assert payload["run"]["run_id"] == "run_explain_001"
    assert payload["summary"].startswith("Run run_explain_001 completed successfully.")
    assert "summary.tsv" in payload["summary"]
    assert payload["explanation"]["status_summary"].startswith("Run run_explain_001 completed")
    assert "summary.tsv" in payload["explanation"]["artifact_summary"]
    assert payload["artifact_previews"][0]["name"] == "summary.tsv"
    assert "TP53" in payload["artifact_previews"][0]["excerpt"]
    assert payload["artifact_previews"][1]["name"] == "report.md"
    assert "basic QC" in payload["artifact_previews"][1]["excerpt"]


@pytest.mark.asyncio
async def test_real_sdk_runner_executes_registered_bioinfoflow_tool_roundtrip(
    db_session,
    tmp_path,
    monkeypatch,
):
    pytest.importorskip("run_agent")

    workflow = Workflow(
        name="RNAseq QC",
        description="RNA-seq quality-control workflow",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
        schema_json={"inputs": {"fastq": {"type": "string"}}},
        form_spec={"fields": [{"id": "fastq", "type": "file", "label": "FASTQ"}]},
    )
    db_session.add(workflow)
    await db_session.commit()

    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
    )
    session_store = session_store_module.get_hermes_session_store(tmp_path / "hermes-state.db")
    published_events: list[dict] = []
    call_count = 0

    def _tool_call_response() -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="",
                        tool_calls=[
                            SimpleNamespace(
                                id="tool-call-1",
                                type="function",
                                function=SimpleNamespace(
                                    name="workflow_catalog",
                                    arguments=json.dumps({"search": "RNA", "limit": 5}),
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4, total_tokens=14),
            model="test-model",
        )

    def _final_response() -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="I found the RNAseq QC workflow in the catalog.",
                        tool_calls=None,
                    ),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=8, total_tokens=19),
            model="test-model",
        )

    def fake_interruptible_streaming_api_call(self, api_kwargs, on_first_delta=None):
        nonlocal call_count
        call_count += 1
        if on_first_delta is not None:
            on_first_delta()
        if call_count == 1:
            if self.reasoning_callback is not None:
                self.reasoning_callback("Checking the workflow catalog")
            if self.stream_delta_callback is not None:
                self.stream_delta_callback("Looking up matching workflows...")
            return _tool_call_response()

        if self.stream_delta_callback is not None:
            self.stream_delta_callback("I found the RNAseq QC workflow in the catalog.")
        return _final_response()

    monkeypatch.setattr(
        runner_module.AIAgent,
        "_interruptible_streaming_api_call",
        fake_interruptible_streaming_api_call,
        raising=True,
    )
    monkeypatch.setattr(runner_module.AIAgent, "_interruptible_api_call", fake_interruptible_streaming_api_call)

    async def on_event(event: dict):
        published_events.append(event)

    result = await runner_module.HermesRunner().run_response(
        session_id="sess-real-sdk",
        prompt="Find RNA workflows",
        model="test-model",
        cwd=str(tmp_path),
        session_store=session_store,
        tool_context=HermesToolRuntimeContext(
            session_factory=session_factory,
            project_id="project-1",
            user_id="dev",
            workspace_root=str(tmp_path),
        ),
        on_event=on_event,
    )

    tool_start = next(event for event in published_events if event["type"] == "tool_call_start")
    assert tool_start["metadata"]["name"] == "workflow_catalog"
    assert tool_start["metadata"]["args"] == {"search": "RNA", "limit": 5}

    tool_end = next(event for event in published_events if event["type"] == "tool_call_end")
    assert tool_end["metadata"]["name"] == "workflow_catalog"
    assert tool_end["metadata"]["result_json"]["results"][0]["name"] == "RNAseq QC"
    assert tool_end["metadata"]["summary"] == "Found 1 workflows"

    assert any(
        event["type"] == "thinking_delta"
        and "Checking the workflow catalog" in event.get("content", "")
        for event in published_events
    )
    assert any(
        event["type"] == "text_delta"
        and "Looking up matching workflows" in event.get("content", "")
        for event in published_events
    )
    assert result.final_text == "I found the RNAseq QC workflow in the catalog."
    assert call_count == 2

    recovered_history = session_store.get_messages_as_conversation("sess-real-sdk")
    assert any(
        message.get("role") == "assistant"
        and "RNAseq QC workflow" in str(message.get("content", ""))
        for message in recovered_history
    )


@pytest.mark.asyncio
async def test_runner_limits_concurrent_hermes_runs(monkeypatch):
    active_calls = 0
    max_active_calls = 0
    first_started = threading.Event()
    second_started = threading.Event()
    release_first = threading.Event()
    state_lock = threading.Lock()

    class BlockingAIAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run_conversation(self, prompt: str, conversation_history=None):
            nonlocal active_calls, max_active_calls
            with state_lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
            try:
                if prompt == "first":
                    first_started.set()
                    release_first.wait(timeout=1.0)
                else:
                    second_started.set()
                return {"final_response": prompt}
            finally:
                with state_lock:
                    active_calls -= 1

    async def on_event(event: dict) -> None:
        return None

    monkeypatch.setattr(runner_module, "AIAgent", BlockingAIAgent)

    runner = runner_module.HermesRunner(max_concurrency=1)
    first_task = asyncio.create_task(
        runner.run_response(
            session_id="sess-limit-1",
            prompt="first",
            model="test-model",
            cwd=None,
            on_event=on_event,
        )
    )

    await asyncio.wait_for(asyncio.to_thread(first_started.wait, 1.0), timeout=2.0)

    second_task = asyncio.create_task(
        runner.run_response(
            session_id="sess-limit-2",
            prompt="second",
            model="test-model",
            cwd=None,
            on_event=on_event,
        )
    )

    await asyncio.sleep(0.1)
    assert not second_started.is_set()

    release_first.set()
    first_result, second_result = await asyncio.gather(first_task, second_task)

    assert first_result.final_text == "first"
    assert second_result.final_text == "second"
    assert second_started.is_set()
    assert max_active_calls == 1


@pytest.mark.asyncio
async def test_internal_canary_real_sdk_service_flow_supports_risky_tool_approval_and_history_recovery(
    db_session,
    tmp_path,
    monkeypatch,
):
    pytest.importorskip("run_agent")

    project = Project(
        name="Hermes Canary Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="dev",
    )
    workflow = Workflow(
        name="RNAseq QC Canary",
        description="RNA-seq quality-control workflow",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.1-canary",
        schema_json={"inputs": {"fastq": {"type": "string"}}},
        form_spec={"fields": [{"id": "fastq", "type": "file", "label": "FASTQ"}]},
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    expected_home = tmp_path / "bioinfoflow-home" / "hermes"
    monkeypatch.setattr(
        service_module.settings,
        "agent_hermes_home",
        str(expected_home),
    )
    monkeypatch.setattr(
        service_module.settings,
        "agent_hermes_state_db",
        str(expected_home / "state.db"),
    )
    monkeypatch.setattr(session_store_module, "_SESSION_STORE", None, raising=False)
    monkeypatch.setattr(session_store_module, "_SESSION_STORES", {}, raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=type(db_session),
    )
    monkeypatch.setattr(service_module.app_database, "async_session_maker", session_factory)

    published_events: list[tuple[str, dict]] = []
    call_count = 0

    def _tool_call_response() -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="",
                        tool_calls=[
                            SimpleNamespace(
                                id="tool-call-canary-1",
                                call_id="tool-call-canary-1",
                                response_item_id="fc_canary_1",
                                type="function",
                                function=SimpleNamespace(
                                    name="submit_run",
                                    arguments=json.dumps(
                                        {"workflow_id": str(workflow.id), "values": {}}
                                    ),
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4, total_tokens=14),
            model="canary-model",
        )

    def _final_response() -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Queued the workflow run after approval.",
                        tool_calls=None,
                    ),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=8, total_tokens=19),
            model="canary-model",
        )

    def fake_interruptible_streaming_api_call(self, api_kwargs, on_first_delta=None):
        nonlocal call_count
        call_count += 1
        if on_first_delta is not None:
            on_first_delta()
        if call_count == 1:
            if self.reasoning_callback is not None:
                self.reasoning_callback("Planning the workflow submission")
            if self.stream_delta_callback is not None:
                self.stream_delta_callback("Preparing the run request...")
            return _tool_call_response()
        if self.stream_delta_callback is not None:
            self.stream_delta_callback("Queued the workflow run after approval.")
        return _final_response()

    async def fake_publish_event(**kwargs):
        published_events.append((kwargs["event"], kwargs["data"]))

    async def fake_create_run(self, payload, **kwargs):
        assert payload.values == {}
        return SimpleNamespace(run_id="run_canary_001", status="queued")

    monkeypatch.setattr(service_module, "publish_event", fake_publish_event)
    monkeypatch.setattr(
        runner_module.AIAgent,
        "_interruptible_streaming_api_call",
        fake_interruptible_streaming_api_call,
        raising=True,
    )
    monkeypatch.setattr(runner_module.AIAgent, "_interruptible_api_call", fake_interruptible_streaming_api_call)
    monkeypatch.setattr(tool_bridge_module.RunCompiler, "create_run", fake_create_run)

    service = HermesConversationService(db_session)
    conversation = await service.create_conversation(
        project_id=str(project.id),
        user_id="dev",
        workspace_id=project.workspace_id,
        title="Hermes Canary",
    )
    send_result = await service.send_message(
        project_id=str(project.id),
        content="Submit the RNAseq QC workflow.",
        user_id="dev",
        workspace_id=project.workspace_id,
        conversation_id=str(conversation.id),
        model_override="canary-model",
    )
    response_id = send_result["response_id"]
    assert response_id is not None

    approvals = []
    for _ in range(40):
        approvals = await service.list_pending_approvals(
            conversation_id=str(conversation.id),
            user_id="dev",
        )
        if approvals:
            break
        await asyncio.sleep(0.05)

    assert approvals
    approval = approvals[0]
    assert approval.payload["tool"] == "submit_run"
    assert approval.payload["approval_type"] == "tool_risk"

    registry_entry = await service_module.hermes_response_registry.get(str(response_id))
    assert registry_entry is not None
    assert registry_entry.task is not None

    await service.resolve_approval(str(approval.id), action="approve", user_id="dev")
    await asyncio.wait_for(registry_entry.task, timeout=5)

    history = await service.get_conversation_history(
        conversation_id=str(conversation.id),
        user_id="dev",
        workspace_id=project.workspace_id,
    )
    stored_messages = service.session_store.get_messages(conversation.hermes_session_id)

    event_names = [name for name, _ in published_events]
    assert "agent.thinking_delta" in event_names
    assert "agent.tool_call_start" in event_names
    assert "agent.approval.requested" in event_names
    assert "agent.approval.resolved" in event_names
    assert "agent.tool_call_end" in event_names
    assert "agent.done" in event_names
    assert call_count == 2
    assert Path(service_module.settings.agent_hermes_state_db).exists()
    assert os.environ["HERMES_HOME"] == str(expected_home)
    assert (expected_home / "sessions").is_dir()
    assert (expected_home / "logs").is_dir()
    assert stored_messages
    assert any(message.role.value == "agent" for message in history.messages)
    assert any(
        part.get("type") == "text"
        and "Queued the workflow run after approval." in part.get("text", "")
        for message in history.messages
        for part in ((message.metadata or {}).get("parts") or [])
    )


@pytest.mark.asyncio
async def test_reconcile_stale_hermes_responses_marks_orphans_as_backend_restart(
    db_session,
    tmp_path,
):
    project = Project(
        name="Hermes Runtime Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    conversation = Conversation(
        project_id=str(project.id),
        user_id="dev",
        title="Hermes Runtime",
        storage_backend=ConversationStorageBackend.HERMES,
        hermes_session_id="sess-runtime",
        workspace_binding_id=project.workspace_id,
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    stale_response = AgentResponseHandle(
        conversation_id=str(conversation.id),
        status=AgentResponseStatus.RUNNING,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.add(stale_response)
    await db_session.commit()
    stale_response.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    await db_session.commit()

    updated = await service_module.reconcile_stale_hermes_responses(
        db_session,
        stale_before=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    await db_session.refresh(stale_response)

    assert updated == 1
    assert stale_response.status == AgentResponseStatus.ERROR
    assert stale_response.error_message == "backend_restart"
    assert stale_response.completed_at is not None


@pytest.mark.asyncio
async def test_request_tool_approval_reuses_unified_approval_flow(
    db_session,
    tmp_path,
    monkeypatch,
):
    project = Project(
        name="Hermes Approval Bridge Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    conversation = Conversation(
        project_id=str(project.id),
        user_id="dev",
        title="Hermes Approval Bridge",
        storage_backend=ConversationStorageBackend.HERMES,
        hermes_session_id="sess-approval",
        workspace_binding_id=project.workspace_id,
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    response_handle = AgentResponseHandle(
        conversation_id=str(conversation.id),
        status=AgentResponseStatus.RUNNING,
    )
    db_session.add(response_handle)
    await db_session.commit()
    await db_session.refresh(response_handle)

    published: list[dict] = []

    async def fake_publish_event(**kwargs):
        published.append(kwargs)

    monkeypatch.setattr(service_module, "publish_event", fake_publish_event)

    service = HermesConversationService(db_session)
    approval_task = asyncio.create_task(
        service.request_tool_approval(
            response_id=str(response_handle.id),
            conversation_id=str(conversation.id),
            project_id=str(project.id),
            tool_name="submit_run",
            tool_input={"workflow_name": "nf-core/rnaseq"},
            risk="act_high",
            description="Submit a new workflow run",
        )
    )

    await asyncio.sleep(0.05)
    approvals = await service.list_pending_approvals(
        conversation_id=str(conversation.id),
        user_id="dev",
    )
    assert len(approvals) == 1
    assert approvals[0].payload["tool"] == "submit_run"
    assert approvals[0].payload["approval_type"] == "tool_risk"
    assert approvals[0].payload["risk"] == "act_high"

    await service.resolve_approval(str(approvals[0].id), action="approve", user_id="dev")
    approval_result = await asyncio.wait_for(approval_task, timeout=1)

    assert approval_result == "once"
    assert published
    assert published[0]["event"] == "agent.approval.requested"
    assert published[0]["data"]["tool"] == "submit_run"
    assert published[0]["data"]["approval_type"] == "tool_risk"
    assert any(
        event["event"] == "agent.tool_call_progress"
        and event["data"]["metadata"]["name"] == "submit_run"
        and event["data"]["metadata"]["status"] == "requires_approval"
        and "Waiting for approval" in event["data"]["metadata"]["preview"]
        for event in published
    )
    assert any(
        event["event"] == "agent.approval.resolved"
        and event["data"]["status"] == AgentApprovalHandleStatus.APPROVED
        for event in published
    )
    assert any(
        event["event"] == "agent.tool_call_progress"
        and event["data"]["metadata"]["name"] == "submit_run"
        and event["data"]["metadata"]["status"] == "approved"
        and "resuming" in event["data"]["metadata"]["preview"].lower()
        for event in published
    )

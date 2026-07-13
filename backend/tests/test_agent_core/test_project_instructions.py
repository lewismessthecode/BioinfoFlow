from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.agent_core.context import AgentContextAssembler
from app.services.agent_core.context.instructions import (
    _remote_read_first_existing_command,
    _target_metadata,
)
import app.services.agent_core.context as context_module
from app.workspace import DEFAULT_WORKSPACE_ID


async def _workspace(db_session) -> Workspace:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    return workspace


def _instruction_classes():
    assert hasattr(context_module, "ProjectInstructionResolver")
    assert hasattr(context_module, "ProjectInstructionFile")
    return (
        context_module.ProjectInstructionResolver,
        context_module.ProjectInstructionFile,
    )


@pytest.mark.asyncio
async def test_project_instruction_resolver_walks_local_root_to_current_with_priority(
    tmp_path,
    monkeypatch,
):
    resolver_cls, _instruction_file_cls = _instruction_classes()
    repo_root = tmp_path / "repo"
    current = repo_root / "pipelines" / "rnaseq"
    current.mkdir(parents=True)
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    (repo_root / "AGENTS.md").write_text("root agents", encoding="utf-8")
    (repo_root / "CLAUDE.md").write_text("root claude hidden", encoding="utf-8")
    (repo_root / "pipelines" / "AGENTS.override.md").write_text(
        "pipeline override",
        encoding="utf-8",
    )
    (repo_root / "pipelines" / "AGENTS.md").write_text(
        "pipeline agents hidden",
        encoding="utf-8",
    )
    (current / "GEMINI.md").write_text("leaf gemini", encoding="utf-8")
    session = SimpleNamespace(
        session_metadata={
            "execution_target": {
                "kind": "local",
                "cwd": str(current),
            }
        }
    )

    context = await resolver_cls(max_bytes=32768).resolve(session)

    assert context is not None
    assert "## Project instructions" in context
    assert context.index(str(repo_root / "AGENTS.md")) < context.index(
        str(repo_root / "pipelines" / "AGENTS.override.md")
    )
    assert context.index(str(repo_root / "pipelines" / "AGENTS.override.md")) < context.index(
        str(current / "GEMINI.md")
    )
    assert "root agents" in context
    assert "pipeline override" in context
    assert "leaf gemini" in context
    assert "root claude hidden" not in context
    assert "pipeline agents hidden" not in context


@pytest.mark.asyncio
async def test_project_instruction_context_marks_truncation(tmp_path, monkeypatch):
    resolver_cls, _instruction_file_cls = _instruction_classes()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    (repo_root / "AGENTS.md").write_text("0123456789abcdef", encoding="utf-8")

    context = await resolver_cls(max_bytes=10).resolve(
        SimpleNamespace(session_metadata={"execution_target": {"kind": "local"}})
    )

    assert context is not None
    assert "0123456789" in context
    assert "abcdef" not in context
    assert "[Truncated to 10 bytes.]" in context


@pytest.mark.asyncio
async def test_project_instruction_resolver_skips_local_symlink_escape(
    tmp_path,
    monkeypatch,
):
    resolver_cls, _instruction_file_cls = _instruction_classes()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "outside-instructions.md"
    outside.write_text("outside secret", encoding="utf-8")
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    (repo_root / "AGENTS.md").symlink_to(outside)

    context = await resolver_cls(max_bytes=32768).resolve(
        SimpleNamespace(session_metadata={"execution_target": {"kind": "local"}})
    )

    assert context is None


@pytest.mark.asyncio
async def test_current_local_session_target_overrides_stale_remote_turn_target(
    tmp_path,
    monkeypatch,
):
    resolver_cls, _instruction_file_cls = _instruction_classes()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    (repo_root / "AGENTS.md").write_text(
        "current local instructions",
        encoding="utf-8",
    )
    session = SimpleNamespace(
        toolset_policy={"name": "execution"},
        context_policy={"memory": "accepted_project_scope"},
        session_metadata={"execution_target": {"type": "local"}},
    )
    turn = SimpleNamespace(
        model_profile_snapshot={
            "metadata": {
                "trace_label": "retain this non-target field",
                "remote_project_root": "/srv/stale",
                "project_instruction_snapshot": "stale remote instructions",
                "execution_target": {
                    "type": "remote_ssh",
                    "connection_id": "stale-conn",
                    "cwd": "/srv/stale",
                },
            }
        }
    )

    target = _target_metadata(session, turn)
    context = await resolver_cls(max_bytes=32768).resolve(session, turn=turn)

    assert target["trace_label"] == "retain this non-target field"
    assert target["type"] == "local"
    assert context is not None
    assert "current local instructions" in context
    assert "stale remote instructions" not in context


@pytest.mark.asyncio
async def test_context_assembler_injects_project_instructions_before_environment(
    db_session,
    tmp_path,
    monkeypatch,
):
    await _workspace(db_session)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    (repo_root / "AGENTS.md").write_text("assembler root instruction", encoding="utf-8")
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        metadata={"execution_target": {"kind": "local", "cwd": str(repo_root)}},
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Use the repo rules.",
    )

    messages = await AgentContextAssembler(db_session).provider_messages(
        agent_session=session,
        turn=turn,
    )
    system_content = messages[0]["content"]

    assert "## Project instructions" in system_content
    assert "assembler root instruction" in system_content
    assert system_content.index("## Project instructions") < system_content.index(
        "## Environment"
    )


@pytest.mark.asyncio
async def test_remote_project_instruction_resolver_uses_remote_reader_seam():
    resolver_cls, instruction_file_cls = _instruction_classes()

    class FakeRemoteReader:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def read_first_existing(
            self,
            *,
            agent_session,
            connection_id: str,
            directory: str,
            filenames,
            max_bytes: int,
            remote_root: str,
        ):
            del agent_session
            self.calls.append(
                {
                    "connection_id": connection_id,
                    "directory": directory,
                    "filenames": tuple(filenames),
                    "max_bytes": max_bytes,
                    "remote_root": remote_root,
                }
            )
            if directory == "/srv/project":
                return instruction_file_cls(
                    source="ssh://conn-1/srv/project/AGENTS.md",
                    content="remote root",
                    truncated=False,
                )
            if directory == "/srv/project/analysis":
                return instruction_file_cls(
                    source="ssh://conn-1/srv/project/analysis/GEMINI.md",
                    content="remote leaf",
                    truncated=False,
                )
            return None

    reader = FakeRemoteReader()
    session = SimpleNamespace(
        id="session-1",
        workspace_id="workspace-1",
        user_id="user-1",
        session_metadata={
            "remote_connection_id": "conn-1",
            "remote_project_root": "/srv/project",
            "execution_target": {
                "kind": "remote_ssh",
                "cwd": "/srv/project/analysis",
            },
        },
    )

    context = await resolver_cls(max_bytes=32768, remote_reader=reader).resolve(session)

    assert context is not None
    assert context.index("remote root") < context.index("remote leaf")
    assert reader.calls == [
        {
            "connection_id": "conn-1",
            "directory": "/srv/project",
            "filenames": (
                "AGENTS.override.md",
                "AGENTS.md",
                "CLAUDE.md",
                "GEMINI.md",
            ),
            "max_bytes": 32768,
            "remote_root": "/srv/project",
        },
        {
            "connection_id": "conn-1",
            "directory": "/srv/project/analysis",
            "filenames": (
                "AGENTS.override.md",
                "AGENTS.md",
                "CLAUDE.md",
                "GEMINI.md",
            ),
            "max_bytes": 32757,
            "remote_root": "/srv/project",
        },
    ]


def test_remote_instruction_read_command_skips_symlink_escapes():
    command = _remote_read_first_existing_command(
        directory="/srv/project",
        filenames=("AGENTS.md",),
        max_bytes=1024,
        remote_root="/srv/project",
    )

    assert 'file_real=$(realpath -- "$path") || continue' in command
    assert 'case "$file_real" in "$root_real"|"$root_real"/*) ;; *) continue;; esac' in command
    assert 'head -c 1025 -- "$path"' in command


@pytest.mark.asyncio
async def test_remote_project_instruction_resolver_accepts_canonical_connection_id():
    resolver_cls, instruction_file_cls = _instruction_classes()

    class FakeRemoteReader:
        async def read_first_existing(
            self,
            *,
            agent_session,
            connection_id: str,
            directory: str,
            filenames,
            max_bytes: int,
            remote_root: str,
        ):
            del agent_session, filenames, max_bytes, remote_root
            if connection_id == "canonical-conn" and directory == "/srv/project":
                return instruction_file_cls(
                    source="ssh://canonical-conn/srv/project/AGENTS.md",
                    content="canonical target",
                    truncated=False,
                )
            return None

    session = SimpleNamespace(
        id="session-1",
        workspace_id="workspace-1",
        user_id="user-1",
        session_metadata={
            "remote_connection_id": "canonical-conn",
            "remote_project_id": "project-1",
            "remote_project_root": "/srv/project",
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": "canonical-conn",
                "cwd": "/srv/project",
            },
        },
    )

    context = await resolver_cls(
        max_bytes=32768,
        remote_reader=FakeRemoteReader(),
    ).resolve(session)

    assert context is not None
    assert "canonical target" in context
    assert "Project instructions unavailable" not in context


@pytest.mark.asyncio
async def test_remote_project_instructions_drop_root_when_current_target_changes():
    resolver_cls, instruction_file_cls = _instruction_classes()

    class CapturingRemoteReader:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def read_first_existing(
            self,
            *,
            agent_session,
            connection_id: str,
            directory: str,
            filenames,
            max_bytes: int,
            remote_root: str,
        ):
            del agent_session, filenames, max_bytes
            self.calls.append(
                {
                    "connection_id": connection_id,
                    "directory": directory,
                    "remote_root": remote_root,
                }
            )
            return instruction_file_cls(
                source=f"ssh://{connection_id}{directory}/AGENTS.md",
                content="leaked project A instructions",
                truncated=False,
            )

    reader = CapturingRemoteReader()
    session = SimpleNamespace(
        id="session-1",
        workspace_id="workspace-1",
        user_id="user-1",
        session_metadata={
            "remote_connection_id": "conn-a",
            "remote_project_id": "project-a",
            "remote_project_root": "/srv/project-a",
            "remote_root_path": "/srv/project-a",
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": "conn-b",
            },
        },
    )

    target = _target_metadata(session)
    context = await resolver_cls(max_bytes=32768, remote_reader=reader).resolve(session)

    assert target["connection_id"] == "conn-b"
    assert "remote_project_id" not in target
    assert "remote_project_root" not in target
    assert "remote_root_path" not in target
    assert reader.calls == []
    assert context is not None
    assert "/srv/project-a" not in context
    assert "leaked project A instructions" not in context


@pytest.mark.asyncio
async def test_remote_project_instruction_partial_failure_keeps_prior_files():
    resolver_cls, instruction_file_cls = _instruction_classes()

    class PartiallyFailingRemoteReader:
        async def read_first_existing(
            self,
            *,
            agent_session,
            connection_id: str,
            directory: str,
            filenames,
            max_bytes: int,
            remote_root: str,
        ):
            del agent_session, connection_id, filenames, max_bytes, remote_root
            if directory == "/srv/project":
                return instruction_file_cls(
                    source="ssh://conn-1/srv/project/AGENTS.md",
                    content="remote root survives",
                    truncated=False,
                )
            raise RuntimeError("leaf disappeared")

    session = SimpleNamespace(
        id="session-1",
        workspace_id="workspace-1",
        user_id="user-1",
        session_metadata={
            "remote_connection_id": "conn-1",
            "remote_project_root": "/srv/project",
            "execution_target": {
                "kind": "remote_ssh",
                "cwd": "/srv/project/analysis",
            },
        },
    )

    context = await resolver_cls(
        max_bytes=32768,
        remote_reader=PartiallyFailingRemoteReader(),
    ).resolve(session)

    assert context is not None
    assert "remote root survives" in context
    assert "## Project instruction diagnostics" in context
    assert "Skipped /srv/project/analysis" in context
    assert "Project instructions unavailable" not in context


@pytest.mark.asyncio
async def test_remote_project_instruction_resolver_prefers_session_target_over_toolset():
    resolver_cls, instruction_file_cls = _instruction_classes()

    class FakeRemoteReader:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def read_first_existing(
            self,
            *,
            agent_session,
            connection_id: str,
            directory: str,
            filenames,
            max_bytes: int,
            remote_root: str,
        ):
            del agent_session, filenames, max_bytes
            self.calls.append(
                {
                    "connection_id": connection_id,
                    "directory": directory,
                    "remote_root": remote_root,
                }
            )
            if connection_id == "session-conn" and directory == "/srv/project":
                return instruction_file_cls(
                    source="ssh://session-conn/srv/project/AGENTS.md",
                    content="session target",
                    truncated=False,
                )
            return None

    reader = FakeRemoteReader()
    session = SimpleNamespace(
        id="session-1",
        workspace_id="workspace-1",
        user_id="user-1",
        toolset_policy={
            "remote_connection_id": "toolset-conn",
            "remote_project_root": "/wrong/project",
            "execution_target": {
                "kind": "remote_ssh",
                "cwd": "/wrong/project",
            },
        },
        session_metadata={
            "remote_connection_id": "session-conn",
            "remote_project_root": "/srv/project",
            "execution_target": {
                "kind": "remote_ssh",
                "cwd": "/srv/project/analysis",
            },
        },
    )

    context = await resolver_cls(max_bytes=32768, remote_reader=reader).resolve(session)

    assert context is not None
    assert "session target" in context
    assert reader.calls[0] == {
        "connection_id": "session-conn",
        "directory": "/srv/project",
        "remote_root": "/srv/project",
    }


@pytest.mark.asyncio
async def test_remote_project_instruction_failures_return_unavailable_marker():
    resolver_cls, _instruction_file_cls = _instruction_classes()

    class FailingRemoteReader:
        async def read_first_existing(self, **_kwargs):
            raise RuntimeError("ssh unavailable")

    session = SimpleNamespace(
        id="session-1",
        workspace_id="workspace-1",
        user_id="user-1",
        session_metadata={
            "remote_connection_id": "conn-1",
            "remote_project_root": "/srv/project",
            "execution_target": {"kind": "remote_ssh"},
        },
    )

    context = await resolver_cls(
        max_bytes=32768,
        remote_reader=FailingRemoteReader(),
    ).resolve(session)

    assert context is not None
    assert "## Project instructions" in context
    assert "Project instructions unavailable" in context

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shlex
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.config import settings
from app.models.project import Project
from app.models.remote_connection import RemoteConnection
from app.models.workspace import Workspace
from app.path_layout import bioinfoflow_home, state_root
from app.services.agent_harness.context import build_session_prompt_snapshot
from app.services.agent_harness.environment_runtime import (
    _DatabaseRemoteExecutor,
    workspace_runtime_for_session,
)
from app.services.agent_harness.factory import open_session_request_workspace
from app.services.agent_harness.sandbox.process_sandbox import (
    SandboxAvailability,
    SandboxRunner,
)
from app.services.agent_harness.tools import ToolCall
from app.services.agent_harness.workspace_runtime import (
    LocalWorkspaceBackend,
    RemoteWorkspaceBackend,
)
from app.services.llm.credentials import encrypt_secret
from app.services.remote_execution import RemoteCommandResult
from app.utils.exceptions import NotFoundError


class _RecordingRemoteExecutor:
    def __init__(self) -> None:
        self.connections = []
        self.stdin_calls = []

    async def run(
        self,
        connection,
        command,
        *,
        timeout_seconds,
        output_limit,
    ) -> RemoteCommandResult:
        del timeout_seconds, output_limit
        self.connections.append(connection)
        if 'shutil.which("bwrap")' in command:
            return RemoteCommandResult(
                exit_code=0,
                stdout=(
                    '{"path":"/usr/bin/bwrap","writable":false,'
                    '"available":true,"failure":null,'
                    '"system_roots":["/usr","/bin"],'
                    '"network_roots":[],"shell":"/bin/bash"}'
                ),
                stderr="",
                timed_out=False,
                truncated=False,
                stdout_truncated=False,
                stderr_truncated=False,
            )
        return RemoteCommandResult(
            exit_code=0,
            stdout='{"data":"aGVsbG8="}',
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )

    async def run_with_stdin(
        self,
        connection,
        command,
        *,
        stdin_data,
        timeout_seconds,
        output_limit,
    ) -> RemoteCommandResult:
        self.connections.append(connection)
        self.stdin_calls.append(
            {
                "command": command,
                "stdin_data": stdin_data,
                "timeout_seconds": timeout_seconds,
                "output_limit": output_limit,
            }
        )
        return RemoteCommandResult(
            exit_code=0,
            stdout="ok",
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )


class _RemoteInstructionExecutor:
    def __init__(
        self, content: str, *, skills: tuple[dict[str, str], ...] = ()
    ) -> None:
        self.content = content
        self.skills = skills
        self.connections = []
        self.commands = []

    async def run(
        self,
        connection,
        command,
        *,
        timeout_seconds,
        output_limit,
    ) -> RemoteCommandResult:
        del timeout_seconds, output_limit
        import json

        self.connections.append(connection)
        self.commands.append(command)
        payload = {
            "path": "/srv/project/AGENTS.md",
            "content": self.content,
        }
        if self.skills:
            payload["skills"] = list(self.skills)
        return RemoteCommandResult(
            exit_code=0,
            stdout=json.dumps(payload),
            stderr="",
            timed_out=False,
            truncated=False,
            stdout_truncated=False,
            stderr_truncated=False,
        )


class _LocalCommandRemoteExecutor:
    def __init__(self, *, environment: dict[str, str] | None = None) -> None:
        self.commands: list[str] = []
        self.environment = environment

    async def run(
        self,
        connection,
        command,
        *,
        timeout_seconds,
        output_limit,
    ) -> RemoteCommandResult:
        del connection
        self.commands.append(command)
        process = await asyncio.create_subprocess_exec(
            *shlex.split(command),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=(
                {**os.environ, **self.environment}
                if self.environment is not None
                else None
            ),
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
        truncated = len(stdout) + len(stderr) > output_limit
        return RemoteCommandResult(
            exit_code=process.returncode or 0,
            stdout=stdout[:output_limit].decode("utf-8", errors="replace"),
            stderr=stderr[:output_limit].decode("utf-8", errors="replace"),
            timed_out=False,
            truncated=truncated,
            stdout_truncated=len(stdout) > output_limit,
            stderr_truncated=len(stderr) > output_limit,
        )


async def _workspace(db_session) -> Workspace:
    workspace = Workspace(
        id=str(uuid4()),
        name="Harness workspace",
        slug=f"harness-{uuid4()}",
        is_default=False,
    )
    db_session.add(workspace)
    await db_session.commit()
    return workspace


async def _create_remote_project(db_session, *, remote_root: str):
    workspace = await _workspace(db_session)
    connection = RemoteConnection(
        workspace_id=str(workspace.id),
        name="Cluster",
        host="cluster.example.org",
        port=22,
        username="alice",
        auth_method="agent",
    )
    db_session.add(connection)
    await db_session.flush()
    project = Project(
        name="Remote project",
        storage_mode="remote",
        remote_connection_id=str(connection.id),
        remote_root_path=remote_root,
        user_id="user-1",
        workspace_id=str(workspace.id),
    )
    db_session.add(project)
    await db_session.commit()
    return workspace, project


@pytest.mark.asyncio
async def test_open_session_workspace_creates_isolated_projectless_directory(
    db_session,
) -> None:
    workspace = await _workspace(db_session)

    snapshot = await open_session_request_workspace(
        db_session,
        project_id=None,
        workspace_id=str(workspace.id),
        user_id="user-1",
    )

    root = Path(snapshot["root"])
    assert snapshot["runtime"] == "local"
    assert root.exists()
    assert root.is_dir()
    assert root != bioinfoflow_home()
    assert root != state_root()
    assert (
        root == bioinfoflow_home() / "agent_workspaces" / str(workspace.id) / "user-1"
    )


@pytest.mark.asyncio
async def test_open_session_workspace_rejects_unsafe_projectless_scope_ids(
    db_session,
) -> None:
    with pytest.raises(ValueError, match="invalid workspace id"):
        await open_session_request_workspace(
            db_session,
            project_id=None,
            workspace_id="../other-workspace",
            user_id="user-1",
        )


@pytest.mark.asyncio
async def test_open_session_workspace_describes_local_project(
    db_session, tmp_path, monkeypatch
) -> None:
    workspace = await _workspace(db_session)
    project = Project(
        name="Local project",
        directory_name="local-project",
        storage_mode="managed",
        user_id="user-1",
        workspace_id=str(workspace.id),
    )
    db_session.add(project)
    await db_session.commit()
    monkeypatch.setattr(
        "app.services.agent_harness.factory.project_home",
        lambda _project: tmp_path / "local-project",
    )
    monkeypatch.setattr(settings, "bioinfoflow_public_api_base_url", "")

    snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
    )

    assert snapshot == {
        "api_url": "http://127.0.0.1:8000/api/v1",
        "runtime": "local",
        "root": str((tmp_path / "local-project").resolve()),
    }


@pytest.mark.asyncio
async def test_open_session_workspace_rejects_project_outside_user_scope(
    db_session,
) -> None:
    workspace = await _workspace(db_session)
    other_workspace = await _workspace(db_session)
    project = Project(
        name="Other project",
        directory_name="other-project",
        storage_mode="managed",
        user_id="other-user",
        workspace_id=str(other_workspace.id),
    )
    db_session.add(project)
    await db_session.commit()

    with pytest.raises(NotFoundError, match="Project not found"):
        await open_session_request_workspace(
            db_session,
            project_id=str(project.id),
            workspace_id=str(workspace.id),
            user_id="user-1",
        )


@pytest.mark.asyncio
async def test_open_session_workspace_rejects_remote_connection_from_other_workspace(
    db_session,
) -> None:
    workspace = await _workspace(db_session)
    other_workspace = await _workspace(db_session)
    connection = RemoteConnection(
        workspace_id=str(other_workspace.id),
        name="Other cluster",
        host="other.example.org",
        port=22,
        username="alice",
        auth_method="agent",
    )
    db_session.add(connection)
    await db_session.flush()
    project = Project(
        name="Broken remote project",
        storage_mode="remote",
        remote_connection_id=str(connection.id),
        remote_root_path="/srv/project",
        user_id="user-1",
        workspace_id=str(workspace.id),
    )
    db_session.add(project)
    await db_session.commit()

    with pytest.raises(NotFoundError, match="Remote connection not found"):
        await open_session_request_workspace(
            db_session,
            project_id=str(project.id),
            workspace_id=str(workspace.id),
            user_id="user-1",
        )


@pytest.mark.asyncio
async def test_open_session_workspace_describes_remote_without_persisting_credentials(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1/",
    )
    workspace = await _workspace(db_session)
    connection = RemoteConnection(
        workspace_id=str(workspace.id),
        name="Cluster",
        host="cluster.example.org",
        port=22,
        username="alice",
        auth_method="agent",
    )
    db_session.add(connection)
    await db_session.flush()
    project = Project(
        name="Remote project",
        storage_mode="remote",
        remote_connection_id=str(connection.id),
        remote_root_path="/srv/project",
        user_id="user-1",
        workspace_id=str(workspace.id),
    )
    db_session.add(project)
    await db_session.commit()

    snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=_RemoteInstructionExecutor(""),
    )

    assert snapshot == {
        "api_url": "https://bioinfoflow.example/api/v1",
        "runtime": "remote_ssh",
        "root": "/srv/project",
        "remote_connection": {
            "id": str(connection.id),
            "name": "Cluster",
            "host": "cluster.example.org",
            "port": 22,
            "username": "alice",
        },
    }
    assert "password" not in repr(snapshot).lower()
    assert "private_key" not in repr(snapshot).lower()


@pytest.mark.asyncio
async def test_remote_session_freezes_remote_project_instructions_without_local_skills(
    db_session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    local_skills = tmp_path / "backend-skills"
    local_skill = local_skills / "backend-only"
    local_skill.mkdir(parents=True)
    (local_skill / "SKILL.md").write_text(
        "---\nname: backend-only\ndescription: Must stay local.\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "bioinfoflow_skills_root", str(local_skills))
    workspace = await _workspace(db_session)
    connection = RemoteConnection(
        workspace_id=str(workspace.id),
        name="Cluster",
        host="cluster.example.org",
        port=22,
        username="alice",
        auth_method="agent",
    )
    db_session.add(connection)
    await db_session.flush()
    project = Project(
        name="Remote project",
        storage_mode="remote",
        remote_connection_id=str(connection.id),
        remote_root_path="/srv/project",
        user_id="user-1",
        workspace_id=str(workspace.id),
    )
    db_session.add(project)
    await db_session.commit()
    executor = _RemoteInstructionExecutor("Use the cluster scheduler.")

    workspace_snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=executor,
    )
    prompt_snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={**workspace_snapshot, "project": str(project.id)},
    )

    assert workspace_snapshot["project_instructions"] == [
        "Instructions from /srv/project/AGENTS.md:\n\nUse the cluster scheduler."
    ]
    assert "Use the cluster scheduler." in prompt_snapshot["content"]
    assert "backend-only" not in prompt_snapshot["content"]
    assert str(local_skill / "SKILL.md") not in prompt_snapshot["content"]
    assert len(executor.commands) == 1


@pytest.mark.asyncio
async def test_remote_session_freezes_remote_skills_for_progressive_read_loading(
    db_session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    local_skills = tmp_path / "backend-skills"
    local_skill = local_skills / "backend-only"
    local_skill.mkdir(parents=True)
    (local_skill / "SKILL.md").write_text(
        "---\nname: backend-only\ndescription: Must stay local.\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "bioinfoflow_skills_root", str(local_skills))
    workspace = await _workspace(db_session)
    connection = RemoteConnection(
        workspace_id=str(workspace.id),
        name="Cluster",
        host="cluster.example.org",
        port=22,
        username="alice",
        auth_method="agent",
    )
    db_session.add(connection)
    await db_session.flush()
    project = Project(
        name="Remote project",
        storage_mode="remote",
        remote_connection_id=str(connection.id),
        remote_root_path="/srv/project",
        user_id="user-1",
        workspace_id=str(workspace.id),
    )
    db_session.add(project)
    await db_session.commit()
    executor = _RemoteInstructionExecutor(
        "Use the cluster scheduler.",
        skills=(
            {
                "name": "variant-review",
                "description": "Review called variants.",
                "path": "/srv/project/.agents/skills/variant-review/SKILL.md",
            },
            {
                "name": "alignment-qc",
                "description": "Inspect alignment quality.",
                "path": "/srv/project/.codex/skills/alignment-qc/SKILL.md",
            },
        ),
    )

    workspace_snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=executor,
    )
    prompt_snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={**workspace_snapshot, "project": str(project.id)},
    )

    assert workspace_snapshot["skills"] == [
        {
            "name": "alignment-qc",
            "description": "Inspect alignment quality.",
            "path": "/srv/project/.codex/skills/alignment-qc/SKILL.md",
        },
        {
            "name": "variant-review",
            "description": "Review called variants.",
            "path": "/srv/project/.agents/skills/variant-review/SKILL.md",
        },
    ]
    assert (
        "- alignment-qc: Inspect alignment quality. "
        "(/srv/project/.codex/skills/alignment-qc/SKILL.md)"
        in prompt_snapshot["content"]
    )
    assert (
        "- variant-review: Review called variants. "
        "(/srv/project/.agents/skills/variant-review/SKILL.md)"
        in prompt_snapshot["content"]
    )
    assert "backend-only" not in prompt_snapshot["content"]
    assert str(local_skill / "SKILL.md") not in prompt_snapshot["content"]
    assert "skill_read_roots" not in prompt_snapshot
    assert len(executor.commands) == 1


@pytest.mark.asyncio
async def test_remote_skill_metadata_frozen_for_the_prompt_has_a_utf8_total_budget(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    workspace, project = await _create_remote_project(
        db_session,
        remote_root="/srv/project",
    )
    executor = _RemoteInstructionExecutor(
        "",
        skills=tuple(
            {
                "name": f"skill-{index:03d}",
                "description": f"{'测' * 1_800}-{index:03d}",
                "path": (f"/srv/project/.agents/skills/skill-{index:03d}/SKILL.md"),
            }
            for index in reversed(range(13))
        ),
    )

    workspace_snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=executor,
    )

    skill_lines = [
        f"- {skill['name']}: {skill['description']} ({skill['path']})"
        for skill in workspace_snapshot["skills"]
    ]
    skill_section = (
        "## Available skills\n"
        "Skills are reusable procedures. Load one only when relevant by using read "
        "on its SKILL.md path, then follow its referenced files as needed.\n"
        + "\n".join(skill_lines)
    )
    assert len(skill_section.encode("utf-8")) <= 64 * 1024
    assert [skill["name"] for skill in workspace_snapshot["skills"]] == sorted(
        skill["name"] for skill in workspace_snapshot["skills"]
    )
    assert workspace_snapshot["skills"][0]["name"] == "skill-000"
    assert not any(
        skill["name"] == "skill-012" for skill in workspace_snapshot["skills"]
    )


@pytest.mark.asyncio
async def test_remote_skill_discovery_rejects_symlinks_escape_and_oversized_metadata(
    db_session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    remote_root = tmp_path / "remote-project"
    agents_skill = remote_root / ".agents" / "skills" / "variant-review"
    codex_skill = remote_root / ".codex" / "skills" / "alignment-qc"
    agents_skill.mkdir(parents=True)
    codex_skill.mkdir(parents=True)
    (agents_skill / "SKILL.md").write_text(
        "---\nname: variant-review\ndescription: Review called variants.\n---\n",
        encoding="utf-8",
    )
    (codex_skill / "SKILL.md").write_text(
        "---\nname: alignment-qc\ndescription: Inspect alignment quality.\n---\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside-skill"
    outside.mkdir()
    (outside / "SKILL.md").write_text(
        "---\nname: escaped\ndescription: Must not be advertised.\n---\n",
        encoding="utf-8",
    )
    (remote_root / ".agents" / "skills" / "escaped").symlink_to(
        outside, target_is_directory=True
    )
    linked_file = remote_root / ".codex" / "skills" / "linked-file"
    linked_file.mkdir()
    (linked_file / "SKILL.md").symlink_to(outside / "SKILL.md")
    oversized = remote_root / ".agents" / "skills" / "oversized"
    oversized.mkdir()
    (oversized / "SKILL.md").write_text(
        "---\nname: oversized\ndescription: " + ("x" * (17 * 1024)) + "\n---\n",
        encoding="utf-8",
    )
    workspace = await _workspace(db_session)
    connection = RemoteConnection(
        workspace_id=str(workspace.id),
        name="Cluster",
        host="cluster.example.org",
        port=22,
        username="alice",
        auth_method="agent",
    )
    db_session.add(connection)
    await db_session.flush()
    project = Project(
        name="Remote project",
        storage_mode="remote",
        remote_connection_id=str(connection.id),
        remote_root_path=str(remote_root),
        user_id="user-1",
        workspace_id=str(workspace.id),
    )
    db_session.add(project)
    await db_session.commit()

    snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=_LocalCommandRemoteExecutor(),
    )

    assert snapshot["skills"] == [
        {
            "name": "alignment-qc",
            "description": "Inspect alignment quality.",
            "path": str(codex_skill / "SKILL.md"),
        },
        {
            "name": "variant-review",
            "description": "Review called variants.",
            "path": str(agents_skill / "SKILL.md"),
        },
    ]


@pytest.mark.asyncio
async def test_remote_context_discovery_does_not_follow_a_file_swapped_to_a_symlink(
    db_session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    remote_root = tmp_path / "remote-project"
    remote_root.mkdir()
    instructions = remote_root / "AGENTS.md"
    instructions.write_text("Use the project scheduler.\n", encoding="utf-8")
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("DO-NOT-LEAK-REMOTE-SECRET\n", encoding="utf-8")
    sitecustomize_root = tmp_path / "sitecustomize"
    sitecustomize_root.mkdir()
    (sitecustomize_root / "sitecustomize.py").write_text(
        """
import os
from pathlib import Path

race_path = Path(os.environ["BIOINFOFLOW_TEST_RACE_PATH"])
race_target = os.environ["BIOINFOFLOW_TEST_RACE_TARGET"]
original_is_file = Path.is_file
original_os_open = os.open

def swap_to_symlink():
    if not race_path.is_symlink():
        race_path.unlink(missing_ok=True)
        race_path.symlink_to(race_target)

def racing_is_file(self):
    result = original_is_file(self)
    if result and self == race_path:
        swap_to_symlink()
    return result

def racing_os_open(path, flags, mode=0o777, *, dir_fd=None):
    if Path(path) == race_path or (dir_fd is not None and path == race_path.name):
        swap_to_symlink()
    return original_os_open(path, flags, mode, dir_fd=dir_fd)

Path.is_file = racing_is_file
os.open = racing_os_open
""".strip(),
        encoding="utf-8",
    )
    workspace, project = await _create_remote_project(
        db_session, remote_root=str(remote_root)
    )

    snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=_LocalCommandRemoteExecutor(
            environment={
                "PYTHONPATH": str(sitecustomize_root),
                "BIOINFOFLOW_TEST_RACE_PATH": str(instructions),
                "BIOINFOFLOW_TEST_RACE_TARGET": str(secret),
            }
        ),
    )

    assert "DO-NOT-LEAK-REMOTE-SECRET" not in json.dumps(snapshot)


@pytest.mark.asyncio
async def test_remote_skill_discovery_reads_only_the_configured_byte_limit(
    db_session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    remote_root = tmp_path / "remote-project"
    oversized_skill = remote_root / ".agents" / "skills" / "oversized" / "SKILL.md"
    oversized_skill.parent.mkdir(parents=True)
    oversized_skill.write_text(
        "---\nname: oversized\ndescription: " + ("x" * (17 * 1024)) + "\n---\n",
        encoding="utf-8",
    )
    sitecustomize_root = tmp_path / "sitecustomize"
    sitecustomize_root.mkdir()
    (sitecustomize_root / "sitecustomize.py").write_text(
        """
import os
from pathlib import Path

guarded_path = Path(os.environ["BIOINFOFLOW_TEST_BOUNDED_PATH"])
original_read_bytes = Path.read_bytes

def guarded_read_bytes(self):
    if self == guarded_path:
        raise RuntimeError("attempted an unbounded remote metadata read")
    return original_read_bytes(self)

Path.read_bytes = guarded_read_bytes
""".strip(),
        encoding="utf-8",
    )
    workspace, project = await _create_remote_project(
        db_session, remote_root=str(remote_root)
    )

    snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=_LocalCommandRemoteExecutor(
            environment={
                "PYTHONPATH": str(sitecustomize_root),
                "BIOINFOFLOW_TEST_BOUNDED_PATH": str(oversized_skill),
            }
        ),
    )

    assert "skills" not in snapshot


@pytest.mark.asyncio
async def test_remote_skill_discovery_stops_after_the_deterministic_limit(
    db_session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    remote_root = tmp_path / "remote-project"
    for index in reversed(range(201)):
        skill = remote_root / ".agents" / "skills" / f"skill-{index:03d}"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: skill-{index:03d}\ndescription: Skill {index:03d}.\n---\n",
            encoding="utf-8",
        )
    sitecustomize_root = tmp_path / "sitecustomize"
    sitecustomize_root.mkdir()
    (sitecustomize_root / "sitecustomize.py").write_text(
        """
import os

limit = int(os.environ["BIOINFOFLOW_TEST_ENUMERATION_LIMIT"])
original_scandir = os.scandir
scandir_calls = 0

def bounded_scandir(path):
    global scandir_calls
    scandir_calls += 1
    if scandir_calls > limit:
        raise RuntimeError("remote skill discovery entered a 201st candidate")
    return original_scandir(path)

os.scandir = bounded_scandir
""".strip(),
        encoding="utf-8",
    )
    workspace, project = await _create_remote_project(
        db_session, remote_root=str(remote_root)
    )

    snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=_LocalCommandRemoteExecutor(
            environment={
                "PYTHONPATH": str(sitecustomize_root),
                # One scan for the skills root plus one scan for each of the
                # 200 accepted candidate directories.
                "BIOINFOFLOW_TEST_ENUMERATION_LIMIT": "201",
            }
        ),
    )

    assert [skill["name"] for skill in snapshot["skills"]] == [
        f"skill-{index:03d}" for index in range(200)
    ]


@pytest.mark.asyncio
async def test_remote_skill_discovery_bounds_scanned_directory_entries(
    db_session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    remote_root = tmp_path / "remote-project"
    skills_root = remote_root / ".agents" / "skills"
    skills_root.mkdir(parents=True)
    scan_limit = 3_200
    for index in range(scan_limit + 1):
        (skills_root / f"irrelevant-{index:04d}.txt").touch()
    sitecustomize_root = tmp_path / "sitecustomize"
    sitecustomize_root.mkdir()
    (sitecustomize_root / "sitecustomize.py").write_text(
        """
import os

limit = int(os.environ["BIOINFOFLOW_TEST_ENTRY_SCAN_LIMIT"])
original_scandir = os.scandir
scanned_entries = 0

class BoundedScandir:
    def __init__(self, stream):
        self.stream = stream

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def __iter__(self):
        return self

    def __next__(self):
        global scanned_entries
        entry = next(self.stream)
        scanned_entries += 1
        if scanned_entries > limit:
            raise RuntimeError("remote skill discovery exceeded its entry budget")
        return entry

def bounded_scandir(path):
    return BoundedScandir(original_scandir(path))

os.scandir = bounded_scandir
""".strip(),
        encoding="utf-8",
    )
    workspace, project = await _create_remote_project(
        db_session, remote_root=str(remote_root)
    )

    snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=_LocalCommandRemoteExecutor(
            environment={
                "PYTHONPATH": str(sitecustomize_root),
                "BIOINFOFLOW_TEST_ENTRY_SCAN_LIMIT": str(scan_limit),
            }
        ),
    )

    assert "skills" not in snapshot


@pytest.mark.asyncio
async def test_remote_skill_discovery_bounds_scanned_directories(
    db_session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    remote_root = tmp_path / "remote-project"
    skills_root = remote_root / ".agents" / "skills"
    directory_limit = 800
    for index in range(directory_limit):
        (skills_root / f"empty-{index:04d}").mkdir(parents=True)
    sitecustomize_root = tmp_path / "sitecustomize"
    sitecustomize_root.mkdir()
    (sitecustomize_root / "sitecustomize.py").write_text(
        """
import os

limit = int(os.environ["BIOINFOFLOW_TEST_DIRECTORY_SCAN_LIMIT"])
original_scandir = os.scandir
scanned_directories = 0

def bounded_scandir(path):
    global scanned_directories
    scanned_directories += 1
    if scanned_directories > limit:
        raise RuntimeError("remote skill discovery exceeded its directory budget")
    return original_scandir(path)

os.scandir = bounded_scandir
""".strip(),
        encoding="utf-8",
    )
    workspace, project = await _create_remote_project(
        db_session, remote_root=str(remote_root)
    )

    snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=_LocalCommandRemoteExecutor(
            environment={
                "PYTHONPATH": str(sitecustomize_root),
                "BIOINFOFLOW_TEST_DIRECTORY_SCAN_LIMIT": str(directory_limit),
            }
        ),
    )

    assert "skills" not in snapshot


@pytest.mark.asyncio
async def test_remote_skill_discovery_bounds_directory_depth(
    db_session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    remote_root = tmp_path / "remote-project"
    skill_directory = remote_root / ".agents" / "skills"
    maximum_depth = 32
    for depth in range(maximum_depth + 1):
        skill_directory /= f"level-{depth:02d}"
    skill_directory.mkdir(parents=True)
    (skill_directory / "SKILL.md").write_text(
        "---\nname: too-deep\ndescription: Must not be discovered.\n---\n",
        encoding="utf-8",
    )
    workspace, project = await _create_remote_project(
        db_session, remote_root=str(remote_root)
    )

    snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=_LocalCommandRemoteExecutor(),
    )

    assert "skills" not in snapshot


@pytest.mark.asyncio
async def test_remote_skill_discovery_is_deterministic_and_bounded(
    db_session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    remote_root = tmp_path / "remote-project"
    for index in reversed(range(205)):
        skill = remote_root / ".agents" / "skills" / f"skill-{index:03d}"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: skill-{index:03d}\ndescription: Skill {index:03d}.\n---\n",
            encoding="utf-8",
        )
    workspace, project = await _create_remote_project(
        db_session, remote_root=str(remote_root)
    )

    snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=_LocalCommandRemoteExecutor(),
    )

    assert len(snapshot["skills"]) == 200
    assert [item["name"] for item in snapshot["skills"]] == [
        f"skill-{index:03d}" for index in range(200)
    ]


@pytest.mark.asyncio
async def test_remote_context_discovery_fails_closed_when_remote_root_is_invalid(
    db_session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    workspace, project = await _create_remote_project(
        db_session, remote_root=str(tmp_path / "missing-project")
    )

    with pytest.raises(ValueError, match="remote project root is invalid"):
        await open_session_request_workspace(
            db_session,
            project_id=str(project.id),
            workspace_id=str(workspace.id),
            user_id="user-1",
            remote_executor=_LocalCommandRemoteExecutor(),
        )


@pytest.mark.asyncio
async def test_remote_session_discovers_project_instructions_from_parent_directory(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    workspace = await _workspace(db_session)
    connection = RemoteConnection(
        workspace_id=str(workspace.id),
        name="Cluster",
        host="cluster.example.org",
        port=22,
        username="alice",
        auth_method="agent",
    )
    db_session.add(connection)
    await db_session.flush()
    project = Project(
        name="Nested remote project",
        storage_mode="remote",
        remote_connection_id=str(connection.id),
        remote_root_path="/srv/team/project",
        user_id="user-1",
        workspace_id=str(workspace.id),
    )
    db_session.add(project)
    await db_session.commit()

    class ParentInstructionExecutor(_RemoteInstructionExecutor):
        async def run(self, connection, command, **kwargs):
            if "root.parents" not in command:
                self.content = ""
                return await super().run(connection, command, **kwargs)
            del kwargs
            self.connections.append(connection)
            self.commands.append(command)
            return RemoteCommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "path": "/srv/team/AGENTS.md",
                        "content": "Use the team scheduler.",
                    }
                ),
                stderr="",
                timed_out=False,
                truncated=False,
                stdout_truncated=False,
                stderr_truncated=False,
            )

    executor = ParentInstructionExecutor("Use the team scheduler.")
    snapshot = await open_session_request_workspace(
        db_session,
        project_id=str(project.id),
        workspace_id=str(workspace.id),
        user_id="user-1",
        remote_executor=executor,
    )

    assert snapshot["project_instructions"] == [
        "Instructions from /srv/team/AGENTS.md:\n\nUse the team scheduler."
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "configured_url,error",
    [
        ("", "must be configured"),
        ("http://localhost:8000/api/v1", "cannot use localhost"),
    ],
)
async def test_open_session_workspace_fails_closed_for_unreachable_remote_api(
    db_session,
    monkeypatch,
    configured_url,
    error,
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        configured_url,
    )
    workspace = await _workspace(db_session)
    connection = RemoteConnection(
        workspace_id=str(workspace.id),
        name="Cluster",
        host="cluster.example.org",
        port=22,
        username="alice",
        auth_method="agent",
    )
    db_session.add(connection)
    await db_session.flush()
    project = Project(
        name="Remote project",
        storage_mode="remote",
        remote_connection_id=str(connection.id),
        remote_root_path="/srv/project",
        user_id="user-1",
        workspace_id=str(workspace.id),
    )
    db_session.add(project)
    await db_session.commit()

    with pytest.raises(ValueError, match=error):
        await open_session_request_workspace(
            db_session,
            project_id=str(project.id),
            workspace_id=str(workspace.id),
            user_id="user-1",
        )


@pytest.mark.asyncio
async def test_remote_runtime_resolves_current_credentials_only_when_executing(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    workspace = await _workspace(db_session)
    connection = RemoteConnection(
        workspace_id=str(workspace.id),
        name="Cluster",
        host="cluster.example.org",
        port=22,
        username="alice",
        auth_method="agent",
    )
    db_session.add(connection)
    await db_session.commit()
    executor = _RecordingRemoteExecutor()
    session = SimpleNamespace(
        workspace_id=str(workspace.id),
        project_id=str(uuid4()),
        permission_mode="ask_dangerous",
        workspace_access="read_write",
        workspace_snapshot={
            "runtime": "remote_ssh",
            "root": "/srv/project",
            "remote_connection": {
                "id": str(connection.id),
                "name": connection.name,
                "host": connection.host,
                "port": connection.port,
                "username": connection.username,
            },
        },
    )

    async def write_artifact(payload):
        return {"artifact_id": str(payload)}

    runtime = workspace_runtime_for_session(
        db_session,
        session,
        remote_executor=executor,
        artifact_writer=write_artifact,
    )
    path, content = await runtime._executor.backend.read_bytes("result.txt")

    assert isinstance(runtime._executor.backend, RemoteWorkspaceBackend)
    assert runtime._executor.backend.artifact_writer is write_artifact
    assert runtime._executor.environment["BIOFLOW_API_URL"] == (
        "https://bioinfoflow.example/api/v1"
    )
    assert path == "/srv/project/result.txt"
    assert content == b"hello"
    assert executor.connections[0].id == str(connection.id)


@pytest.mark.asyncio
async def test_database_remote_executor_run_with_stdin_rejects_snapshot_mismatch(
    db_session,
) -> None:
    executor = _RecordingRemoteExecutor()
    adapter = _DatabaseRemoteExecutor(
        db_session,
        workspace_id=str(uuid4()),
        connection_id="expected-connection",
        executor=executor,
    )

    with pytest.raises(ValueError, match="does not match"):
        await adapter.run_with_stdin(
            SimpleNamespace(id="other-connection"),
            "bash -s",
            stdin_data=b"secret\x00payload\n",
            timeout_seconds=17,
            output_limit=4097,
        )

    assert executor.stdin_calls == []


@pytest.mark.asyncio
async def test_database_remote_executor_run_with_stdin_uses_fresh_credentials(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_credential_key", "factory-test-key")
    workspace = await _workspace(db_session)
    connection = RemoteConnection(
        workspace_id=str(workspace.id),
        name="Credential cluster",
        host="cluster.example.org",
        port=22,
        username="alice",
        auth_method="password",
        encrypted_password=encrypt_secret("old-password"),
    )
    db_session.add(connection)
    await db_session.commit()
    executor = _RecordingRemoteExecutor()
    adapter = _DatabaseRemoteExecutor(
        db_session,
        workspace_id=str(workspace.id),
        connection_id=str(connection.id),
        executor=executor,
    )

    connection.encrypted_password = encrypt_secret("rotated-password")
    await db_session.commit()
    stdin_data = b"token-with-binary-byte:\x00\xff\n"
    result = await adapter.run_with_stdin(
        SimpleNamespace(
            id=str(connection.id),
            host="cluster.example.org",
            port=22,
            username="alice",
        ),
        "bash -s -- --flag",
        stdin_data=stdin_data,
        timeout_seconds=23,
        output_limit=8193,
    )

    assert result.stdout == "ok"
    assert executor.connections[0].password == "rotated-password"
    assert executor.stdin_calls == [
        {
            "command": "bash -s -- --flag",
            "stdin_data": stdin_data,
            "timeout_seconds": 23,
            "output_limit": 8193,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("host", "replacement.example.org"),
        ("port", 2222),
        ("username", "mallory"),
    ],
)
async def test_remote_runtime_rejects_connection_target_drift(
    db_session, monkeypatch, field, replacement
) -> None:
    monkeypatch.setattr(
        settings,
        "bioinfoflow_public_api_base_url",
        "https://bioinfoflow.example/api/v1",
    )
    workspace = await _workspace(db_session)
    connection = RemoteConnection(
        workspace_id=str(workspace.id),
        name="Cluster",
        host="cluster.example.org",
        port=22,
        username="alice",
        auth_method="agent",
    )
    db_session.add(connection)
    await db_session.commit()
    executor = _RecordingRemoteExecutor()
    session = SimpleNamespace(
        workspace_id=str(workspace.id),
        project_id=str(uuid4()),
        permission_mode="ask_changes",
        workspace_access="read_only",
        workspace_snapshot={
            "runtime": "remote_ssh",
            "root": "/srv/project",
            "remote_connection": {
                "id": str(connection.id),
                "name": connection.name,
                "host": connection.host,
                "port": connection.port,
                "username": connection.username,
            },
        },
    )
    setattr(connection, field, replacement)
    await db_session.commit()
    runtime = workspace_runtime_for_session(
        db_session,
        session,
        remote_executor=executor,
    )

    result = await runtime.execute(ToolCall("read-1", "read", {"path": "result.txt"}))

    assert result.status == "failed"
    assert "target changed after the Agent session was created" in (result.error or "")
    assert executor.connections == []


@pytest.mark.asyncio
async def test_database_remote_executor_serializes_only_credential_resolution(
    monkeypatch,
) -> None:
    resolution = SimpleNamespace(active=0, maximum=0)

    class _ConcurrentRemoteConnectionService:
        def __init__(self, _db) -> None:
            pass

        async def get_connection(self, connection_id, *, workspace_id):
            assert connection_id == "connection-1"
            assert workspace_id == "workspace-1"
            resolution.active += 1
            resolution.maximum = max(resolution.maximum, resolution.active)
            await asyncio.sleep(0.01)
            return SimpleNamespace(id=connection_id)

        async def resolve_connection_config(self, model):
            await asyncio.sleep(0.01)
            resolution.active -= 1
            return SimpleNamespace(
                id=model.id,
                host="cluster.example.org",
                port=22,
                username="alice",
                password="fresh-secret",
            )

    class _ParallelRemoteExecutor(_RecordingRemoteExecutor):
        def __init__(self) -> None:
            super().__init__()
            self.entered = 0
            self.both_entered = asyncio.Event()

        async def _wait_for_peer(self) -> None:
            self.entered += 1
            if self.entered == 2:
                self.both_entered.set()
            await asyncio.wait_for(self.both_entered.wait(), timeout=1)

        async def run(self, *args, **kwargs) -> RemoteCommandResult:
            await self._wait_for_peer()
            return await super().run(*args, **kwargs)

        async def run_with_stdin(self, *args, **kwargs) -> RemoteCommandResult:
            await self._wait_for_peer()
            return await super().run_with_stdin(*args, **kwargs)

    monkeypatch.setattr(
        "app.services.agent_harness.environment_runtime.RemoteConnectionService",
        _ConcurrentRemoteConnectionService,
    )
    executor = _ParallelRemoteExecutor()
    adapter = _DatabaseRemoteExecutor(
        object(),
        workspace_id="workspace-1",
        connection_id="connection-1",
        executor=executor,
    )
    snapshot = SimpleNamespace(
        id="connection-1",
        host="cluster.example.org",
        port=22,
        username="alice",
    )

    await asyncio.gather(
        adapter.run(
            snapshot,
            "first",
            timeout_seconds=10,
            output_limit=100,
        ),
        adapter.run_with_stdin(
            snapshot,
            "second",
            stdin_data=b"stdin",
            timeout_seconds=10,
            output_limit=100,
        ),
    )

    assert resolution.maximum == 1
    assert resolution.active == 0
    assert executor.entered == 2


def test_local_runtime_respects_the_frozen_root_and_uses_the_default_tool_contract(
    db_session, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_public_api_base_url", "")
    session = SimpleNamespace(
        workspace_id="workspace-1",
        user_id="user-1",
        project_id=None,
        permission_mode="ask_changes",
        workspace_access="read_only",
        workspace_snapshot={"runtime": "local", "root": str(tmp_path)},
    )

    runtime = workspace_runtime_for_session(db_session, session)

    assert isinstance(runtime._executor.backend, LocalWorkspaceBackend)
    assert runtime._executor.backend.working_directory == tmp_path.resolve()
    assert runtime._executor.environment["BIOFLOW_API_URL"] == (
        "http://127.0.0.1:8000/api/v1"
    )
    assert [tool.name for tool in runtime.tools] == [
        "read",
        "bash",
        "edit",
        "write",
        "ask_user",
        "update_plan",
    ]


@pytest.mark.asyncio
async def test_local_factory_gives_bash_the_same_platform_path_protection(
    db_session, tmp_path, monkeypatch
) -> None:
    external_root = tmp_path / "home"
    repo_root = external_root / "BioinfoFlow"
    data_root = repo_root / "data"
    state = data_root / "state"
    source = repo_root / "backend" / "app" / "secret.py"
    attachment = state / "agent_harness" / "attachments" / "secret.txt"
    socket = external_root / "docker.sock"
    for path in (source, attachment, socket):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("platform-secret", encoding="utf-8")
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    monkeypatch.setattr(settings, "bioinfoflow_home", str(data_root))
    monkeypatch.setattr(settings, "docker_socket", f"unix://{socket}")

    captured = []

    class _CaptureAdapter:
        name = "capture"

        def availability(self):
            return SandboxAvailability("capture", "/capture", True)

        def available(self):
            return True

        def supports_docker_socket(self, root):
            del root
            return False

        def build_argv(self, spec):
            captured.append(spec)
            return ["bash", "--noprofile", "--norc", "-c", "true"]

    runner = SandboxRunner(enabled=True, adapters=[_CaptureAdapter()])
    monkeypatch.setattr(
        SandboxRunner,
        "from_settings",
        classmethod(lambda cls, source=None: runner),
    )
    session = SimpleNamespace(
        workspace_id="workspace-1",
        user_id="user-1",
        project_id="project-1",
        permission_mode="full_access",
        workspace_access="read_write",
        workspace_snapshot={"runtime": "local", "root": str(external_root)},
    )

    runtime = workspace_runtime_for_session(db_session, session)
    read_result = await runtime.execute(
        ToolCall("read-source", "read", {"path": str(source)})
    )
    write_result = await runtime.execute(
        ToolCall("write-state", "write", {"path": str(attachment), "content": "x"})
    )
    bash_result = await runtime.execute(
        ToolCall("bash-boundary", "bash", {"command": "true"})
    )

    assert read_result.status == "failed"
    assert write_result.status == "failed"
    assert bash_result.status == "completed"
    assert len(captured) == 1
    protected = set(captured[0].protected_roots)
    assert repo_root.resolve() in protected
    assert state.resolve() in protected
    assert socket.resolve() in protected


@pytest.mark.asyncio
async def test_local_factory_keeps_a_project_under_source_dev_data_writable(
    db_session, tmp_path, monkeypatch
) -> None:
    repo_root = tmp_path / "BioinfoFlow"
    data_root = repo_root / "data"
    project_root = data_root / "projects" / "project-1"
    state = data_root / "state"
    project_root.mkdir(parents=True)
    state.mkdir(parents=True)
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    monkeypatch.setattr(settings, "bioinfoflow_home", str(data_root))

    captured = []

    class _CaptureAdapter:
        name = "capture"

        def availability(self):
            return SandboxAvailability("capture", "/capture", True)

        def available(self):
            return True

        def supports_docker_socket(self, root):
            del root
            return False

        def build_argv(self, spec):
            captured.append(spec)
            return ["bash", "--noprofile", "--norc", "-c", "true"]

    runner = SandboxRunner(enabled=True, adapters=[_CaptureAdapter()])
    monkeypatch.setattr(
        SandboxRunner,
        "from_settings",
        classmethod(lambda cls, source=None: runner),
    )
    session = SimpleNamespace(
        workspace_id="workspace-1",
        user_id="user-1",
        project_id="project-1",
        permission_mode="full_access",
        workspace_access="read_write",
        workspace_snapshot={"runtime": "local", "root": str(project_root)},
    )

    runtime = workspace_runtime_for_session(db_session, session)
    write_result = await runtime.execute(
        ToolCall("write-project", "write", {"path": "result.txt", "content": "ok"})
    )
    bash_result = await runtime.execute(
        ToolCall("bash-project", "bash", {"command": "true"})
    )

    assert write_result.status == "completed"
    assert (project_root / "result.txt").read_text(encoding="utf-8") == "ok"
    assert bash_result.status == "completed"
    assert captured[0].write_roots == [project_root.resolve()]
    assert repo_root.resolve() not in captured[0].protected_roots
    assert state.resolve() not in captured[0].protected_roots


@pytest.mark.asyncio
async def test_local_runtime_can_read_every_skill_advertised_in_the_prompt(
    db_session, tmp_path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    configured_root = tmp_path / "configured-skills"
    skill = configured_root / "ngs-runtime"
    skill.mkdir(parents=True)
    skill_file = skill / "SKILL.md"
    skill_file.write_text(
        "---\nname: ngs-runtime\ndescription: Inspect the runtime.\n---\n"
        "Run the environment checks.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "bioinfoflow_skills_root", str(configured_root))
    prompt_snapshot = build_session_prompt_snapshot(
        core_snapshot={"id": "core-v1", "content": "Core behavior."},
        workspace={"runtime": "local", "root": str(project)},
    )
    session = SimpleNamespace(
        workspace_id="workspace-1",
        user_id="user-1",
        project_id="project-1",
        permission_mode="ask_changes",
        workspace_access="read_only",
        prompt_snapshot=prompt_snapshot,
        workspace_snapshot={"runtime": "local", "root": str(project)},
    )
    runtime = workspace_runtime_for_session(db_session, session)

    result = await runtime.execute(
        ToolCall("read-skill", "read", {"path": str(skill_file.resolve())})
    )

    assert str(skill_file.resolve()) in prompt_snapshot["content"]
    assert result.status == "completed"
    assert "Run the environment checks." in result.output["text"]


def test_local_project_runtime_rejects_a_missing_workspace_root(db_session) -> None:
    session = SimpleNamespace(
        workspace_id="workspace-1",
        user_id="user-1",
        project_id="project-1",
        permission_mode="ask_changes",
        workspace_access="read_only",
        workspace_snapshot={"runtime": "local"},
    )

    with pytest.raises(ValueError, match="missing its root"):
        workspace_runtime_for_session(db_session, session)


def test_remote_runtime_revalidates_public_api_configuration(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "bioinfoflow_public_api_base_url", "")
    session = SimpleNamespace(
        workspace_id=str(uuid4()),
        project_id=str(uuid4()),
        permission_mode="ask_changes",
        workspace_access="read_only",
        workspace_snapshot={
            "api_url": "https://previous.example/api/v1",
            "runtime": "remote_ssh",
            "root": "/srv/project",
            "remote_connection": {
                "id": str(uuid4()),
                "name": "Cluster",
                "host": "cluster.example.org",
                "port": 22,
                "username": "alice",
            },
        },
    )

    with pytest.raises(ValueError, match="must be configured"):
        workspace_runtime_for_session(db_session, session)

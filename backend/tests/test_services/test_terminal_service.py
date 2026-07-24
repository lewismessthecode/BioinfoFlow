from __future__ import annotations

import asyncio
import contextlib
import shlex
from pathlib import Path

import pytest

from app.services.remote_execution import RemoteConnectionConfig
from app.services.terminal_service import (
    DefaultRemoteTerminalFactory,
    TerminalSessionManager,
)
from app.utils.exceptions import BadRequestError


async def _next_message(
    queue: asyncio.Queue[dict], kind: str, *, contains: str | None = None
) -> dict:
    deadline = asyncio.get_running_loop().time() + 5
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise AssertionError(f"Timed out waiting for terminal message: {kind}")
        message = await asyncio.wait_for(queue.get(), timeout=remaining)
        if message["type"] == kind and (
            contains is None or contains in str(message.get("data", ""))
        ):
            return message


class FakeRemoteTerminalTransport:
    def __init__(self) -> None:
        self.output: asyncio.Queue[bytes] = asyncio.Queue()
        self.writes: list[bytes] = []
        self.resizes: list[tuple[int, int]] = []
        self.terminated = False
        self.exit_code = 0

    async def read(self, _max_bytes: int) -> bytes:
        return await self.output.get()

    async def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def resize(self, *, cols: int, rows: int) -> None:
        self.resizes.append((cols, rows))

    async def wait(self) -> int:
        return self.exit_code

    async def terminate(self) -> None:
        self.terminated = True
        self.output.put_nowait(b"")

    def feed(self, data: bytes) -> None:
        self.output.put_nowait(data)


class HangingTerminateRemoteTerminalTransport(FakeRemoteTerminalTransport):
    async def terminate(self) -> None:
        await asyncio.Event().wait()


class _FakeAsyncSshProcess:
    def __init__(self) -> None:
        self.stdout = asyncio.StreamReader()
        self.stdin = None


class _FakeAsyncSshClient:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict]] = []

    async def create_process(self, command: str, **kwargs):
        self.created.append((command, kwargs))
        return _FakeAsyncSshProcess()


class _FakeAsyncSshClientContext:
    def __init__(self, client: _FakeAsyncSshClient) -> None:
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, *_args):
        return None


class _FakeAsyncSshExecutor:
    def __init__(self) -> None:
        self.client = _FakeAsyncSshClient()
        self.connections: list[tuple[RemoteConnectionConfig, int]] = []

    def _connect(self, connection: RemoteConnectionConfig, timeout_seconds: int):
        self.connections.append((connection, timeout_seconds))
        return _FakeAsyncSshClientContext(self.client)


@pytest.mark.asyncio
async def test_remote_terminal_factory_uses_stored_credential_jump_for_outer_transport():
    jump = RemoteConnectionConfig(
        id="jump-1",
        name="Bastion",
        host="bastion.example.org",
        username="jump-user",
        password="jump-secret",
    )
    target = RemoteConnectionConfig(
        id="target-1",
        name="Cluster",
        host="cluster.example.org",
        username="alice",
        port=2222,
        jump_connection=jump,
    )
    async_executor = _FakeAsyncSshExecutor()
    factory = DefaultRemoteTerminalFactory(async_executor=async_executor)

    await factory(
        connection=target,
        remote_root_path="/data/project with spaces",
        cols=120,
        rows=40,
        env={},
    )

    assert async_executor.connections == [(jump, 10)]
    command, options = async_executor.client.created[0]
    assert shlex.split(command) == [
        "ssh",
        "-p",
        "2222",
        "-tt",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "--",
        "alice@cluster.example.org",
        "cd '/data/project with spaces' && exec \"${SHELL:-/bin/sh}\" -i",
    ]
    assert options == {
        "request_pty": True,
        "term_type": "xterm-256color",
        "term_size": (120, 40),
        "encoding": None,
    }


@pytest.mark.asyncio
async def test_remote_terminal_factory_uses_system_ssh_jump_for_outer_transport(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    def fake_spawn_pty_process(**kwargs):
        captured.update(kwargs)
        return FakeRemoteTerminalTransport()

    monkeypatch.setattr(
        "app.services.terminal_service._spawn_pty_process",
        fake_spawn_pty_process,
    )
    jump = RemoteConnectionConfig(
        id="jump-1",
        name="Bastion",
        host="bastion.example.org",
        username="jump-user",
        key_path="/keys/bastion_ed25519",
    )
    target = RemoteConnectionConfig(
        id="target-1",
        name="Cluster",
        host="cluster.example.org",
        username="alice",
        ssh_config_path="/home/jump-user/.ssh/config",
        jump_connection=jump,
    )
    factory = DefaultRemoteTerminalFactory()

    await factory(
        connection=target,
        remote_root_path="/data/project",
        cols=100,
        rows=30,
        env={"TERM": "xterm-256color"},
    )

    argv = captured["command"]
    assert isinstance(argv, list)
    assert argv[:-1] == [
        "ssh",
        "-i",
        "/keys/bastion_ed25519",
        "-tt",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "--",
        "jump-user@bastion.example.org",
    ]
    assert shlex.split(argv[-1]) == [
        "ssh",
        "-F",
        "/home/jump-user/.ssh/config",
        "-tt",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "--",
        "alice@cluster.example.org",
        'cd /data/project && exec "${SHELL:-/bin/sh}" -i',
    ]
    assert captured["env"] == {"TERM": "xterm-256color"}
    assert captured["cols"] == 100
    assert captured["rows"] == 30


@pytest.mark.asyncio
async def test_remote_terminal_factory_rejects_nested_jump_connections():
    nested_jump = RemoteConnectionConfig(
        id="nested-jump",
        name="Nested bastion",
        host="nested.example.org",
    )
    jump = RemoteConnectionConfig(
        id="jump-1",
        name="Bastion",
        host="bastion.example.org",
        jump_connection=nested_jump,
    )
    target = RemoteConnectionConfig(
        id="target-1",
        name="Cluster",
        host="cluster.example.org",
        jump_connection=jump,
    )

    with pytest.raises(BadRequestError, match="Nested jump connections"):
        await DefaultRemoteTerminalFactory()(
            connection=target,
            remote_root_path="/data/project",
            cols=80,
            rows=24,
            env={},
        )


@pytest.mark.asyncio
async def test_terminal_session_manager_reuses_project_session(tmp_path: Path):
    manager = TerminalSessionManager(shell="/bin/sh", idle_timeout_seconds=30)
    first = None

    try:
        first = await manager.create_or_get(project_id="project-1", root_path=tmp_path)
        second = await manager.create_or_get(project_id="project-1", root_path=tmp_path)

        assert second.id == first.id
        assert second.cwd == str(tmp_path.resolve())
    finally:
        if first is not None:
            await manager.close_session(first.id)
        await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_streams_output_and_reports_cwd(tmp_path: Path):
    manager = TerminalSessionManager(shell="/bin/sh", idle_timeout_seconds=30)
    session = await manager.create_or_get(project_id="project-2", root_path=tmp_path)
    try:
        queue = await manager.attach(session.id)

        await manager.send_input(session.id, "printf 'hello-terminal\\n'\n")
        output = await _next_message(queue, "output", contains="hello-terminal")
        assert "hello-terminal" in output["data"]

        nested = tmp_path / "nested"
        nested.mkdir()

        await manager.change_directory(session.id, "nested")
        cwd = await _next_message(queue, "cwd")
        assert cwd["cwd"] == str(nested.resolve())
    finally:
        await manager.close_session(session.id)
        await manager.shutdown()


@pytest.mark.asyncio
async def test_remote_session_creation_does_not_block_existing_session_attach(
    tmp_path: Path,
):
    factory_started = asyncio.Event()
    release_factory = asyncio.Event()
    transport = FakeRemoteTerminalTransport()

    async def slow_remote_factory(**_kwargs):
        factory_started.set()
        await release_factory.wait()
        return transport

    manager = TerminalSessionManager(
        shell="/bin/sh",
        idle_timeout_seconds=30,
        remote_terminal_factory=slow_remote_factory,
    )
    local_session = await manager.create_or_get(
        project_id="project-local", root_path=tmp_path
    )
    remote_task = asyncio.create_task(
        manager.create_or_get_remote(
            project_id="project-remote-slow",
            connection=RemoteConnectionConfig(
                id="conn-1",
                name="Phoenix login",
                host="login.example.org",
                username="alice",
            ),
            remote_root_path="/data/phoenix",
            target_label="remote · Phoenix login",
        )
    )

    try:
        await asyncio.wait_for(factory_started.wait(), timeout=1)
        queue = await asyncio.wait_for(manager.attach(local_session.id), timeout=0.2)
        ready = await _next_message(queue, "ready")
        assert ready["session"]["id"] == local_session.id

        release_factory.set()
        await asyncio.wait_for(remote_task, timeout=1)
    finally:
        if not remote_task.done():
            remote_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await remote_task
        await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_streams_remote_output_and_controls_remote_pty():
    transport = FakeRemoteTerminalTransport()
    created: list[dict] = []

    async def fake_remote_factory(**kwargs):
        created.append(kwargs)
        return transport

    manager = TerminalSessionManager(
        shell="/bin/sh",
        idle_timeout_seconds=30,
        remote_terminal_factory=fake_remote_factory,
    )
    connection = RemoteConnectionConfig(
        id="conn-1",
        name="Phoenix login",
        host="login.example.org",
        username="alice",
    )
    session = await manager.create_or_get_remote(
        project_id="project-remote",
        connection=connection,
        remote_root_path="/data/phoenix",
        target_label="remote · Phoenix login",
    )

    try:
        assert session.status == "running"
        assert session.target_type == "remote"
        assert session.target_label == "remote · Phoenix login"
        assert session.remote_connection_id == "conn-1"
        assert session.cwd == "/data/phoenix"
        assert created[0]["connection"] == connection
        assert created[0]["remote_root_path"] == "/data/phoenix"

        queue = await manager.attach(session.id)
        ready = await _next_message(queue, "ready")
        assert ready["session"]["status"] == "running"
        cwd = await _next_message(queue, "cwd")
        assert cwd == {"type": "cwd", "cwd": "/data/phoenix"}

        transport.feed(b"hello-remote\n")
        output = await _next_message(queue, "output", contains="hello-remote")
        assert output["data"] == "hello-remote\n"

        await manager.send_input(session.id, "pwd\n")
        await manager.resize(session.id, cols=100, rows=30)
        await manager.change_directory(session.id, "runs/run-1")
        changed = await _next_message(queue, "cwd")

        assert transport.writes == [
            b"pwd\n",
            b"cd /data/phoenix/runs/run-1\n",
        ]
        assert transport.resizes == [(100, 30)]
        assert changed == {"type": "cwd", "cwd": "/data/phoenix/runs/run-1"}
    finally:
        await manager.close_session(session.id)
        await manager.shutdown()

    assert transport.terminated is True


@pytest.mark.asyncio
async def test_remote_session_creation_closes_losing_race_transport():
    release_factory = asyncio.Event()
    transports: list[FakeRemoteTerminalTransport] = []

    async def racing_remote_factory(**_kwargs):
        transport = FakeRemoteTerminalTransport()
        transports.append(transport)
        await release_factory.wait()
        return transport

    manager = TerminalSessionManager(
        shell="/bin/sh",
        idle_timeout_seconds=30,
        remote_terminal_factory=racing_remote_factory,
        transport_shutdown_timeout_seconds=0.05,
    )
    connection = RemoteConnectionConfig(
        id="conn-1",
        name="Phoenix login",
        host="login.example.org",
        username="alice",
    )
    first_task = asyncio.create_task(
        manager.create_or_get_remote(
            project_id="project-remote-race",
            connection=connection,
            remote_root_path="/data/phoenix",
            target_label="remote · Phoenix login",
        )
    )
    second_task = asyncio.create_task(
        manager.create_or_get_remote(
            project_id="project-remote-race",
            connection=connection,
            remote_root_path="/data/phoenix",
            target_label="remote · Phoenix login",
        )
    )

    try:
        deadline = asyncio.get_running_loop().time() + 1
        while len(transports) < 2 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0)
        assert len(transports) == 2

        release_factory.set()
        first, second = await asyncio.gather(first_task, second_task)

        assert second.id == first.id
        assert sum(transport.terminated for transport in transports) == 1
    finally:
        for task in (first_task, second_task):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_close_bounds_hung_remote_terminate():
    transport = HangingTerminateRemoteTerminalTransport()

    async def fake_remote_factory(**_kwargs):
        return transport

    manager = TerminalSessionManager(
        shell="/bin/sh",
        idle_timeout_seconds=30,
        remote_terminal_factory=fake_remote_factory,
        transport_shutdown_timeout_seconds=0.01,
    )
    session = await manager.create_or_get_remote(
        project_id="project-remote-hung-close",
        connection=RemoteConnectionConfig(
            id="conn-1",
            name="Phoenix login",
            host="login.example.org",
            username="alice",
        ),
        remote_root_path="/data/phoenix",
        target_label="remote · Phoenix login",
    )

    closed = await asyncio.wait_for(manager.close_session(session.id), timeout=0.5)

    assert closed is True
    await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_rejects_remote_chdir_outside_root():
    transport = FakeRemoteTerminalTransport()

    async def fake_remote_factory(**_kwargs):
        return transport

    manager = TerminalSessionManager(
        shell="/bin/sh",
        idle_timeout_seconds=30,
        remote_terminal_factory=fake_remote_factory,
    )
    session = await manager.create_or_get_remote(
        project_id="project-remote-escape",
        connection=RemoteConnectionConfig(
            id="conn-1",
            name="Phoenix login",
            host="login.example.org",
            username="alice",
        ),
        remote_root_path="/data/phoenix",
        target_label="remote · Phoenix login",
    )

    try:
        with pytest.raises(PermissionError):
            await manager.change_directory(session.id, "../escape")
        with pytest.raises(PermissionError):
            await manager.change_directory(session.id, "/data/phoenix/runs")
    finally:
        await manager.close_session(session.id)
        await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_replays_initial_output_to_late_subscribers(
    tmp_path: Path,
):
    shell_script = tmp_path / "prompt-shell.sh"
    shell_script.write_text(
        "#!/bin/sh\nprintf 'bpiper/projects/demo main\\n❯ '\nexec /bin/sh\n"
    )
    shell_script.chmod(0o755)

    manager = TerminalSessionManager(shell=str(shell_script), idle_timeout_seconds=30)
    session = await manager.create_or_get(
        project_id="project-prompt", root_path=tmp_path
    )

    try:
        await asyncio.sleep(0.2)
        queue = await manager.attach(session.id)

        output = await _next_message(
            queue, "output", contains="bpiper/projects/demo main"
        )
        data = output["data"]
        for _ in range(4):
            if "❯" in data:
                break
            data += (await _next_message(queue, "output"))["data"]
        assert "❯" in data
    finally:
        await manager.close_session(session.id)
        await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_rejects_paths_outside_project_root(
    tmp_path: Path,
):
    manager = TerminalSessionManager(shell="/bin/sh", idle_timeout_seconds=30)
    session = await manager.create_or_get(project_id="project-3", root_path=tmp_path)
    try:
        with pytest.raises(PermissionError):
            await manager.change_directory(session.id, "../escape")
    finally:
        await manager.close_session(session.id)
        await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_rejects_absolute_chdir_paths(
    tmp_path: Path,
):
    manager = TerminalSessionManager(shell="/bin/sh", idle_timeout_seconds=30)
    session = await manager.create_or_get(
        project_id="project-absolute", root_path=tmp_path
    )
    try:
        with pytest.raises(PermissionError):
            await manager.change_directory(session.id, str(tmp_path.resolve()))
    finally:
        await manager.close_session(session.id)
        await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_evicts_exited_sessions(tmp_path: Path):
    manager = TerminalSessionManager(shell="/bin/sh", idle_timeout_seconds=30)
    session = await manager.create_or_get(project_id="project-4", root_path=tmp_path)
    queue = await manager.attach(session.id)

    try:
        await manager.send_input(session.id, "exit\n")
        await _next_message(queue, "exit")

        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline:
            if (
                session.id not in manager._sessions_by_id
                and manager._project_index.get("project-4") is None
            ):
                break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError("Exited session was not evicted from the manager")
    finally:
        await manager.shutdown()


def test_terminal_session_manager_builds_prompt_sanitized_environment(monkeypatch):
    monkeypatch.setenv("TERM", "screen-256color")
    manager = TerminalSessionManager(shell="/bin/zsh", idle_timeout_seconds=30)

    env = manager._build_terminal_environment()

    assert env["TERM"] == "xterm-256color"
    assert env["VIRTUAL_ENV_DISABLE_PROMPT"] == "1"
    assert env["PYENV_VIRTUALENV_DISABLE_PROMPT"] == "1"
    assert env["CONDA_CHANGEPS1"] == "no"
    assert env["STARSHIP_CONFIG"].endswith("terminal_starship.toml")


def test_terminal_session_manager_spawns_zsh_with_managed_prompt_config(
    monkeypatch, tmp_path: Path
):
    captured: dict[str, object] = {}

    class DummyProcess:
        pid = 12345

        def poll(self):
            return None

    monkeypatch.setattr("app.services.terminal_service.pty.openpty", lambda: (11, 12))
    monkeypatch.setattr("app.services.terminal_service.os.close", lambda _fd: None)

    def fake_popen(*args, **kwargs):
        captured["args"] = args[0]
        captured["env"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        return DummyProcess()

    monkeypatch.setattr("app.services.terminal_service.subprocess.Popen", fake_popen)

    manager = TerminalSessionManager(shell="/bin/zsh", idle_timeout_seconds=30)
    session = manager._spawn_session(
        project_id="project-zsh",
        root_path=tmp_path,
        shell="/bin/zsh",
    )

    assert session.cwd == str(tmp_path)
    assert captured["args"] == ["/bin/zsh", "-i"]
    assert str(captured["cwd"]) == str(tmp_path)

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["ZDOTDIR"].endswith("app/services/terminal_shell")
    assert env["HISTFILE"].endswith(".terminal_history")


def test_terminal_starship_config_disables_git_status_symbols():
    config_path = (
        Path(__file__).resolve().parents[2] / "app/services/terminal_starship.toml"
    )
    config = config_path.read_text()
    git_status_section = config.split("[git_status]", maxsplit=1)[1].split(
        "[character]", maxsplit=1
    )[0]

    assert "[git_status]" in config
    assert "disabled = true" in git_status_section


# --- Phase 2 Fix 11: Terminal environment variable filtering ---


def test_terminal_environment_filters_sensitive_vars(monkeypatch):
    """Sensitive env vars like API keys and secrets must be excluded."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
    monkeypatch.setenv("DATABASE_PASSWORD", "db-pass")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-token")
    monkeypatch.setenv("MY_SECRET", "hidden")
    monkeypatch.setenv("SAFE_VAR", "visible")
    monkeypatch.setenv("PATH", "/usr/bin")

    manager = TerminalSessionManager(shell="/bin/sh")
    env = manager._build_terminal_environment()

    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "DATABASE_PASSWORD" not in env
    assert "GITHUB_TOKEN" not in env
    assert "MY_SECRET" not in env
    assert env.get("SAFE_VAR") == "visible"
    assert env.get("PATH") == "/usr/bin"

from __future__ import annotations

import asyncio

import asyncssh
import pytest

from app.services.remote_execution import (
    AsyncSshRemoteExecutor,
    RemoteConnectionConfig,
    SshRemoteExecutor,
    _TofuHostKeyClient,
)


class _FakeStream:
    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def read(self, _size: int = -1) -> bytes:
        await asyncio.sleep(0)
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class _FakeProcess:
    def __init__(
        self,
        *,
        stdout: list[bytes] | None = None,
        stderr: list[bytes] | None = None,
        returncode: int | None = 0,
        wait_forever: bool = False,
    ) -> None:
        self.stdout = _FakeStream(stdout or [])
        self.stderr = _FakeStream(stderr or [])
        self.returncode = returncode
        self.wait_forever = wait_forever
        self.killed = False

    async def wait(self) -> int:
        if self.wait_forever:
            while not self.killed:
                await asyncio.sleep(0.01)
        if self.returncode is None:
            self.returncode = -9 if self.killed else 0
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class _FakeAsyncSshResult:
    def __init__(self, *, stdout: str = "", stderr: str = "", exit_status: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_status = exit_status


class _FakeAsyncSshClient:
    def __init__(self, result: _FakeAsyncSshResult):
        self.result = result
        self.commands: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def create_process(self, command: str, *, encoding=None):
        assert encoding is None
        self.commands.append(command)
        return _FakeAsyncSshProcess(self.result)


class _FakeAsyncSshProcess:
    def __init__(self, result: _FakeAsyncSshResult):
        self.stdout = _FakeStream([result.stdout.encode()])
        self.stderr = _FakeStream([result.stderr.encode()])
        self.exit_status = result.exit_status
        self.killed = False

    async def wait(self):
        await asyncio.sleep(0)
        return self.exit_status

    def kill(self) -> None:
        self.killed = True
        self.exit_status = -9


@pytest.mark.asyncio
async def test_ssh_executor_builds_open_ssh_argv_without_shell_string():
    captured: dict[str, object] = {}

    async def process_factory(*argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return _FakeProcess(stdout=[b"ok\n"])

    executor = SshRemoteExecutor(process_factory=process_factory)
    connection = RemoteConnectionConfig(
        id="conn-1",
        name="Cluster",
        host="cluster.example.org",
        username="alice",
        port=2222,
        key_path="/Users/alice/.ssh/id_ed25519",
    )

    result = await executor.run(
        connection,
        "hostname",
        timeout_seconds=5,
        output_limit=100,
    )

    assert captured["argv"] == [
        "ssh",
        "-i",
        "/Users/alice/.ssh/id_ed25519",
        "-p",
        "2222",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "--",
        "alice@cluster.example.org",
        "hostname",
    ]
    assert captured["kwargs"]["stdout"] == asyncio.subprocess.PIPE
    assert captured["kwargs"]["stderr"] == asyncio.subprocess.PIPE
    assert result.exit_code == 0
    assert result.stdout == "ok\n"


@pytest.mark.asyncio
async def test_ssh_executor_uses_asyncssh_for_password_connections():
    captured: dict[str, object] = {}
    client = _FakeAsyncSshClient(_FakeAsyncSshResult(stdout="ok\n"))

    def connect_factory(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return client

    executor = SshRemoteExecutor(
        async_executor=AsyncSshRemoteExecutor(connect_factory=connect_factory)
    )
    connection = RemoteConnectionConfig(
        id="conn-1",
        name="Cluster",
        host="cluster.example.org",
        username="alice",
        port=2222,
        password="secret",
    )

    result = await executor.run(
        connection,
        "hostname",
        timeout_seconds=5,
        output_limit=100,
    )

    assert captured["args"] == ("cluster.example.org",)
    assert captured["kwargs"]["username"] == "alice"
    assert captured["kwargs"]["password"] == "secret"
    assert captured["kwargs"]["port"] == 2222
    assert captured["kwargs"]["known_hosts"] is not None
    assert captured["kwargs"]["server_host_key_algs"] == "default"
    assert captured["kwargs"]["client_factory"] is not None
    assert client.commands == ["hostname"]
    assert result.exit_code == 0
    assert result.stdout == "ok\n"


def test_asyncssh_tofu_host_key_client_pins_first_key(tmp_path):
    key = asyncssh.generate_private_key("ssh-ed25519")
    known_hosts_path = tmp_path / "ssh_known_hosts.json"
    client = _TofuHostKeyClient(
        host="cluster.example.org",
        port=2222,
        known_hosts_path=known_hosts_path,
    )

    assert client.validate_host_public_key("cluster.example.org", "", 2222, key) is True

    second_client = _TofuHostKeyClient(
        host="cluster.example.org",
        port=2222,
        known_hosts_path=known_hosts_path,
    )
    assert (
        second_client.validate_host_public_key("cluster.example.org", "", 2222, key)
        is True
    )


def test_asyncssh_tofu_host_key_client_rejects_changed_key(tmp_path):
    first_key = asyncssh.generate_private_key("ssh-ed25519")
    second_key = asyncssh.generate_private_key("ssh-ed25519")
    known_hosts_path = tmp_path / "ssh_known_hosts.json"
    client = _TofuHostKeyClient(
        host="cluster.example.org",
        port=2222,
        known_hosts_path=known_hosts_path,
    )

    assert client.validate_host_public_key("cluster.example.org", "", 2222, first_key)
    assert not client.validate_host_public_key(
        "cluster.example.org",
        "",
        2222,
        second_key,
    )


@pytest.mark.asyncio
async def test_ssh_config_alias_is_used_as_exact_target_without_user_or_port():
    captured: dict[str, object] = {}

    async def process_factory(*argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return _FakeProcess(stdout=[b"ok\n"])

    executor = SshRemoteExecutor(process_factory=process_factory)
    connection = RemoteConnectionConfig(
        id="conn-1",
        name="Cluster",
        host="cluster.example.org",
        username="alice",
        port=2222,
        ssh_alias="cluster-login",
        ssh_config_path="/Users/alice/.ssh/config",
    )

    await executor.run(
        connection,
        "hostname",
        timeout_seconds=5,
        output_limit=100,
    )

    assert captured["argv"] == [
        "ssh",
        "-F",
        "/Users/alice/.ssh/config",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "--",
        "cluster-login",
        "hostname",
    ]


def test_ssh_executor_builds_interactive_pty_argv():
    executor = SshRemoteExecutor()
    connection = RemoteConnectionConfig(
        id="conn-1",
        name="Cluster",
        host="cluster.example.org",
        username="alice",
        port=2222,
        key_path="/Users/alice/.ssh/id_ed25519",
    )

    argv = executor.build_interactive_argv(
        connection,
        'cd /data/project && exec "${SHELL:-/bin/sh}" -i',
        connect_timeout_seconds=10,
    )

    assert argv == [
        "ssh",
        "-i",
        "/Users/alice/.ssh/id_ed25519",
        "-p",
        "2222",
        "-tt",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "--",
        "alice@cluster.example.org",
        'cd /data/project && exec "${SHELL:-/bin/sh}" -i',
    ]


@pytest.mark.asyncio
async def test_ssh_executor_truncates_streams_and_marks_result():
    async def process_factory(*_argv, **_kwargs):
        return _FakeProcess(stdout=[b"abcdef"], stderr=[b"uvwxyz"])

    executor = SshRemoteExecutor(process_factory=process_factory)

    result = await executor.run(
        RemoteConnectionConfig(id="conn-1", name="Cluster", host="cluster"),
        "cat big.txt",
        timeout_seconds=5,
        output_limit=3,
    )

    assert result.stdout == "abc"
    assert result.stderr == "uvw"
    assert result.truncated is True
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True


@pytest.mark.asyncio
async def test_ssh_executor_returns_timeout_result_and_kills_process():
    process = _FakeProcess(stdout=[b"partial"], returncode=None, wait_forever=True)

    async def process_factory(*_argv, **_kwargs):
        return process

    executor = SshRemoteExecutor(process_factory=process_factory)

    result = await executor.run(
        RemoteConnectionConfig(id="conn-1", name="Cluster", host="cluster"),
        "sleep 60",
        timeout_seconds=1,
        output_limit=100,
    )

    assert process.killed is True
    assert result.exit_code == -9
    assert result.timed_out is True
    assert result.stdout == "partial"
    assert result.stderr == ""


@pytest.mark.asyncio
async def test_ssh_executor_streams_stdout_stderr_and_exit_frames():
    async def process_factory(*_argv, **_kwargs):
        return _FakeProcess(
            stdout=[b"hello\n", b"world\n"],
            stderr=[b"warn\n"],
            returncode=7,
        )

    executor = SshRemoteExecutor(process_factory=process_factory)

    frames = [
        frame
        async for frame in executor.stream(
            RemoteConnectionConfig(id="conn-1", name="Cluster", host="cluster"),
            "tail -f run.log",
            timeout_seconds=5,
            output_limit=100,
        )
    ]

    assert [frame.type for frame in frames] == ["stdout", "stderr", "stdout", "exit"]
    assert frames[0].data == "hello\n"
    assert frames[1].data == "warn\n"
    assert frames[2].data == "world\n"
    assert frames[3].exit_code == 7


@pytest.mark.asyncio
async def test_ssh_executor_stream_timeout_kills_quiet_process():
    process = _FakeProcess(returncode=None, wait_forever=True)

    async def process_factory(*_argv, **_kwargs):
        return process

    executor = SshRemoteExecutor(process_factory=process_factory)

    frames = [
        frame
        async for frame in executor.stream(
            RemoteConnectionConfig(id="conn-1", name="Cluster", host="cluster"),
            "sleep 60",
            timeout_seconds=1,
            output_limit=100,
        )
    ]

    assert process.killed is True
    assert len(frames) == 1
    assert frames[0].type == "exit"
    assert frames[0].exit_code == -9
    assert frames[0].timed_out is True


@pytest.mark.asyncio
async def test_ssh_executor_stream_close_kills_remote_process():
    process = _FakeProcess(stdout=[b"hello\n"], returncode=None, wait_forever=True)

    async def process_factory(*_argv, **_kwargs):
        return process

    executor = SshRemoteExecutor(process_factory=process_factory)
    stream = executor.stream(
        RemoteConnectionConfig(id="conn-1", name="Cluster", host="cluster"),
        "tail -f run.log",
        timeout_seconds=60,
        output_limit=100,
    )

    first = await stream.__anext__()
    assert first.type == "stdout"
    await stream.aclose()

    assert process.killed is True


@pytest.mark.asyncio
async def test_ssh_executor_stream_caps_output():
    async def process_factory(*_argv, **_kwargs):
        return _FakeProcess(stdout=[b"abcdef"], returncode=0)

    executor = SshRemoteExecutor(process_factory=process_factory)

    frames = [
        frame
        async for frame in executor.stream(
            RemoteConnectionConfig(id="conn-1", name="Cluster", host="cluster"),
            "cat big.log",
            timeout_seconds=5,
            output_limit=3,
        )
    ]

    assert [frame.type for frame in frames] == ["stdout", "truncated", "exit"]
    assert frames[0].data == "abc"
    assert frames[1].data == "remote output truncated after 3 bytes"


@pytest.mark.asyncio
async def test_ssh_executor_stream_truncation_kills_process():
    process = _FakeProcess(stdout=[b"abcdef"], returncode=None, wait_forever=True)

    async def process_factory(*_argv, **_kwargs):
        return process

    executor = SshRemoteExecutor(process_factory=process_factory)

    frames = [
        frame
        async for frame in executor.stream(
            RemoteConnectionConfig(id="conn-1", name="Cluster", host="cluster"),
            "yes",
            timeout_seconds=60,
            output_limit=3,
        )
    ]

    assert process.killed is True
    assert [frame.type for frame in frames] == ["stdout", "truncated", "exit"]
    assert frames[-1].exit_code == -9

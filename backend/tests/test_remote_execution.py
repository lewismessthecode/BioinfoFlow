from __future__ import annotations

import asyncio
import json
import multiprocessing
import shlex
from pathlib import Path

import asyncssh
import pytest

from app.services.remote_execution import (
    AsyncSshRemoteExecutor,
    RemoteConnectionConfig,
    SshRemoteExecutor,
    _TofuHostKeyClient,
    build_inner_ssh_command,
)
from app.utils.exceptions import BadRequestError


def _validate_tofu_host_in_process(
    known_hosts_path: str,
    host: str,
    port: int,
    private_key: bytes,
    start_barrier,
    results,
) -> None:
    try:
        key = asyncssh.import_private_key(private_key)
        client = _TofuHostKeyClient(
            host=host,
            port=port,
            known_hosts_path=Path(known_hosts_path),
        )
        start_barrier.wait(timeout=10)
        accepted = client.validate_host_public_key(host, "", port, key)
        results.put(
            {
                "record_key": f"{host}:{port}",
                "public_key": key.export_public_key("openssh").decode("utf-8").strip(),
                "accepted": accepted,
                "error": None,
            }
        )
    except BaseException as exc:  # noqa: BLE001 - child failure must reach parent
        results.put(
            {
                "record_key": f"{host}:{port}",
                "public_key": None,
                "accepted": False,
                "error": repr(exc),
            }
        )


def _run_concurrent_tofu_validations(known_hosts_path, attempts):
    context = multiprocessing.get_context("spawn")
    start_barrier = context.Barrier(len(attempts) + 1)
    results = context.Queue()
    processes = [
        context.Process(
            target=_validate_tofu_host_in_process,
            args=(
                str(known_hosts_path),
                host,
                port,
                private_key,
                start_barrier,
                results,
            ),
        )
        for host, port, private_key in attempts
    ]
    try:
        for process in processes:
            process.start()
        start_barrier.wait(timeout=10)
        payloads = [results.get(timeout=20) for _ in processes]
        for process in processes:
            process.join(timeout=20)
        assert all(process.exitcode == 0 for process in processes)
        return payloads
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        results.close()
        results.join_thread()


def _seed_large_known_hosts(path) -> dict[str, str]:
    records = {
        f"seed-{index}.example.org:22": "ssh-ed25519 seeded-public-key"
        for index in range(20_000)
    }
    path.write_text(json.dumps(records, sort_keys=True) + "\n", encoding="utf-8")
    return records


class _FakeStream:
    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def read(self, _size: int = -1) -> bytes:
        await asyncio.sleep(0)
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class _BlockingFakeStream:
    def __init__(self) -> None:
        self.read_started = asyncio.Event()
        self.cancelled = False

    async def read(self, _size: int = -1) -> bytes:
        self.read_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
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
        self.wait_calls = 0
        self.stdin = _FakeStdin()

    async def wait(self) -> int:
        self.wait_calls += 1
        if self.wait_forever:
            while not self.killed:
                await asyncio.sleep(0.01)
        if self.returncode is None:
            self.returncode = -9 if self.killed else 0
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class _FakeStdin:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        self.closed = True


class _FailingDrainStdin(_FakeStdin):
    async def drain(self) -> None:
        await asyncio.sleep(0)
        raise RuntimeError("stdin drain failed")


class _BlockingDrainStdin(_FakeStdin):
    def __init__(self) -> None:
        super().__init__()
        self.drain_started = asyncio.Event()

    async def drain(self) -> None:
        self.drain_started.set()
        await asyncio.Event().wait()


class _WaitFailureProcess(_FakeProcess):
    async def wait(self) -> int:
        self.wait_calls += 1
        if self.wait_calls == 1:
            raise RuntimeError("ssh wait failed")
        if self.returncode is None:
            self.returncode = -9 if self.killed else 0
        return self.returncode


class _FakeAsyncSshResult:
    def __init__(self, *, stdout: str = "", stderr: str = "", exit_status: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_status = exit_status


class _FakeAsyncSshClient:
    def __init__(
        self,
        result: _FakeAsyncSshResult,
        *,
        process: _FakeAsyncSshProcess | None = None,
    ):
        self.result = result
        self.process = process
        self.commands: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def create_process(self, command: str, *, encoding=None):
        assert encoding is None
        self.commands.append(command)
        return self.process or _FakeAsyncSshProcess(self.result)


class _FakeAsyncSshProcess:
    def __init__(self, result: _FakeAsyncSshResult):
        self.stdout = _FakeStream([result.stdout.encode()])
        self.stderr = _FakeStream([result.stderr.encode()])
        self.exit_status = result.exit_status
        self.killed = False
        self.wait_calls = 0
        self.wait_forever = False
        self.stdin = _FakeStdin()

    async def wait(self):
        self.wait_calls += 1
        if self.wait_forever:
            while not self.killed:
                await asyncio.sleep(0.01)
        else:
            await asyncio.sleep(0)
        return self.exit_status

    def kill(self) -> None:
        self.killed = True
        self.exit_status = -9


class _AsyncWaitFailureProcess(_FakeAsyncSshProcess):
    async def wait(self):
        self.wait_calls += 1
        if self.wait_calls == 1:
            raise RuntimeError("asyncssh wait failed")
        return self.exit_status


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
async def test_ssh_executor_sends_secret_over_stdin_not_argv():
    captured: dict[str, object] = {}

    async def process_factory(*argv, **kwargs):
        process = _FakeProcess(stdout=[b"ok\n"])
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        captured["process"] = process
        return process

    executor = SshRemoteExecutor(process_factory=process_factory)
    connection = RemoteConnectionConfig(
        id="conn-1",
        name="Cluster",
        host="cluster.example.org",
        username="alice",
    )

    result = await executor.run_with_stdin(
        connection,
        "IFS= read -r BIOFLOW_AGENT_TOKEN && export BIOFLOW_AGENT_TOKEN && bif system health",
        stdin_data=b"short-lived-secret\n",
        timeout_seconds=5,
        output_limit=100,
    )

    assert "short-lived-secret" not in " ".join(captured["argv"])
    assert captured["kwargs"]["stdin"] == asyncio.subprocess.PIPE
    process = captured["process"]
    assert bytes(process.stdin.data) == b"short-lived-secret\n"
    assert process.stdin.closed is True
    assert result.stdout == "ok\n"


@pytest.mark.asyncio
async def test_ssh_executor_stdin_failure_reaps_process_and_readers():
    process = _FakeProcess(returncode=None, wait_forever=True)
    process.stdin = _FailingDrainStdin()
    stdout = _BlockingFakeStream()
    stderr = _BlockingFakeStream()
    process.stdout = stdout
    process.stderr = stderr

    async def process_factory(*_argv, **_kwargs):
        return process

    executor = SshRemoteExecutor(process_factory=process_factory)
    existing_tasks = set(asyncio.all_tasks())

    with pytest.raises(RuntimeError, match="stdin drain failed"):
        await executor.run_with_stdin(
            RemoteConnectionConfig(id="conn-1", name="Cluster", host="cluster"),
            "bif system health",
            stdin_data=b"secret\n",
            timeout_seconds=5,
            output_limit=100,
        )

    leaked_tasks = [
        task
        for task in asyncio.all_tasks()
        if task not in existing_tasks and not task.done()
    ]
    try:
        assert process.killed is True
        assert process.wait_calls == 1
        assert stdout.cancelled is True
        assert stderr.cancelled is True
        assert leaked_tasks == []
    finally:
        process.kill()
        for task in leaked_tasks:
            task.cancel()
        await asyncio.gather(*leaked_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_ssh_executor_wait_failure_reaps_process_and_readers():
    process = _WaitFailureProcess(returncode=None)
    stdout = _BlockingFakeStream()
    stderr = _BlockingFakeStream()
    process.stdout = stdout
    process.stderr = stderr

    async def process_factory(*_argv, **_kwargs):
        return process

    with pytest.raises(RuntimeError, match="ssh wait failed"):
        await SshRemoteExecutor(process_factory=process_factory).run_with_stdin(
            RemoteConnectionConfig(id="conn-1", name="Cluster", host="cluster"),
            "bif system health",
            stdin_data=b"secret\n",
            timeout_seconds=5,
            output_limit=100,
        )

    assert process.killed is True
    assert process.wait_calls == 2
    assert stdout.cancelled is True
    assert stderr.cancelled is True


@pytest.mark.asyncio
async def test_ssh_executor_cancellation_during_stdin_reaps_process_and_readers():
    process = _FakeProcess(returncode=None, wait_forever=True)
    stdin = _BlockingDrainStdin()
    stdout = _BlockingFakeStream()
    stderr = _BlockingFakeStream()
    process.stdin = stdin
    process.stdout = stdout
    process.stderr = stderr

    async def process_factory(*_argv, **_kwargs):
        return process

    task = asyncio.create_task(
        SshRemoteExecutor(process_factory=process_factory).run_with_stdin(
            RemoteConnectionConfig(id="conn-1", name="Cluster", host="cluster"),
            "bif system health",
            stdin_data=b"secret\n",
            timeout_seconds=60,
            output_limit=100,
        )
    )
    await stdin.drain_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.killed is True
    assert process.wait_calls == 1
    assert stdout.cancelled is True
    assert stderr.cancelled is True


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


@pytest.mark.asyncio
async def test_asyncssh_executor_stdin_failure_reaps_process_and_readers():
    process = _FakeAsyncSshProcess(_FakeAsyncSshResult())
    process.exit_status = None
    process.stdin = _FailingDrainStdin()
    stdout = _BlockingFakeStream()
    stderr = _BlockingFakeStream()
    process.stdout = stdout
    process.stderr = stderr
    client = _FakeAsyncSshClient(_FakeAsyncSshResult(), process=process)
    executor = AsyncSshRemoteExecutor(connect_factory=lambda *_a, **_kw: client)
    existing_tasks = set(asyncio.all_tasks())

    with pytest.raises(RuntimeError, match="stdin drain failed"):
        await executor.run_with_stdin(
            RemoteConnectionConfig(
                id="conn-1",
                name="Cluster",
                host="cluster.example.org",
                password="secret",
            ),
            "bif system health",
            stdin_data=b"short-lived-secret\n",
            timeout_seconds=5,
            output_limit=100,
        )

    leaked_tasks = [
        task
        for task in asyncio.all_tasks()
        if task not in existing_tasks and not task.done()
    ]
    try:
        assert process.killed is True
        assert process.wait_calls == 1
        assert stdout.cancelled is True
        assert stderr.cancelled is True
        assert leaked_tasks == []
    finally:
        process.kill()
        for task in leaked_tasks:
            task.cancel()
        await asyncio.gather(*leaked_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_asyncssh_executor_wait_failure_reaps_process_and_readers():
    process = _AsyncWaitFailureProcess(_FakeAsyncSshResult())
    process.exit_status = None
    stdout = _BlockingFakeStream()
    stderr = _BlockingFakeStream()
    process.stdout = stdout
    process.stderr = stderr
    client = _FakeAsyncSshClient(_FakeAsyncSshResult(), process=process)

    with pytest.raises(RuntimeError, match="asyncssh wait failed"):
        await AsyncSshRemoteExecutor(
            connect_factory=lambda *_a, **_kw: client
        ).run_with_stdin(
            RemoteConnectionConfig(
                id="conn-1",
                name="Cluster",
                host="cluster.example.org",
                password="secret",
            ),
            "bif system health",
            stdin_data=b"short-lived-secret\n",
            timeout_seconds=5,
            output_limit=100,
        )

    assert process.killed is True
    assert process.wait_calls == 2
    assert stdout.cancelled is True
    assert stderr.cancelled is True


@pytest.mark.asyncio
async def test_asyncssh_executor_cancellation_reaps_process_and_readers():
    process = _FakeAsyncSshProcess(_FakeAsyncSshResult())
    process.exit_status = None
    process.wait_forever = True
    stdout = _BlockingFakeStream()
    stderr = _BlockingFakeStream()
    process.stdout = stdout
    process.stderr = stderr
    client = _FakeAsyncSshClient(_FakeAsyncSshResult(), process=process)
    task = asyncio.create_task(
        AsyncSshRemoteExecutor(
            connect_factory=lambda *_a, **_kw: client
        ).run_with_stdin(
            RemoteConnectionConfig(
                id="conn-1",
                name="Cluster",
                host="cluster.example.org",
                password="secret",
            ),
            "bif system health",
            stdin_data=b"short-lived-secret\n",
            timeout_seconds=60,
            output_limit=100,
        )
    )
    while process.wait_calls == 0:
        await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.killed is True
    assert process.wait_calls == 2
    assert stdout.cancelled is True
    assert stderr.cancelled is True


@pytest.mark.asyncio
async def test_ssh_executor_routes_through_asyncssh_jump_connection():
    captured: dict[str, object] = {}
    client = _FakeAsyncSshClient(_FakeAsyncSshResult(stdout="phoenix\n"))

    def connect_factory(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return client

    jump = RemoteConnectionConfig(
        id="jump-1",
        name="Bastion",
        host="bastion.example.org",
        username="jump-user",
        password="jump-secret",
    )
    target = RemoteConnectionConfig(
        id="target-1",
        name="Phoenix",
        host="10.32.5.1",
        username="phoenix",
        port=22,
        jump_connection=jump,
    )
    executor = SshRemoteExecutor(
        async_executor=AsyncSshRemoteExecutor(connect_factory=connect_factory)
    )

    result = await executor.run(
        target,
        "hostname",
        timeout_seconds=5,
        output_limit=100,
    )

    assert captured["args"] == ("bastion.example.org",)
    assert captured["kwargs"]["username"] == "jump-user"
    assert captured["kwargs"]["password"] == "jump-secret"
    assert client.commands == [
        "ssh -p 22 -o BatchMode=yes -o ConnectTimeout=5 -- phoenix@10.32.5.1 hostname"
    ]
    assert result.stdout == "phoenix\n"


@pytest.mark.asyncio
async def test_ssh_executor_routes_through_system_ssh_jump_connection():
    captured: dict[str, object] = {}

    async def process_factory(*argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return _FakeProcess(stdout=[b"phoenix\n"])

    jump = RemoteConnectionConfig(
        id="jump-1",
        name="Bastion",
        host="bastion.example.org",
        username="jump-user",
        key_path="/keys/jump",
    )
    target = RemoteConnectionConfig(
        id="target-1",
        name="Phoenix",
        host="10.32.5.1",
        username="phoenix",
        port=22,
        jump_connection=jump,
    )

    result = await SshRemoteExecutor(process_factory=process_factory).run(
        target,
        "hostname",
        timeout_seconds=5,
        output_limit=100,
    )

    assert captured["argv"] == [
        "ssh",
        "-i",
        "/keys/jump",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "--",
        "jump-user@bastion.example.org",
        "ssh -p 22 -o BatchMode=yes -o ConnectTimeout=5 -- phoenix@10.32.5.1 hostname",
    ]
    assert result.stdout == "phoenix\n"


@pytest.mark.asyncio
async def test_ssh_executor_jump_route_keeps_stdin_secret_out_of_commands():
    captured: dict[str, object] = {}

    async def process_factory(*argv, **kwargs):
        process = _FakeProcess(stdout=[b"healthy\n"])
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        captured["process"] = process
        return process

    jump = RemoteConnectionConfig(
        id="jump-1",
        name="Bastion",
        host="bastion.example.org",
        username="jump-user",
        key_path="/keys/jump",
    )
    target = RemoteConnectionConfig(
        id="target-1",
        name="Phoenix",
        host="10.32.5.1",
        username="phoenix",
        port=22,
        jump_connection=jump,
    )
    command = (
        "IFS= read -r BIOFLOW_AGENT_TOKEN && export BIOFLOW_AGENT_TOKEN "
        "&& bif system health"
    )
    secret = b"short-lived-secret\n"

    result = await SshRemoteExecutor(process_factory=process_factory).run_with_stdin(
        target,
        command,
        stdin_data=secret,
        timeout_seconds=5,
        output_limit=100,
    )

    outer_argv = captured["argv"]
    inner_command = outer_argv[-1]
    assert "short-lived-secret" not in " ".join(outer_argv)
    assert "short-lived-secret" not in inner_command
    assert shlex.split(inner_command)[-1] == command
    process = captured["process"]
    assert bytes(process.stdin.data) == secret
    assert process.stdin.closed is True
    assert result.stdout == "healthy\n"


@pytest.mark.asyncio
async def test_ssh_executor_stream_routes_through_jump_and_preserves_frames():
    client = _FakeAsyncSshClient(
        _FakeAsyncSshResult(stdout="out\n", stderr="warn\n", exit_status=7)
    )
    jump = RemoteConnectionConfig(
        id="jump-1",
        name="Bastion",
        host="bastion.example.org",
        username="jump-user",
        password="jump-secret",
    )
    target = RemoteConnectionConfig(
        id="target-1",
        name="Phoenix",
        host="10.32.5.1",
        username="phoenix",
        jump_connection=jump,
    )
    executor = SshRemoteExecutor(
        async_executor=AsyncSshRemoteExecutor(connect_factory=lambda *_a, **_kw: client)
    )

    frames = [
        frame
        async for frame in executor.stream(
            target,
            "hostname",
            timeout_seconds=5,
            output_limit=100,
        )
    ]

    assert [(frame.type, frame.data, frame.exit_code) for frame in frames] == [
        ("stdout", "out\n", None),
        ("stderr", "warn\n", None),
        ("exit", None, 7),
    ]
    assert client.commands == [
        "ssh -o BatchMode=yes -o ConnectTimeout=5 -- phoenix@10.32.5.1 hostname"
    ]


@pytest.mark.parametrize(
    "command",
    [
        "printf hello world",
        "printf '%s' \"quoted value\"",
        "printf safe; touch /tmp/must-not-run-locally",
        "printf $(touch /tmp/must-not-run-locally)",
        "printf '$(touch /tmp/must-not-run-locally)'",
    ],
)
def test_inner_ssh_command_round_trips_adversarial_remote_commands(command):
    connection = RemoteConnectionConfig(
        id="target-1",
        name="Dash target",
        host="-internal.example.org",
        username="-phoenix",
        port=2222,
    )

    inner_command = build_inner_ssh_command(
        connection,
        command,
        connect_timeout_seconds=5,
    )

    assert shlex.split(inner_command) == [
        "ssh",
        "-p",
        "2222",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "--",
        "-phoenix@-internal.example.org",
        command,
    ]


@pytest.mark.asyncio
async def test_ssh_executor_jump_stream_preserves_truncation_frame():
    client = _FakeAsyncSshClient(_FakeAsyncSshResult(stdout="abcdef"))
    target = RemoteConnectionConfig(
        id="target-1",
        name="Phoenix",
        host="10.32.5.1",
        username="phoenix",
        jump_connection=RemoteConnectionConfig(
            id="jump-1",
            name="Bastion",
            host="bastion.example.org",
            password="jump-secret",
        ),
    )
    executor = SshRemoteExecutor(
        async_executor=AsyncSshRemoteExecutor(connect_factory=lambda *_a, **_kw: client)
    )

    frames = [
        frame
        async for frame in executor.stream(
            target,
            "hostname",
            timeout_seconds=5,
            output_limit=3,
        )
    ]

    assert [(frame.type, frame.data) for frame in frames] == [
        ("stdout", "abc"),
        ("truncated", "remote output truncated after 3 bytes"),
        ("exit", None),
    ]


@pytest.mark.asyncio
async def test_ssh_executor_rejects_nested_runtime_jump_config():
    direct = RemoteConnectionConfig(id="direct", name="Direct", host="direct")
    nested = RemoteConnectionConfig(
        id="nested", name="Nested", host="nested", jump_connection=direct
    )
    target = RemoteConnectionConfig(
        id="target", name="Target", host="target", jump_connection=nested
    )

    with pytest.raises(BadRequestError, match="Nested jump"):
        await SshRemoteExecutor().run(
            target,
            "hostname",
            timeout_seconds=5,
            output_limit=100,
        )


@pytest.mark.asyncio
async def test_ssh_executor_rejects_empty_jump_command():
    target = RemoteConnectionConfig(
        id="target",
        name="Target",
        host="target",
        jump_connection=RemoteConnectionConfig(id="jump", name="Jump", host="jump"),
    )

    with pytest.raises(BadRequestError, match="non-empty"):
        await SshRemoteExecutor().run(
            target,
            "  ",
            timeout_seconds=5,
            output_limit=100,
        )


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


def test_asyncssh_tofu_host_key_client_fails_closed_on_invalid_json(tmp_path):
    key = asyncssh.generate_private_key("ssh-ed25519")
    known_hosts_path = tmp_path / "ssh_known_hosts.json"
    invalid_json = "{not valid json\n"
    known_hosts_path.write_text(invalid_json, encoding="utf-8")
    client = _TofuHostKeyClient(
        host="cluster.example.org",
        port=2222,
        known_hosts_path=known_hosts_path,
    )

    with pytest.raises(RuntimeError, match="invalid JSON"):
        client.validate_host_public_key("cluster.example.org", "", 2222, key)

    assert known_hosts_path.read_text(encoding="utf-8") == invalid_json


@pytest.mark.parametrize(
    "invalid_structure",
    [
        "[]\n",
        '{"cluster.example.org:2222": 42}\n',
    ],
)
def test_asyncssh_tofu_host_key_client_fails_closed_on_invalid_structure(
    tmp_path,
    invalid_structure,
):
    key = asyncssh.generate_private_key("ssh-ed25519")
    known_hosts_path = tmp_path / "ssh_known_hosts.json"
    known_hosts_path.write_text(invalid_structure, encoding="utf-8")
    client = _TofuHostKeyClient(
        host="cluster.example.org",
        port=2222,
        known_hosts_path=known_hosts_path,
    )

    with pytest.raises(RuntimeError, match="invalid structure"):
        client.validate_host_public_key("cluster.example.org", "", 2222, key)

    assert known_hosts_path.read_text(encoding="utf-8") == invalid_structure


def test_asyncssh_tofu_host_key_client_fails_closed_when_registry_cannot_be_read(
    tmp_path,
):
    key = asyncssh.generate_private_key("ssh-ed25519")
    known_hosts_path = tmp_path / "ssh_known_hosts.json"
    known_hosts_path.mkdir()
    client = _TofuHostKeyClient(
        host="cluster.example.org",
        port=2222,
        known_hosts_path=known_hosts_path,
    )

    with pytest.raises(RuntimeError, match="could not be read"):
        client.validate_host_public_key("cluster.example.org", "", 2222, key)

    assert known_hosts_path.is_dir()


def test_asyncssh_tofu_host_key_client_preserves_concurrent_first_hosts(tmp_path):
    known_hosts_path = tmp_path / "ssh_known_hosts.json"
    seeded = _seed_large_known_hosts(known_hosts_path)
    attempts = [
        (
            f"cluster-{index}.example.org",
            2200 + index,
            asyncssh.generate_private_key("ssh-ed25519").export_private_key("openssh"),
        )
        for index in range(4)
    ]

    payloads = _run_concurrent_tofu_validations(known_hosts_path, attempts)

    assert [payload["error"] for payload in payloads] == [None] * len(payloads)
    assert all(payload["accepted"] is True for payload in payloads)
    stored = json.loads(known_hosts_path.read_text(encoding="utf-8"))
    assert all(stored[key] == value for key, value in seeded.items())
    assert all(
        stored[payload["record_key"]] == payload["public_key"] for payload in payloads
    )


def test_asyncssh_tofu_host_key_client_accepts_one_concurrent_key_per_host(tmp_path):
    known_hosts_path = tmp_path / "ssh_known_hosts.json"
    seeded = _seed_large_known_hosts(known_hosts_path)
    attempts = [
        (
            "cluster.example.org",
            2222,
            asyncssh.generate_private_key("ssh-ed25519").export_private_key("openssh"),
        )
        for _ in range(4)
    ]

    payloads = _run_concurrent_tofu_validations(known_hosts_path, attempts)

    assert [payload["error"] for payload in payloads] == [None] * len(payloads)
    accepted = [payload for payload in payloads if payload["accepted"] is True]
    assert len(accepted) == 1
    stored = json.loads(known_hosts_path.read_text(encoding="utf-8"))
    assert all(stored[key] == value for key, value in seeded.items())
    assert stored["cluster.example.org:2222"] == accepted[0]["public_key"]


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
async def test_ssh_executor_stdin_timeout_returns_result_and_reaps_process():
    process = _FakeProcess(stdout=[b"partial"], returncode=None, wait_forever=True)

    async def process_factory(*_argv, **_kwargs):
        return process

    result = await SshRemoteExecutor(process_factory=process_factory).run_with_stdin(
        RemoteConnectionConfig(id="conn-1", name="Cluster", host="cluster"),
        "sleep 60",
        stdin_data=b"secret\n",
        timeout_seconds=1,
        output_limit=100,
    )

    assert process.killed is True
    assert process.wait_calls == 2
    assert result.exit_code == -9
    assert result.timed_out is True
    assert result.stdout == "partial"


@pytest.mark.asyncio
async def test_asyncssh_executor_stdin_timeout_returns_result_and_reaps_process():
    process = _FakeAsyncSshProcess(_FakeAsyncSshResult(stdout="partial"))
    process.exit_status = None
    process.wait_forever = True
    client = _FakeAsyncSshClient(_FakeAsyncSshResult(), process=process)

    result = await AsyncSshRemoteExecutor(
        connect_factory=lambda *_a, **_kw: client
    ).run_with_stdin(
        RemoteConnectionConfig(
            id="conn-1",
            name="Cluster",
            host="cluster.example.org",
            password="secret",
        ),
        "sleep 60",
        stdin_data=b"short-lived-secret\n",
        timeout_seconds=1,
        output_limit=100,
    )

    assert process.killed is True
    assert process.wait_calls == 2
    assert result.exit_code == -9
    assert result.timed_out is True
    assert result.stdout == "partial"


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

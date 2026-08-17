"""Run local agent Bash in a disposable Docker identity without daemon access."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Literal
import uuid

import docker

from app.config import settings
from app.services.agent_harness.sandbox.capability_paths import (
    require_safe_workspace_root,
    sensitive_capability_paths,
)


@dataclass(frozen=True, slots=True)
class ContainerSandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    output_limit_exceeded: bool
    timed_out: bool
    sandbox: dict[str, Any]


class DockerSandboxExecutor:
    """Docker-backed execution boundary used by Compose deployments.

    The backend keeps Docker authority for workflow scheduling, but the agent
    command runs in a fresh container that never receives the daemon socket.
    """

    def __init__(
        self,
        *,
        image: str,
        socket: str | None = None,
        client: docker.DockerClient | None = None,
    ) -> None:
        if not image.strip():
            raise ValueError("sandbox container image is required")
        self.image = image.strip()
        self.socket = socket or settings.docker_socket
        self._client = client

    @classmethod
    def from_settings(cls, source: object | None = None) -> DockerSandboxExecutor | None:
        configured = source or settings
        image = str(getattr(configured, "agent_sandbox_image", "") or "").strip()
        if not image:
            return None
        return cls(
            image=image,
            socket=str(getattr(configured, "docker_socket", settings.docker_socket)),
        )

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.DockerClient(base_url=self.socket)
        return self._client

    async def execute(
        self,
        *,
        argv: list[str],
        cwd: Path,
        workspace_root: Path,
        environment: dict[str, str],
        mode: Literal["read-only", "workspace-write", "danger-full-access"],
        timeout_seconds: int,
        capture_limit: int,
        cancellation: Any | None,
        cwd_inode: int,
        workspace_inode: int,
    ) -> ContainerSandboxResult:
        workspace_root = require_safe_workspace_root(workspace_root)
        read_roots = _container_read_roots()
        cwd_is_identity_mounted = _is_relative_to(cwd, workspace_root) or any(
            _is_relative_to(cwd, root) for root in read_roots
        )
        if not cwd_is_identity_mounted:
            raise RuntimeError(
                "sandbox cwd must be inside an identity-mounted workspace or read root"
            )
        primary_error: BaseException | None = None
        request_path = _write_request(
            argv=argv,
            cwd=cwd,
            workspace_root=workspace_root,
            environment=environment,
            mode=mode,
            timeout_seconds=timeout_seconds,
            capture_limit=capture_limit,
            cwd_inode=cwd_inode,
            workspace_inode=workspace_inode,
        )
        container = None
        try:
            start_task = asyncio.create_task(
                asyncio.to_thread(
                    self._start_container,
                    request_path,
                    workspace_root,
                    mode,
                    read_roots,
                ),
                name="agent-sandbox-container-start",
            )
            try:
                container = await asyncio.shield(start_task)
            except asyncio.CancelledError:
                container = await _finish_container_start(start_task)
                if container is not None:
                    try:
                        await asyncio.to_thread(container.kill)
                    except Exception:
                        pass
                raise
            wait_task = asyncio.create_task(
                asyncio.to_thread(container.wait),
                name="agent-sandbox-container-wait",
            )
            cancelled = asyncio.create_task(_wait_for_cancellation(cancellation))
            try:
                done, _ = await asyncio.wait(
                    {wait_task, cancelled},
                    timeout=timeout_seconds + 10,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancelled in done:
                    await asyncio.to_thread(container.kill)
                    await asyncio.gather(wait_task, return_exceptions=True)
                    raise asyncio.CancelledError
                if wait_task not in done:
                    await asyncio.to_thread(container.kill)
                    await asyncio.gather(wait_task, return_exceptions=True)
                    raise TimeoutError(
                        f"sandbox container timed out after {timeout_seconds}s"
                    )
                wait_result = wait_task.result()
                if (
                    not isinstance(wait_result, dict)
                    or isinstance(wait_result.get("StatusCode"), bool)
                    or not isinstance(wait_result.get("StatusCode"), int)
                ):
                    raise RuntimeError("sandbox container returned an invalid exit status")
                container_status = wait_result["StatusCode"]
            finally:
                cancelled.cancel()
                await asyncio.gather(cancelled, return_exceptions=True)
            stdout = await asyncio.to_thread(
                container.logs,
                stdout=True,
                stderr=False,
            )
            stderr = await asyncio.to_thread(
                container.logs,
                stdout=False,
                stderr=True,
            )
            if container_status != 0:
                detail = (stderr or b"").decode("utf-8", errors="replace").strip()
                suffix = f": {detail[:1000]}" if detail else ""
                raise RuntimeError(
                    f"sandbox container exited with status {container_status}{suffix}"
                )
            return _parse_result(
                stdout or b"",
                stderr or b"",
                expected_mode=mode,
            )
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            try:
                if container is not None:
                    try:
                        await asyncio.to_thread(container.remove, force=True)
                    except Exception:
                        if primary_error is None:
                            raise
            finally:
                request_path.unlink(missing_ok=True)

    def _start_container(
        self,
        request_path: Path,
        workspace_root: Path,
        mode: Literal["read-only", "workspace-write", "danger-full-access"],
        read_roots: tuple[Path, ...],
    ):
        volumes: dict[str, dict[str, str]] = {
            str(request_path): {
                "bind": "/run/bioinfoflow-sandbox/request.json",
                "mode": "ro",
            },
            str(workspace_root): {
                "bind": str(workspace_root),
                "mode": "rw",
            },
        }
        for root in read_roots:
            if root == workspace_root:
                continue
            volumes[str(root)] = {
                "bind": str(root),
                "mode": "ro",
            }
        options: dict[str, Any] = {
            "command": [
                "/app/sandbox_worker/executor.mjs",
                "/run/bioinfoflow-sandbox/request.json",
            ],
            "entrypoint": ["node"],
            "detach": True,
            "environment": {},
            "labels": {
                "bioinfoflow.role": "agent-sandbox",
                "bioinfoflow.execution": uuid.uuid4().hex,
            },
            "volumes": volumes,
            "read_only": mode != "danger-full-access",
            "tmpfs": {"/tmp": "rw,nosuid,nodev,size=256m"},
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
        }
        hostname = os.environ.get("HOSTNAME")
        if hostname and _running_in_container():
            options["network_mode"] = f"container:{hostname}"
        return self.client.containers.run(self._execution_image(), **options)

    def _execution_image(self) -> str:
        if not _running_in_container():
            return self.image
        hostname = os.environ.get("HOSTNAME", "").strip()
        if not hostname:
            raise RuntimeError("sandbox image identity is unavailable")
        backend = self.client.containers.get(hostname)
        configured = self.client.images.get(self.image)
        backend_image = str(getattr(backend.image, "id", "") or "")
        configured_image = str(getattr(configured, "id", "") or "")
        if not backend_image or configured_image != backend_image:
            raise RuntimeError(
                "configured sandbox image does not match the running backend image"
            )
        return backend_image


def _write_request(
    *,
    argv: list[str],
    cwd: Path,
    workspace_root: Path,
    environment: dict[str, str],
    mode: str,
    timeout_seconds: int,
    capture_limit: int,
    cwd_inode: int | None,
    workspace_inode: int,
) -> Path:
    request_root = Path(settings.state_root) / "agent_harness" / "sandbox_requests"
    request_root.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(
        prefix="request-",
        suffix=".json",
        dir=request_root,
    )
    path = Path(raw_path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": 1,
                    "argv": argv,
                    "cwd": str(cwd),
                    "environment": environment,
                    "mode": mode,
                    "workspace_root": str(workspace_root),
                    "protected_endpoints": [],
                    "timeout_ms": timeout_seconds * 1000,
                    "capture_limit": capture_limit,
                    "cwd_inode": str(cwd_inode) if cwd_inode is not None else None,
                    "workspace_inode": str(workspace_inode),
                },
                handle,
                separators=(",", ":"),
            )
        path.chmod(0o600)
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _parse_result(
    stdout: bytes,
    stderr: bytes,
    *,
    expected_mode: Literal["read-only", "workspace-write", "danger-full-access"],
) -> ContainerSandboxResult:
    if stderr.strip():
        detail = stderr.decode("utf-8", errors="replace").strip()[:1000]
        raise RuntimeError(f"sandbox container failed: {detail}")
    lines = [line for line in stdout.decode("utf-8", errors="replace").splitlines() if line]
    if len(lines) != 1:
        raise RuntimeError("sandbox container returned an invalid response")
    try:
        value = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise RuntimeError("sandbox container returned invalid JSON") from exc
    if not isinstance(value, dict) or value.get("version") != 1:
        raise RuntimeError("sandbox container response version is unsupported")
    expected_fields = {
        "version",
        "status",
        "exit_code",
        "signal",
        "stdout",
        "stderr",
        "output_limit_exceeded",
        "timed_out",
        "sandbox",
    }
    if set(value) != expected_fields or value.get("status") != "completed":
        raise RuntimeError("sandbox container response schema is invalid")
    exit_code = value.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise RuntimeError("sandbox container response exit code is invalid")
    if not isinstance(value.get("stdout"), str) or not isinstance(
        value.get("stderr"), str
    ):
        raise RuntimeError("sandbox container response output is invalid")
    if not isinstance(value.get("output_limit_exceeded"), bool) or not isinstance(
        value.get("timed_out"), bool
    ):
        raise RuntimeError("sandbox container response flags are invalid")
    if value.get("signal") is not None and not isinstance(value.get("signal"), str):
        raise RuntimeError("sandbox container response signal is invalid")
    sandbox = value.get("sandbox")
    if not isinstance(sandbox, dict) or set(sandbox) != {
        "mode",
        "adapter",
        "enforcement",
        "denial_signatures",
        "runner_failure_rules",
    }:
        raise RuntimeError("sandbox container response omitted confinement facts")
    if sandbox.get("mode") != expected_mode:
        raise RuntimeError("sandbox container response mode did not match request")
    if not isinstance(sandbox.get("adapter"), str) or not sandbox.get("adapter"):
        raise RuntimeError("sandbox container response adapter is invalid")
    expected_enforcement = None if expected_mode == "danger-full-access" else "full"
    if sandbox.get("enforcement") != expected_enforcement:
        raise RuntimeError("sandbox container response enforcement is invalid")
    signatures = sandbox.get("denial_signatures")
    rules = sandbox.get("runner_failure_rules")
    if not isinstance(signatures, list) or any(
        not isinstance(item, str) or not item for item in signatures
    ):
        raise RuntimeError("sandbox container denial signatures are invalid")
    if not isinstance(rules, list) or any(not isinstance(item, dict) for item in rules):
        raise RuntimeError("sandbox container runner failure rules are invalid")
    for rule in rules:
        if not set(rule) <= {
            "allowed_exit_codes",
            "fatal_signatures",
            "informational_lines",
        }:
            raise RuntimeError("sandbox container runner failure rule is invalid")
        fatal = rule.get("fatal_signatures")
        allowed = rule.get("allowed_exit_codes", [])
        informational = rule.get("informational_lines", [])
        if (
            not isinstance(fatal, list)
            or not fatal
            or any(not isinstance(item, str) or not item for item in fatal)
            or not isinstance(allowed, list)
            or any(isinstance(item, bool) or not isinstance(item, int) for item in allowed)
            or not isinstance(informational, list)
            or any(
                not isinstance(item, str) or not item for item in informational
            )
        ):
            raise RuntimeError("sandbox container runner failure rule is invalid")
    if expected_mode == "danger-full-access" and (signatures or rules):
        raise RuntimeError("unconfined sandbox response included confinement rules")
    return ContainerSandboxResult(
        exit_code=exit_code,
        stdout=value["stdout"],
        stderr=value["stderr"],
        output_limit_exceeded=value["output_limit_exceeded"],
        timed_out=value["timed_out"],
        sandbox=sandbox,
    )


async def _wait_for_cancellation(cancellation: Any | None) -> None:
    if cancellation is None:
        await asyncio.Future()
    wait = getattr(cancellation, "wait", None)
    if not callable(wait):
        await asyncio.Future()
    await wait()


async def _finish_container_start(task: asyncio.Task) -> Any | None:
    """Recover a container handle after cancellation races Docker startup."""

    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    try:
        return task.result()
    except Exception:
        return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _container_read_roots() -> tuple[Path, ...]:
    roots = (
        Path(settings.projects_root),
        Path(settings.sources_root),
        Path(settings.skills_root),
    )
    result: list[Path] = []
    sensitive = sensitive_capability_paths()
    for root in roots:
        resolved = root.expanduser().resolve(strict=False)
        if not resolved.is_dir():
            continue
        if resolved == Path("/") or any(
            _is_relative_to(resolved, protected)
            or _is_relative_to(protected, resolved)
            for protected in sensitive
        ):
            raise RuntimeError(
                f"sandbox read root overlaps a protected capability path: {resolved}"
            )
        if resolved not in result:
            result.append(resolved)
    return tuple(result)


def _running_in_container() -> bool:
    return Path("/.dockerenv").exists()

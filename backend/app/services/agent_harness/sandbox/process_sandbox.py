"""DeepSeek Harness backed local process confinement.

BioinfoFlow owns the stable JSON-lines bridge and process supervision. Platform
profiles, provider selection, denial signatures, and launcher-failure rules come
from the pinned ``@deepseek-ai/dsh-sandbox-local`` package.
"""

from __future__ import annotations

import atexit
from collections import deque
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
from typing import Any, Literal, Protocol, TypeAlias
import uuid

from app.config import BACKEND_ROOT, settings
from app.services.agent_harness.sandbox.capability_paths import (
    sensitive_capability_paths,
)


SandboxMode: TypeAlias = Literal[
    "read-only", "workspace-write", "danger-full-access"
]
ConfinedSandboxMode: TypeAlias = Literal["read-only", "workspace-write"]
_shared_client_instance: DeepSeekSandboxClient | None = None
_shared_client_lock = threading.Lock()


class SandboxUnavailableError(RuntimeError):
    """Raised when required confinement cannot be established."""


@dataclass(frozen=True, slots=True)
class SandboxAvailability:
    adapter: str
    executable: str | None
    available: bool
    failure_category: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class SandboxResult:
    argv: list[str]
    adapter: str
    sandboxed: bool
    mode: SandboxMode
    enforcement: Literal["full", "partial"] | None = None
    denial_signatures: tuple[str, ...] = ()
    runner_failure_rules: tuple[dict[str, Any], ...] = ()


class SandboxClient(Protocol):
    def availability(self) -> SandboxAvailability | dict[str, Any]: ...

    def confine(
        self,
        *,
        argv: list[str],
        mode: ConfinedSandboxMode,
        workspace_root: Path,
        protected_endpoints: list[Path],
    ) -> SandboxResult: ...


class DeepSeekSandboxClient:
    """Persistent fail-closed client for the versioned Node worker protocol."""

    def __init__(
        self,
        *,
        worker_command: tuple[str, ...] | None = None,
        request_timeout_seconds: float = 5.0,
    ) -> None:
        self.worker_command = worker_command or _default_worker_command()
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        self.request_timeout_seconds = request_timeout_seconds
        self._process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[dict[str, Any] | BaseException | None] = (
            queue.Queue()
        )
        self._stderr: deque[str] = deque(maxlen=20)
        self._request_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._closed = False
        atexit.register(self.close)

    def availability(self) -> SandboxAvailability:
        executable = shutil.which(self.worker_command[0])
        worker = _worker_script_from_command(self.worker_command)
        if executable is None:
            return SandboxAvailability(
                adapter="deepseek-local",
                executable=None,
                available=False,
                failure_category="binary_missing",
                failure_message=f"{self.worker_command[0]} executable not found",
            )
        if worker is not None and not worker.is_file():
            return SandboxAvailability(
                adapter="deepseek-local",
                executable=executable,
                available=False,
                failure_category="worker_missing",
                failure_message=f"sandbox worker not found: {worker}",
            )
        if worker is not None and not (
            worker.parent
            / "node_modules"
            / "@deepseek-ai"
            / "dsh-sandbox-local"
            / "package.json"
        ).is_file():
            return SandboxAvailability(
                adapter="deepseek-local",
                executable=executable,
                available=False,
                failure_category="dependencies_missing",
                failure_message="sandbox worker dependencies are not installed",
            )
        return SandboxAvailability(
            adapter="deepseek-local",
            executable=executable,
            available=True,
        )

    def confine(
        self,
        *,
        argv: list[str],
        mode: ConfinedSandboxMode,
        workspace_root: Path,
        protected_endpoints: list[Path],
    ) -> SandboxResult:
        if mode not in {"read-only", "workspace-write"}:
            raise ValueError(f"unsupported confined sandbox mode: {mode}")
        if not argv or any(not isinstance(item, str) or not item for item in argv):
            raise ValueError("sandbox argv must contain non-empty strings")
        root = workspace_root.expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"sandbox workspace root is not a directory: {root}")
        request_id = uuid.uuid4().hex
        request = {
            "version": 1,
            "id": request_id,
            "method": "confine",
            "argv": list(argv),
            "mode": mode,
            "workspace_root": str(root),
            "protected_endpoints": [
                str(path.expanduser().resolve(strict=False))
                for path in protected_endpoints
            ],
        }
        with self._request_lock:
            process = self._ensure_process()
            assert process.stdin is not None
            try:
                process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._invalidate_process()
                raise SandboxUnavailableError(
                    f"DeepSeek sandbox worker exited before request: {exc}"
                ) from exc
            try:
                response = self._responses.get(timeout=self.request_timeout_seconds)
            except queue.Empty as exc:
                self._invalidate_process()
                raise SandboxUnavailableError(
                    "DeepSeek sandbox worker response timed out"
                ) from exc
            if response is None:
                detail = self._stderr_detail()
                self._invalidate_process()
                raise SandboxUnavailableError(
                    "DeepSeek sandbox worker exited before responding" + detail
                )
            if isinstance(response, BaseException):
                self._invalidate_process()
                raise SandboxUnavailableError(
                    f"DeepSeek sandbox worker returned invalid JSON: {response}"
                ) from response
            if set(response) not in (
                {"version", "id", "ok", "result"},
                {"version", "id", "ok", "error"},
            ):
                self._invalidate_process()
                raise SandboxUnavailableError(
                    "DeepSeek sandbox worker response schema is invalid"
                )
            if response.get("version") != 1:
                self._invalidate_process()
                raise SandboxUnavailableError(
                    "DeepSeek sandbox worker response version is unsupported"
                )
            if response.get("id") != request_id:
                self._invalidate_process()
                raise SandboxUnavailableError(
                    "DeepSeek sandbox worker response id did not match request"
                )
            if response.get("ok") is not True:
                error = response.get("error")
                if not isinstance(error, dict) or set(error) != {"code", "message"}:
                    self._invalidate_process()
                    raise SandboxUnavailableError(
                        "DeepSeek sandbox worker error schema is invalid"
                    )
                message = (
                    str(error.get("message"))
                    if isinstance(error, dict) and error.get("message")
                    else "DeepSeek sandbox worker rejected the request"
                )
                raise SandboxUnavailableError(message)
            try:
                return _parse_result(response.get("result"), mode=mode)
            except SandboxUnavailableError:
                self._invalidate_process()
                raise

    def close(self) -> None:
        with self._lifecycle_lock:
            self._closed = True
            self._stop_process_locked()

    def _ensure_process(self) -> subprocess.Popen[str]:
        with self._lifecycle_lock:
            if self._closed:
                raise SandboxUnavailableError("DeepSeek sandbox client is closed")
            if self._process is not None and self._process.poll() is None:
                return self._process
            availability = self.availability()
            if not availability.available:
                raise SandboxUnavailableError(
                    availability.failure_message or "DeepSeek sandbox worker unavailable"
                )
            self._responses = queue.Queue()
            self._stderr.clear()
            try:
                process = subprocess.Popen(
                    list(self.worker_command),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
            except OSError as exc:
                raise SandboxUnavailableError(
                    f"unable to start DeepSeek sandbox worker: {exc}"
                ) from exc
            self._process = process
            assert process.stdout is not None
            assert process.stderr is not None
            self._reader = threading.Thread(
                target=self._read_responses,
                args=(process, self._responses),
                name="deepseek-sandbox-worker-stdout",
                daemon=True,
            )
            self._stderr_reader = threading.Thread(
                target=self._read_stderr,
                args=(process,),
                name="deepseek-sandbox-worker-stderr",
                daemon=True,
            )
            self._reader.start()
            self._stderr_reader.start()
            return process

    def _read_responses(
        self,
        process: subprocess.Popen[str],
        responses: queue.Queue[dict[str, Any] | BaseException | None],
    ) -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                try:
                    response = json.loads(line)
                    if not isinstance(response, dict):
                        raise TypeError("response must be a JSON object")
                except (json.JSONDecodeError, TypeError) as exc:
                    responses.put(exc)
                    return
                responses.put(response)
        finally:
            responses.put(None)

    def _read_stderr(self, process: subprocess.Popen[str]) -> None:
        assert process.stderr is not None
        for line in process.stderr:
            cleaned = " ".join(line.split())
            if cleaned:
                self._stderr.append(cleaned[:400])

    def _stderr_detail(self) -> str:
        return f": {' | '.join(self._stderr)}" if self._stderr else ""

    def _invalidate_process(self) -> None:
        with self._lifecycle_lock:
            self._stop_process_locked()

    def _stop_process_locked(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)


class SandboxRunner:
    """Map BioinfoFlow policy to DeepSeek confinement for one local command."""

    def __init__(
        self,
        *,
        enabled: bool,
        client: SandboxClient | None = None,
    ) -> None:
        self.enabled = enabled
        # DeepSeek's file-effect sandbox does not restrict network visibility.
        self.allow_network = True
        self.client = client or _shared_client()

    @classmethod
    def from_settings(cls, source: object | None = None) -> "SandboxRunner":
        configured = source or settings
        return cls(enabled=bool(getattr(configured, "agent_sandbox_enabled", True)))

    def build(
        self,
        *,
        command: str,
        cwd: Path,
        workspace_root: Path | None = None,
        mode: SandboxMode = "workspace-write",
        protected_endpoints: list[Path] | None = None,
        **legacy_options: Any,
    ) -> SandboxResult:
        if legacy_options:
            names = ", ".join(sorted(legacy_options))
            raise TypeError(f"unsupported sandbox options: {names}")
        if not self.enabled:
            raise SandboxUnavailableError(
                "agent bash requires operating-system sandboxing"
            )
        shell_argv = [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-c",
            command,
        ]
        if mode == "danger-full-access":
            return SandboxResult(
                argv=shell_argv,
                adapter="danger-full-access",
                sandboxed=False,
                mode=mode,
            )
        if mode not in {"read-only", "workspace-write"}:
            raise ValueError(f"unknown sandbox mode: {mode}")
        result = self.client.confine(
            argv=shell_argv,
            mode=mode,
            workspace_root=workspace_root or cwd,
            protected_endpoints=(
                _protected_endpoints()
                if protected_endpoints is None
                else protected_endpoints
            ),
        )
        return SandboxResult(
            argv=list(result.argv),
            adapter=result.adapter,
            sandboxed=True,
            mode=mode,
            enforcement=result.enforcement,
            denial_signatures=tuple(result.denial_signatures),
            runner_failure_rules=tuple(result.runner_failure_rules),
        )

    def availability(self) -> SandboxAvailability:
        value = self.client.availability()
        if isinstance(value, SandboxAvailability):
            return value
        return SandboxAvailability(
            adapter=str(value.get("adapter") or "deepseek-local"),
            executable=(
                str(value["executable"]) if value.get("executable") else None
            ),
            available=bool(value.get("available")),
            failure_category=(
                str(value["failure_category"])
                if value.get("failure_category")
                else None
            ),
            failure_message=(
                str(value["failure_message"])
                if value.get("failure_message")
                else None
            ),
        )

    def available_adapter(self) -> SandboxClient | None:
        return self.client if self.availability().available else None


def _parse_result(value: Any, *, mode: ConfinedSandboxMode) -> SandboxResult:
    if not isinstance(value, dict):
        raise SandboxUnavailableError("DeepSeek sandbox worker result is missing")
    if set(value) != {
        "argv",
        "adapter",
        "enforcement",
        "denial_signatures",
        "runner_failure_rules",
    }:
        raise SandboxUnavailableError(
            "DeepSeek sandbox worker result schema is invalid"
        )
    argv = value.get("argv")
    adapter = value.get("adapter")
    enforcement = value.get("enforcement")
    denial_signatures = value.get("denial_signatures")
    runner_failure_rules = value.get("runner_failure_rules")
    if not isinstance(argv, list) or not argv or any(
        not isinstance(item, str) or not item for item in argv
    ):
        raise SandboxUnavailableError("DeepSeek sandbox worker returned invalid argv")
    if not isinstance(adapter, str) or not adapter:
        raise SandboxUnavailableError("DeepSeek sandbox worker returned no adapter")
    if enforcement != "full":
        raise SandboxUnavailableError(
            "DeepSeek sandbox worker did not provide full enforcement"
        )
    if not isinstance(denial_signatures, list) or any(
        not isinstance(item, str) or not item for item in denial_signatures
    ):
        raise SandboxUnavailableError(
            "DeepSeek sandbox worker returned invalid denial signatures"
        )
    rules = _normalize_runner_failure_rules(runner_failure_rules)
    return SandboxResult(
        argv=list(argv),
        adapter=adapter,
        sandboxed=True,
        mode=mode,
        enforcement="full",
        denial_signatures=tuple(denial_signatures),
        runner_failure_rules=rules,
    )


def _normalize_runner_failure_rules(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise SandboxUnavailableError(
            "DeepSeek sandbox worker returned invalid runner failure rules"
        )
    normalized: list[dict[str, Any]] = []
    for rule in value:
        if not isinstance(rule, dict):
            raise SandboxUnavailableError(
                "DeepSeek sandbox worker returned invalid runner failure rule"
            )
        item: dict[str, Any] = {}
        for key, raw in rule.items():
            if key not in {
                "allowed_exit_codes",
                "fatal_signatures",
                "informational_lines",
            }:
                raise SandboxUnavailableError(
                    "DeepSeek sandbox worker returned an unknown runner failure field"
                )
            if not isinstance(raw, list):
                raise SandboxUnavailableError(
                    "DeepSeek sandbox worker returned invalid runner failure values"
                )
            if key == "allowed_exit_codes":
                if any(
                    isinstance(entry, bool) or not isinstance(entry, int)
                    for entry in raw
                ):
                    raise SandboxUnavailableError(
                        "DeepSeek sandbox worker returned invalid exit codes"
                    )
            elif any(not isinstance(entry, str) or not entry for entry in raw):
                raise SandboxUnavailableError(
                    "DeepSeek sandbox worker returned invalid failure signatures"
                )
            item[key] = tuple(raw)
        if not item.get("fatal_signatures"):
            raise SandboxUnavailableError(
                "DeepSeek sandbox worker returned a failure rule without signatures"
            )
        normalized.append(item)
    return tuple(normalized)


def _default_worker_command() -> tuple[str, ...]:
    return (
        os.environ.get("BIOINFOFLOW_SANDBOX_NODE", "node"),
        str(Path(BACKEND_ROOT) / "sandbox_worker" / "worker.mjs"),
    )


def _worker_script_from_command(command: tuple[str, ...]) -> Path | None:
    if len(command) != 2 or command[0].endswith(("python", "python3")):
        return None
    candidate = Path(command[1])
    return candidate if candidate.suffix in {".js", ".mjs", ".cjs"} else None


def _protected_endpoints() -> list[Path]:
    return list(sensitive_capability_paths())


def _shared_client() -> DeepSeekSandboxClient:
    global _shared_client_instance
    with _shared_client_lock:
        if _shared_client_instance is None:
            _shared_client_instance = DeepSeekSandboxClient()
        return _shared_client_instance

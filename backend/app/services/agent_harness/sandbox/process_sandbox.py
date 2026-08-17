"""OS-level process confinement for the bash tool.

The bible's core principle: *permissions gate the tool; the OS sandbox confines
the process — do not trust command-string parsing.* The risk classifier
(:mod:`app.services.agent_harness.command_risk`) decides whether a command
auto-runs or requires confirmation, but it can never be a security boundary
against a shell that runs arbitrary strings. This module builds the real
boundary: an argv that runs the command under ``bwrap`` (Linux/containers) or
``sandbox-exec`` (macOS), confined to explicit read/write roots with the network
off by default.

Selection is platform-aware and fail-closed: when sandboxing is enabled but no
adapter binary is available, :meth:`SandboxRunner.build` raises rather than
silently running the command unconfined.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, ClassVar, Protocol

from app.config import BACKEND_ROOT, settings


class SandboxUnavailableError(RuntimeError):
    """Raised when sandboxing is required (fail-closed) but unavailable."""


# Read-only system directories every confined command needs to run a shell.
# Do not bind /etc wholesale: the sandbox boundary should block commands such
# as `cat /etc/passwd` rather than relying on the permission classifier.
_LINUX_SYSTEM_RO = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/opt")
_MACOS_WRITE_ROOTS = (
    "/dev/null",
    "/dev/dtracehelper",
    "/private/tmp",
)
_MACOS_SYSTEM_READ_ROOTS = (
    "/System",
    "/usr",
    "/bin",
    "/sbin",
    "/dev",
    "/Library/Apple",
    "/System/Cryptexes",
    "/private/var/db/dyld",
    "/private/etc",
    "/etc",
)
_BWRAP_PROTECTED_STAGE_PREFIX = "/.bioinfoflow-protected-read"
_BWRAP_USER_NAMESPACE_ARGS = ("--unshare-user", "--uid", "0", "--gid", "0")
_BWRAP_PROBE_ARGS = (
    *_BWRAP_USER_NAMESPACE_ARGS,
    "--ro-bind",
    "/",
    "/",
    "--",
    "/bin/true",
)
_BWRAP_PROBE_TIMEOUT_SECONDS = 2.0
_BWRAP_AVAILABILITY_CACHE_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class SandboxSpec:
    command: str
    cwd: Path
    cwd_fd: int | None = None
    read_roots: list[Path] = field(default_factory=list)
    write_roots: list[Path] = field(default_factory=list)
    deny_read_roots: list[Path] = field(default_factory=list)
    protected_roots: list[Path] = field(default_factory=list)
    protected_read_roots: list[Path] = field(default_factory=list)
    docker_socket_root: Path | None = None
    allow_network: bool = False


@dataclass(frozen=True)
class SandboxResult:
    argv: list[str]
    adapter: str
    sandboxed: bool


@dataclass(frozen=True, slots=True)
class SandboxAvailability:
    adapter: str
    executable: str | None
    available: bool
    failure_category: str | None = None
    failure_message: str | None = None


class SandboxAdapter(Protocol):
    name: str

    def availability(self) -> SandboxAvailability: ...

    def available(self) -> bool: ...

    def supports_docker_socket(self, root: Path) -> bool: ...

    def build_argv(self, spec: SandboxSpec) -> list[str]: ...


class BubblewrapAdapter:
    """Linux/container confinement via ``bwrap`` (bubblewrap)."""

    name = "bubblewrap"
    _availability_cache: ClassVar[
        dict[tuple[str, tuple[str, ...]], tuple[float, SandboxAvailability]]
    ] = {}
    _availability_cache_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic

    @classmethod
    def clear_availability_cache(cls) -> None:
        """Clear the process cache, primarily for deterministic tests."""
        with cls._availability_cache_lock:
            cls._availability_cache.clear()

    def availability(self) -> SandboxAvailability:
        executable = shutil.which("bwrap")
        if executable is None:
            return SandboxAvailability(
                adapter=self.name,
                executable=None,
                available=False,
                failure_category="binary_missing",
                failure_message="bwrap executable not found",
            )

        cache_key = (executable, _BWRAP_PROBE_ARGS)
        now = self._clock()
        with self._availability_cache_lock:
            cached = self._availability_cache.get(cache_key)
            if (
                cached is not None
                and now - cached[0] < _BWRAP_AVAILABILITY_CACHE_TTL_SECONDS
            ):
                return cached[1]

            try:
                probe = subprocess.run(
                    [executable, *_BWRAP_PROBE_ARGS],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_BWRAP_PROBE_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                result = SandboxAvailability(
                    adapter=self.name,
                    executable=executable,
                    available=False,
                    failure_category="probe_timeout",
                    failure_message="probe timed out after 2 seconds",
                )
            except (OSError, UnicodeError) as exc:
                result = SandboxAvailability(
                    adapter=self.name,
                    executable=executable,
                    available=False,
                    failure_category="probe_os_error",
                    failure_message=_sanitize_diagnostic(str(exc)),
                )
            else:
                if probe.returncode == 0:
                    result = SandboxAvailability(
                        adapter=self.name,
                        executable=executable,
                        available=True,
                    )
                else:
                    message = _sanitize_diagnostic(probe.stderr)
                    result = SandboxAvailability(
                        adapter=self.name,
                        executable=executable,
                        available=False,
                        failure_category="probe_exit",
                        failure_message=message
                        or f"probe exited with status {probe.returncode}",
                    )
            self._availability_cache[cache_key] = (now, result)
            return result

    def available(self) -> bool:
        return self.availability().available

    def supports_docker_socket(self, root: Path) -> bool:
        return root.exists()

    def build_argv(self, spec: SandboxSpec) -> list[str]:
        argv: list[str] = ["bwrap", *_BWRAP_USER_NAMESPACE_ARGS]
        if spec.cwd_fd is not None:
            argv += ["--sync-fd", str(spec.cwd_fd)]
        for directory in _LINUX_SYSTEM_RO:
            if Path(directory).exists():
                argv += ["--ro-bind", directory, directory]
        # Establish synthetic filesystems before capability binds. Otherwise a
        # later tmpfs mount would hide any allowed workspace rooted under /tmp.
        argv += ["--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
        protected_roots = _existing(spec.protected_roots)
        for root in _outside_protected(_existing(spec.read_roots), protected_roots):
            argv += ["--ro-bind", str(root), str(root)]
        # Write roots are bound after read roots so rw access wins where they
        # overlap a read-only bind.
        for root in _outside_protected(_existing(spec.write_roots), protected_roots):
            argv += ["--bind", str(root), str(root)]
        if spec.cwd_fd is not None:
            cwd_bind = (
                "--bind"
                if any(
                    _is_relative_to(spec.cwd, root)
                    for root in _existing(spec.write_roots)
                )
                else "--ro-bind"
            )
            argv += [
                cwd_bind,
                f"/proc/self/fd/{spec.cwd_fd}",
                str(spec.cwd),
            ]
        protected_read_roots = _existing(spec.protected_read_roots)
        staged_roots = [
            (root, f"{_BWRAP_PROTECTED_STAGE_PREFIX}-{index}")
            for index, root in enumerate(protected_read_roots)
        ]
        for root, stage in staged_roots:
            argv += ["--ro-bind", str(root), stage]
        mount_actions = [
            (len(root.parts), 0, root, None, None) for root in protected_roots
        ] + [
            (len(root.parts), 1, root, stage, "--ro-bind")
            for root, stage in staged_roots
        ]
        for _depth, kind, root, stage, bind in sorted(
            mount_actions,
            key=lambda item: (item[0], item[1], str(item[2])),
        ):
            if kind == 0:
                if root.is_dir():
                    argv += ["--dir", str(root), "--tmpfs", str(root)]
                else:
                    argv += ["--ro-bind", "/dev/null", str(root)]
            else:
                argv += ["--dir", str(root), str(bind), str(stage), str(root)]
        for _root, stage in staged_roots:
            argv += ["--tmpfs", stage]
        if not spec.allow_network:
            argv += ["--unshare-net"]
        argv += ["--chdir", str(spec.cwd), "--die-with-parent"]
        argv += ["bash", "--noprofile", "--norc", "-c", spec.command]
        return argv


class SeatbeltAdapter:
    """macOS dev confinement via ``sandbox-exec`` (Seatbelt)."""

    name = "seatbelt"

    def availability(self) -> SandboxAvailability:
        executable = shutil.which("sandbox-exec")
        if executable is None:
            return SandboxAvailability(
                adapter=self.name,
                executable=None,
                available=False,
                failure_category="binary_missing",
                failure_message="sandbox-exec executable not found",
            )
        return SandboxAvailability(
            adapter=self.name,
            executable=executable,
            available=True,
        )

    def available(self) -> bool:
        return self.availability().available

    def supports_docker_socket(self, root: Path) -> bool:
        return root.exists()

    def build_argv(self, spec: SandboxSpec) -> list[str]:
        profile = self._profile(spec)
        return [
            "sandbox-exec",
            "-p",
            profile,
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-c",
            spec.command,
        ]

    def _profile(self, spec: SandboxSpec) -> str:
        write_roots = list(_MACOS_WRITE_ROOTS) + [
            str(root) for root in _existing(spec.write_roots)
        ]
        deny_read_rules = "\n".join(
            f'    (subpath "{path}")'
            for path in _dedupe([str(root) for root in spec.deny_read_roots])
        )
        deny_read_section = (
            ["(deny file-read-data", deny_read_rules, ")"] if deny_read_rules else []
        )
        read_roots = _dedupe(
            [
                *(
                    str(root)
                    for root in _existing(
                        [Path(path) for path in _MACOS_SYSTEM_READ_ROOTS]
                    )
                ),
                *(str(root) for root in _existing(spec.read_roots)),
            ]
        )
        read_denials = _seatbelt_global_denial(
            operation="file-read-data",
            allowed=read_roots,
        )
        write_denials = _seatbelt_global_denial(
            operation="file-write*",
            allowed=_dedupe(write_roots),
        )
        if spec.allow_network:
            network_rule = ""
        elif spec.docker_socket_root is not None:
            network_rule = (
                "(deny network* (require-not (literal "
                f"{json.dumps(str(spec.docker_socket_root))})))"
            )
        else:
            network_rule = "(deny network*)"
        protected_read_roots = [
            str(root) for root in _existing(spec.protected_read_roots)
        ]
        protected_rules: list[str] = []
        for root in _existing(spec.protected_roots):
            protected_rules.append(f'(deny file-write* (subpath "{root}"))')
            read_exceptions = [
                allowed
                for allowed in protected_read_roots
                if _is_relative_to(Path(allowed), root)
            ]
            if read_exceptions:
                protected_rules.extend(
                    [
                        "(deny file-read*",
                        "    (require-all",
                        f'        (subpath "{root}")',
                        *[
                            f'        (require-not (subpath "{path}"))'
                            for path in read_exceptions
                        ],
                        "    )",
                        ")",
                    ]
                )
            else:
                protected_rules.append(f'(deny file-read* (subpath "{root}"))')
        return "\n".join(
            [
                "(version 1)",
                # macOS processes need evolving Mach/IPC capabilities. Start
                # from the platform baseline, then deny file contents, writes
                # and network outside explicit capabilities.
                "(allow default)",
                *read_denials,
                *deny_read_section,
                *write_denials,
                *protected_rules,
                network_rule,
            ]
        )


class SandboxRunner:
    def __init__(
        self,
        *,
        enabled: bool,
        allow_network: bool = False,
        adapters: list[SandboxAdapter] | None = None,
    ) -> None:
        self.enabled = enabled
        self.allow_network = allow_network
        self.adapters = adapters if adapters is not None else _default_adapters()

    @classmethod
    def from_settings(cls, source: object | None = None) -> "SandboxRunner":
        if source is None:
            source = settings
        return cls(
            enabled=bool(getattr(source, "agent_sandbox_enabled")),
            allow_network=bool(getattr(source, "agent_sandbox_allow_network", False)),
        )

    def build(
        self,
        *,
        command: str,
        cwd: Path,
        read_roots: list[Path],
        write_roots: list[Path],
        cwd_fd: int | None = None,
        deny_read_roots: list[Path] | None = None,
        protected_roots: list[Path] | None = None,
        protected_read_roots: list[Path] | None = None,
        docker_socket_root: Path | None = None,
        allow_network: bool | None = None,
    ) -> SandboxResult:
        if not self.enabled:
            raise SandboxUnavailableError(
                "agent bash requires operating-system sandboxing"
            )

        adapter, availability = self._select_adapter()
        if adapter is None:
            detail = f"{availability.adapter} {availability.failure_category}"
            if availability.failure_message:
                detail += f": {availability.failure_message}"
            raise SandboxUnavailableError(f"agent sandbox unavailable: {detail}")

        spec = SandboxSpec(
            command=command,
            cwd=cwd,
            cwd_fd=cwd_fd,
            read_roots=_dedupe_paths([*read_roots, *_runtime_read_roots()]),
            write_roots=write_roots,
            deny_read_roots=list(deny_read_roots or []),
            protected_roots=protected_roots or [],
            protected_read_roots=protected_read_roots or [],
            docker_socket_root=docker_socket_root,
            allow_network=(
                self.allow_network if allow_network is None else allow_network
            ),
        )
        return SandboxResult(adapter.build_argv(spec), adapter.name, True)

    def _select_adapter(self) -> tuple[SandboxAdapter | None, SandboxAvailability]:
        unavailable: SandboxAvailability | None = None
        for adapter in self.adapters:
            availability = adapter.availability()
            if availability.available:
                return adapter, availability
            if unavailable is None:
                unavailable = availability
        return None, unavailable or SandboxAvailability(
            adapter="none",
            executable=None,
            available=False,
            failure_category="binary_missing",
            failure_message="no sandbox adapter configured",
        )

    def available_adapter(self) -> SandboxAdapter | None:
        """Return the OS sandbox adapter currently available for this runner."""
        return self._select_adapter()[0]

    def availability(self) -> SandboxAvailability:
        """Return the selected adapter's complete availability diagnostic."""
        return self._select_adapter()[1]


def adapter_supports_docker_socket(
    adapter: SandboxAdapter | None,
    root: Path | None,
) -> bool:
    if adapter is None or root is None:
        return False
    supports = getattr(adapter, "supports_docker_socket", None)
    return bool(supports is not None and supports(root))


def _default_adapters() -> list[SandboxAdapter]:
    system = platform.system()
    if system == "Darwin":
        return [SeatbeltAdapter()]
    return [BubblewrapAdapter()]


def _existing(roots: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for root in roots:
        resolved = Path(root)
        key = str(resolved)
        if key in seen or not resolved.exists():
            continue
        seen.add(key)
        result.append(resolved)
    return result


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_paths(values: list[Path]) -> list[Path]:
    return [Path(value) for value in _dedupe([str(Path(value)) for value in values])]


def _seatbelt_global_denial(
    *,
    operation: str,
    allowed: list[str],
) -> list[str]:
    paths = _dedupe(allowed)
    if not paths:
        return [f"(deny {operation})"]
    ancestors = _dedupe(
        [str(parent) for path in paths for parent in (Path(path), *Path(path).parents)]
    )
    filters = [
        *[f'(subpath "{path}")' for path in paths],
        *[f'(literal "{path}")' for path in ancestors],
    ]
    return [
        f"(deny {operation}",
        "    (require-all",
        *[f"        (require-not {item})" for item in filters],
        "    )",
        ")",
    ]


def _runtime_read_roots() -> list[Path]:
    """Return narrow executable/runtime roots, never the user's whole home."""

    candidates = [
        Path(sys.prefix),
        Path(sys.executable).resolve().parent.parent,
        Path(BACKEND_ROOT) / "app",
    ]
    path = os.environ.get("PATH", "")
    for name in (
        "bif",
        "python",
        "python3",
        "rg",
        "git",
        "node",
        "npm",
        "bun",
        "R",
        "Rscript",
        "nextflow",
        "miniwdl",
        "docker",
    ):
        executable = shutil.which(name, path=path)
        if executable is None:
            continue
        resolved = Path(executable).resolve()
        candidates.append(_executable_runtime_root(resolved))
    broad = {Path("/"), Path.home().resolve()}
    return [
        root
        for root in _existing(_dedupe_paths(candidates))
        if root.resolve() not in broad
    ]


def _executable_runtime_root(executable: Path) -> Path:
    for parent in executable.parents:
        if parent.name == "bin":
            candidate = parent.parent
            if candidate in {Path("/"), Path.home().resolve()}:
                return parent
            return candidate
    return executable.parent


def _sanitize_diagnostic(message: str | None) -> str:
    printable = "".join(
        character if character.isprintable() else " " for character in message or ""
    )
    return " ".join(printable.split())[:400]


def _outside_protected(roots: list[Path], protected_roots: list[Path]) -> list[Path]:
    return [
        root
        for root in roots
        if not any(_is_relative_to(root, protected) for protected in protected_roots)
    ]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

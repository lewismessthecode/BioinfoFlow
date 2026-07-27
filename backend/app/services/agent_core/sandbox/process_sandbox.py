"""OS-level process confinement for the bash tool.

The bible's core principle: *permissions gate the tool; the OS sandbox confines
the process — do not trust command-string parsing.* The risk classifier
(:mod:`permissions.shell_risk`) decides whether a command auto-runs or pauses
for approval, but it can never be a security boundary against a shell that runs
arbitrary strings. This module builds the real boundary: an argv that runs the
command under ``bwrap`` (Linux/containers) or ``sandbox-exec`` (macOS), confined
to explicit read/write roots with the network off by default.

Selection is platform-aware and fail-closed: when sandboxing is enabled but no
adapter binary is available, :meth:`SandboxRunner.build` raises rather than
silently running the command unconfined.
"""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.config import settings


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
    "/private/var/folders",
)
_BWRAP_PROTECTED_STAGE_PREFIX = "/.bioinfoflow-protected-read"


@dataclass(frozen=True)
class SandboxSpec:
    command: str
    cwd: Path
    read_roots: list[Path] = field(default_factory=list)
    write_roots: list[Path] = field(default_factory=list)
    deny_read_roots: list[Path] = field(default_factory=list)
    protected_roots: list[Path] = field(default_factory=list)
    protected_read_roots: list[Path] = field(default_factory=list)
    allow_network: bool = False


@dataclass(frozen=True)
class SandboxResult:
    argv: list[str]
    adapter: str
    sandboxed: bool


class SandboxAdapter(Protocol):
    name: str

    def available(self) -> bool: ...

    def build_argv(self, spec: SandboxSpec) -> list[str]: ...


class BubblewrapAdapter:
    """Linux/container confinement via ``bwrap`` (bubblewrap)."""

    name = "bubblewrap"

    def available(self) -> bool:
        return shutil.which("bwrap") is not None

    def build_argv(self, spec: SandboxSpec) -> list[str]:
        argv: list[str] = ["bwrap"]
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
        protected_read_roots = _existing(spec.protected_read_roots)
        staged_roots = [
            (root, f"{_BWRAP_PROTECTED_STAGE_PREFIX}-{index}")
            for index, root in enumerate(protected_read_roots)
        ]
        for root, stage in staged_roots:
            argv += ["--ro-bind", str(root), stage]
        for root in protected_roots:
            if root.is_dir():
                argv += ["--tmpfs", str(root)]
            else:
                argv += ["--ro-bind", "/dev/null", str(root)]
        for root, stage in staged_roots:
            argv += ["--ro-bind", stage, str(root)]
        for _root, stage in staged_roots:
            argv += ["--tmpfs", stage]
        if not spec.allow_network:
            argv += ["--unshare-net"]
        argv += ["--chdir", str(spec.cwd), "--die-with-parent"]
        argv += ["bash", "-lc", spec.command]
        return argv


class SeatbeltAdapter:
    """macOS dev confinement via ``sandbox-exec`` (Seatbelt)."""

    name = "seatbelt"

    def available(self) -> bool:
        return shutil.which("sandbox-exec") is not None

    def build_argv(self, spec: SandboxSpec) -> list[str]:
        profile = self._profile(spec)
        return ["sandbox-exec", "-p", profile, "bash", "-lc", spec.command]

    def _profile(self, spec: SandboxSpec) -> str:
        write_roots = list(_MACOS_WRITE_ROOTS) + [
            str(root) for root in _existing(spec.write_roots)
        ]
        deny_read_rules = "\n".join(
            f'    (subpath "{path}")'
            for path in _dedupe([str(root) for root in spec.deny_read_roots])
        )
        deny_read_section = (
            ["(deny file-read*", deny_read_rules, ")"] if deny_read_rules else []
        )
        write_rules = "\n".join(
            f'    (subpath "{path}")' for path in _dedupe(write_roots)
        )
        network_rule = "(allow network*)" if spec.allow_network else "(deny network*)"
        protected_read_roots = [
            str(root) for root in _existing(spec.protected_read_roots)
        ]
        protected_rules: list[str] = []
        for root in _existing(spec.protected_roots):
            protected_rules.append(f'(deny file-write* (subpath "{root}"))')
            exceptions = [
                allowed
                for allowed in protected_read_roots
                if _is_relative_to(Path(allowed), root)
            ]
            if exceptions:
                protected_rules.extend(
                    [
                        "(deny file-read*",
                        f'    (subpath "{root}")',
                        "    (require-not",
                        *[f'        (subpath "{path}")' for path in exceptions],
                        "    )",
                        ")",
                    ]
                )
            else:
                protected_rules.append(f'(deny file-read* (subpath "{root}"))')
        return "\n".join(
            [
                "(version 1)",
                "(deny default)",
                "(allow process-exec)",
                "(allow process-fork)",
                "(allow signal)",
                "(allow sysctl-read)",
                # Current macOS shells require a wider set of platform reads
                # than a stable allowlist provides. Keep writes capability-based
                # and explicitly deny permanent protected resources.
                "(allow file-read*)",
                *deny_read_section,
                "(allow file-write*",
                write_rules,
                ")",
                *protected_rules,
                network_rule,
            ]
        )


class NoSandboxAdapter:
    """Fallback: run the command directly with no OS confinement."""

    name = "none"

    def available(self) -> bool:
        return True

    def build_argv(self, spec: SandboxSpec) -> list[str]:
        return ["bash", "-lc", spec.command]


_NO_SANDBOX = NoSandboxAdapter()


class SandboxRunner:
    def __init__(
        self,
        *,
        enabled: bool,
        fail_closed: bool = True,
        allow_network: bool = False,
        allow_unsandboxed: bool = False,
        adapters: list[SandboxAdapter] | None = None,
    ) -> None:
        self.enabled = enabled
        self.fail_closed = fail_closed
        self.allow_network = allow_network
        self.allow_unsandboxed = allow_unsandboxed
        self.adapters = adapters if adapters is not None else _default_adapters()

    @classmethod
    def from_settings(cls) -> "SandboxRunner":
        return cls(
            enabled=bool(settings.agent_sandbox_enabled),
            fail_closed=bool(getattr(settings, "agent_sandbox_fail_closed", True)),
            allow_network=bool(getattr(settings, "agent_sandbox_allow_network", False)),
            allow_unsandboxed=bool(
                getattr(settings, "agent_sandbox_allow_unsandboxed", False)
            ),
        )

    def build(
        self,
        *,
        command: str,
        cwd: Path,
        read_roots: list[Path],
        write_roots: list[Path],
        deny_read_roots: list[Path] | None = None,
        protected_roots: list[Path] | None = None,
        protected_read_roots: list[Path] | None = None,
        disable_requested: bool = False,
    ) -> SandboxResult:
        if not self.enabled:
            return SandboxResult(
                _NO_SANDBOX.build_argv(_spec(command, cwd)), "none", False
            )
        if disable_requested:
            if not self.allow_unsandboxed:
                raise SandboxUnavailableError(
                    "dangerously_disable_sandbox is not permitted (agent_sandbox_allow_unsandboxed is off)"
                )
            return SandboxResult(
                _NO_SANDBOX.build_argv(_spec(command, cwd)), "none", False
            )

        adapter = self.available_adapter()
        if adapter is None:
            if self.fail_closed:
                raise SandboxUnavailableError(
                    "agent_sandbox_enabled is true but no OS sandbox (bwrap/sandbox-exec) is available"
                )
            return SandboxResult(
                _NO_SANDBOX.build_argv(_spec(command, cwd)), "none", False
            )

        spec = SandboxSpec(
            command=command,
            cwd=cwd,
            read_roots=read_roots,
            write_roots=write_roots,
            deny_read_roots=list(deny_read_roots or []),
            protected_roots=protected_roots or [],
            protected_read_roots=protected_read_roots or [],
            allow_network=self.allow_network,
        )
        return SandboxResult(adapter.build_argv(spec), adapter.name, True)

    def _select_adapter(self) -> SandboxAdapter | None:
        for adapter in self.adapters:
            if adapter.available():
                return adapter
        return None

    def available_adapter(self) -> SandboxAdapter | None:
        """Return the OS sandbox adapter currently available for this runner."""
        return self._select_adapter()


def _default_adapters() -> list[SandboxAdapter]:
    system = platform.system()
    if system == "Darwin":
        return [SeatbeltAdapter()]
    return [BubblewrapAdapter()]


def _spec(command: str, cwd: Path) -> SandboxSpec:
    return SandboxSpec(command=command, cwd=cwd)


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

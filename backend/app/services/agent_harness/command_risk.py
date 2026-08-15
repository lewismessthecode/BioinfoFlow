"""Quote-aware shell command semantics used by every execution target.

This module deliberately stops short of interpreting a complete shell grammar.
It extracts the command positions and operators needed by the permission layer
without treating quoted arguments or heredoc bodies as executable source.
"""

from __future__ import annotations

import posixpath
import re
import shlex
import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from app.services.agent_harness.risk import RiskAssessment, RiskLevel


TargetKind = Literal["local", "remote_ssh", "container"]
SandboxStrength = Literal["enforced", "declared", "none"]
RiskConfidence = Literal["high", "medium", "low"]
SemanticEffect = Literal[
    "read",
    "write",
    "delete",
    "network",
    "process_control",
    "privilege",
    "code_execution",
    "unknown",
]


@dataclass(frozen=True)
class CommandTargetProfile:
    kind: TargetKind
    trust_domain: str
    identity: str | None
    sandbox_strength: SandboxStrength
    read_roots: tuple[str, ...] = ()
    write_roots: tuple[str, ...] = ()
    working_directory: str | None = None
    network_allowed: bool | None = None
    privileged: bool = False
    connection_id: str | None = None


@dataclass(frozen=True)
class CommandRiskAssessment(RiskAssessment):
    effects: list[str] = field(default_factory=list)
    confidence: RiskConfidence = "low"
    referenced_paths: list[str] = field(default_factory=list)
    protected_resources: list[dict[str, str]] = field(default_factory=list)
    target: dict[str, Any] = field(default_factory=dict)
    boundary: dict[str, Any] = field(default_factory=dict)
    hard_blocked: bool = False

    def _audit_payload(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "effects": self.effects,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "referenced_paths": self.referenced_paths,
            "protected_resources": self.protected_resources,
            "target": self.target,
            "boundary": self.boundary,
            "hard_blocked": self.hard_blocked,
            "requires_explicit_approval": self.requires_explicit_approval,
        }

    def audit_snapshot(self) -> dict[str, Any]:
        snapshot = self._audit_payload()
        snapshot["assessment_fingerprint"] = self.assessment_fingerprint()
        return snapshot

    def assessment_fingerprint(self) -> str:
        payload = json.dumps(
            self._audit_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def assess_command_risk(
    command: str,
    *,
    target: CommandTargetProfile,
    requested_connection_id: str | None = None,
) -> CommandRiskAssessment:
    semantics = _analyze_command_semantics(command, target=target)
    level = semantics.level
    effects = _audit_effects(semantics.effects)
    assert semantics.sink_safety is not None
    assert semantics.execution_safety is not None
    sink_safety = semantics.sink_safety
    execution_safety = semantics.execution_safety
    referenced_paths = list(semantics.referenced_paths)
    protected_resources = list(semantics.protected_resources)
    reasons = [*semantics.reasons, f"command semantics classified as {level}"]
    hard_blocked = False

    if (
        target.kind == "remote_ssh"
        and requested_connection_id
        and requested_connection_id != target.connection_id
    ):
        hard_blocked = True
        reasons.append(
            "requested remote connection does not match the selected execution target"
        )

    if hard_blocked:
        reasons.append("the command matches a non-bypassable hard safety boundary")
        confidence: RiskConfidence = "high"
    else:
        confidence = semantics.confidence

    protected_write = bool(sink_safety.protected_paths)
    destructive_bif = _contains_destructive_bif_command(command)
    if destructive_bif:
        reasons.append("destructive bif commands require explicit user approval")
    if protected_write:
        reasons.append("the command mutates a protected resource")

    if sink_safety.requires_explicit_approval:
        reasons.extend(sink_safety.reasons)
    if execution_safety.requires_explicit_approval:
        reasons.extend(execution_safety.reasons)
    return CommandRiskAssessment(
        level=level,
        reasons=_bounded_strings(reasons),
        affected_resources=[
            {"type": "path", "id": path} for path in referenced_paths[:32]
        ],
        requires_explicit_approval=(
            level == "critical"
            or destructive_bif
            or protected_write
            or sink_safety.requires_explicit_approval
            or execution_safety.requires_explicit_approval
        ),
        effects=effects,
        confidence=confidence,
        referenced_paths=referenced_paths,
        protected_resources=protected_resources,
        target={
            "kind": target.kind,
            "trust_domain": target.trust_domain,
            "identity": target.identity,
            "connection_id": target.connection_id,
            "network_allowed": target.network_allowed,
            "privileged": target.privileged,
        },
        boundary={
            "enforced": target.sandbox_strength == "enforced",
            "sandbox_strength": target.sandbox_strength,
            "working_directory": target.working_directory,
        },
        hard_blocked=hard_blocked,
    )


_RANK: dict[RiskLevel, int] = {
    "read": 0,
    "act_low": 1,
    "external": 2,
    "act_high": 2,
    "destructive": 3,
    "critical": 4,
}

_READ_EXECUTABLES = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "pwd",
        "echo",
        "printf",
        "wc",
        "file",
        "stat",
        "tree",
        "printenv",
        "date",
        "whoami",
        "which",
        "type",
        "du",
        "df",
        "ps",
        "uname",
        "hostname",
        "basename",
        "dirname",
        "realpath",
        "readlink",
        "sort",
        "uniq",
        "cut",
        "tr",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "find",
        "fd",
        "jq",
        "yq",
        "diff",
        "comm",
        "column",
        "nl",
        "true",
        "false",
        "test",
        "id",
        "groups",
        "less",
        "more",
        "tldr",
        "man",
        "help",
        "history",
    }
)
_EXTERNAL_EXECUTABLES = frozenset(
    {
        "curl",
        "wget",
        "ssh",
        "scp",
        "sftp",
        "rsync",
        "nc",
        "ncat",
        "telnet",
        "ping",
        "dig",
        "nslookup",
        "host",
        "ftp",
    }
)
_INSTALL_EXECUTABLES = frozenset(
    {
        "pip",
        "pip3",
        "npm",
        "pnpm",
        "yarn",
        "bun",
        "uv",
        "apt",
        "apt-get",
        "yum",
        "dnf",
        "brew",
        "cargo",
        "go",
        "gem",
        "poetry",
        "conda",
        "mamba",
    }
)
_DESTRUCTIVE_EXECUTABLES = frozenset(
    {
        "rm",
        "rmdir",
        "shred",
        "truncate",
        "kill",
        "pkill",
        "killall",
        "chown",
        "chmod",
        "fdisk",
        "parted",
        "dd",
    }
)
_WRAPPERS = frozenset(
    {"env", "command", "exec", "nohup", "sudo", "timeout", "nice", "setsid"}
)
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "ash"})
_INLINE_INTERPRETER_PATTERNS = (
    ("python", re.compile(r"python(?:\d+(?:\.\d+)*)?")),
    ("python", re.compile(r"pypy(?:\d+(?:\.\d+)*)?")),
    ("node", re.compile(r"node(?:js)?(?:\d+(?:\.\d+)*)?")),
    ("ruby", re.compile(r"ruby(?:\d+(?:\.\d+)*)?")),
    ("perl", re.compile(r"perl(?:\d+(?:\.\d+)*)?")),
    ("php", re.compile(r"php(?:\d+(?:\.\d+)*)?")),
)
_TRUSTED_INTROSPECTION_FLAGS = {
    "python": frozenset({"--version", "-V", "--help", "-h"}),
    "node": frozenset({"--version", "-v", "--help", "-h"}),
    "ruby": frozenset({"--version", "-v", "--help", "-h"}),
    "perl": frozenset({"--version", "-v", "--help", "-h"}),
    "php": frozenset({"--version", "-v", "--help", "-h"}),
}
_SHUTDOWN_EXECUTABLES = frozenset({"shutdown", "reboot", "halt", "poweroff"})
_ROOTISH = frozenset({"/", "/*", "~", "$HOME", "${HOME}", ".."})

_GIT_EXTERNAL = frozenset({"push", "pull", "fetch", "clone", "submodule"})
_DOCKER_EXTERNAL = frozenset({"pull", "push", "login", "logout"})
_DOCKER_DESTRUCTIVE = frozenset({"rm", "rmi", "prune", "kill", "stop", "volume"})


@dataclass(frozen=True)
class _CommandNode:
    tokens: tuple[str, ...]
    operator_before: str | None = None


@dataclass(frozen=True)
class _ParsedCommand:
    text: str
    substitutions: tuple[str, ...]
    process_substitutions: tuple[str, ...]
    heredoc_bodies: tuple[str, ...]
    nodes: tuple[_CommandNode, ...]


@dataclass(frozen=True)
class _UnwrappedCommand:
    tokens: tuple[str, ...]
    elevated: bool = False
    confident: bool = True


@dataclass(frozen=True)
class _ShortOptionClusterMatch:
    matched: bool = False
    value: str | None = None
    ambiguous: bool = False


@dataclass(frozen=True)
class _NodeSemantics:
    level: RiskLevel
    effects: tuple[SemanticEffect, ...]
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CommandSemantics:
    level: RiskLevel
    effects: tuple[SemanticEffect, ...]
    confidence: RiskConfidence
    reasons: tuple[str, ...] = ()
    referenced_paths: tuple[str, ...] = ()
    path_analysis_confident: bool = True
    protected_resources: tuple[dict[str, str], ...] = ()
    sink_safety: _WriteSinkSafety | None = None
    execution_safety: _IndirectExecutionSafety | None = None


def _risk_floor_for_effects(effects: tuple[SemanticEffect, ...]) -> RiskLevel:
    """Reduce semantic effects to the minimum permissible risk level."""
    effect_set = set(effects)
    if effect_set & {"delete", "process_control", "privilege"}:
        return "destructive"
    if "network" in effect_set:
        return "external"
    if effect_set & {"write", "code_execution", "unknown"}:
        return "act_high"
    if "read" in effect_set:
        return "read"
    return "act_high"


def _audit_effects(effects: tuple[SemanticEffect, ...]) -> list[str]:
    """Map internal semantics onto the stable public audit vocabulary."""
    return _dedupe(
        [
            "execute" if effect in {"code_execution", "unknown"} else effect
            for effect in effects
        ]
    )


def classify_command_level(command: str) -> RiskLevel:
    """Return the semantic risk floor for a shell command string."""
    return _analyze_command_semantics(command).level


def _analyze_command_semantics(
    command: str,
    *,
    target: CommandTargetProfile | None = None,
) -> _CommandSemantics:
    """Produce the single semantic input consumed by command assessment."""
    parsed = _parse_command(command)
    semantics = _analyze_command_grammar(parsed)
    if target is None:
        return semantics

    nodes = list(parsed.nodes)
    sink_safety = _analyze_write_sink_safety(nodes)
    execution_safety = _analyze_indirect_execution_safety(parsed, target=target)
    referenced_paths, path_analysis_confident = _referenced_paths(
        nodes,
        target=target,
    )
    protected_resources = _protected_resources(
        [*referenced_paths, *sink_safety.protected_paths]
    )
    level = semantics.level
    reasons = list(semantics.reasons)
    unknown_path = any(_path_is_unresolved(path) for path in referenced_paths)
    outside_paths = [
        path
        for path in referenced_paths
        if not _path_is_unresolved(path)
        and not _path_within_roots(path, target.read_roots)
    ]
    if level in {"read", "act_low"} and (unknown_path or outside_paths):
        level = "act_high"
        if unknown_path:
            reasons.append(
                "a variable or home-relative path cannot be bounded statically"
            )
        if outside_paths:
            reasons.append("a referenced path is outside the target read roots")
    if (
        target.kind == "remote_ssh"
        and level in {"read", "act_low"}
        and not path_analysis_confident
    ):
        level = "act_high"
        reasons.append(
            "remote read option/path semantics cannot be proven safe statically"
        )

    if level == "critical":
        confidence: RiskConfidence = "high"
        reasons.append("the command requires explicit user approval")
    elif target.kind == "remote_ssh":
        confidence = "low" if unknown_path else "medium"
        reasons.append(
            "remote commands are bounded by the remote SSH account and server policy, not the working directory"
        )
    elif target.sandbox_strength == "enforced":
        confidence = "low" if unknown_path else "high"
        reasons.append("the local operating-system sandbox enforces the declared roots")
    else:
        confidence = "low" if unknown_path else "medium"
        reasons.append("the local command has no enforced operating-system sandbox")
    if sink_safety.low_confidence:
        confidence = "low"

    return replace(
        semantics,
        level=level,
        confidence=confidence,
        reasons=tuple(_dedupe(reasons)),
        referenced_paths=tuple(referenced_paths),
        path_analysis_confident=path_analysis_confident,
        protected_resources=tuple(protected_resources),
        sink_safety=sink_safety,
        execution_safety=execution_safety,
    )


def _parse_command(command: str) -> _ParsedCommand:
    text = (command or "").strip()
    command_substitutions = tuple(_command_substitutions(text))
    process_substitutions = tuple(_process_substitutions(text))
    heredoc_bodies = tuple(_heredoc_bodies(text))
    substitutions = (
        *command_substitutions,
        *process_substitutions,
        *heredoc_bodies,
    )
    return _ParsedCommand(
        text=text,
        substitutions=tuple(substitutions),
        process_substitutions=process_substitutions,
        heredoc_bodies=heredoc_bodies,
        nodes=tuple(_parse_command_nodes(_strip_heredoc_bodies(text))),
    )


def _analyze_command_grammar(parsed: _ParsedCommand) -> _CommandSemantics:
    """Adapt the established shell grammar into immutable semantics."""
    text = parsed.text
    if not text:
        return _CommandSemantics(
            level="act_low",
            effects=("unknown",),
            confidence="low",
            reasons=("empty command has no proven side effect",),
        )
    if _looks_like_fork_bomb(text):
        return _CommandSemantics(
            level="critical",
            effects=("process_control",),
            confidence="high",
            reasons=("fork bomb",),
        )
    substitutions = parsed.substitutions
    substitution_semantics = [
        _analyze_command_semantics(inner) for inner in substitutions
    ]
    substitution_effects: list[SemanticEffect] = (
        ["code_execution"] if substitutions else []
    )
    substitution_reasons: list[str] = []
    for nested in substitution_semantics:
        substitution_effects.extend(nested.effects)
        substitution_reasons.extend(nested.reasons)
    if any(nested.level == "critical" for nested in substitution_semantics):
        return _CommandSemantics(
            level="critical",
            effects=tuple(_dedupe(substitution_effects)),
            confidence="high",
            reasons=tuple(
                _dedupe(["critical dynamic shell source", *substitution_reasons])
            ),
        )

    nodes = list(parsed.nodes)
    if _compound_alias_targets_unsafe_device(nodes):
        return _CommandSemantics(
            level="critical",
            effects=("write",),
            confidence="high",
            reasons=("unsafe device write",),
        )
    if _dynamic_command_hardline(nodes) or _invoked_function_hardline(nodes):
        return _CommandSemantics(
            level="critical",
            effects=("code_execution",),
            confidence="high",
            reasons=("dynamic hardline command",),
        )

    introspection_proven = _is_proven_introspection_command(
        text,
        nodes,
        has_dynamic_source=bool(substitutions),
    )
    highest: RiskLevel = "act_high" if substitutions or "<(" in text else "read"
    for nested in substitution_semantics:
        if _RANK[nested.level] > _RANK[highest]:
            highest = nested.level
    effects: list[SemanticEffect] = list(substitution_effects)
    reasons: list[str] = list(substitution_reasons)
    previous: _CommandNode | None = None
    for index, node in enumerate(nodes):
        semantics = _inspect_node(
            node,
            introspection_proven=introspection_proven and index == 0,
        )
        effects.extend(semantics.effects)
        reasons.extend(semantics.reasons)
        if semantics.level == "critical":
            return _CommandSemantics(
                level="critical",
                effects=tuple(_dedupe(effects)) or ("unknown",),
                confidence="high",
                reasons=tuple(_dedupe(reasons)),
            )
        if (
            previous is not None
            and node.operator_before == "|"
            and _executable(previous.tokens) in {"curl", "wget"}
            and _is_shell_stdin_target(node.tokens)
        ):
            return _CommandSemantics(
                level="critical",
                effects=tuple(_dedupe([*effects, "network", "code_execution"])),
                confidence="high",
                reasons=("network source piped to shell",),
            )
        if (
            previous is not None
            and node.operator_before == "|"
            and _is_shell_stdin_target(node.tokens)
            and (source := _literal_shell_source(previous)) is not None
            and classify_command_level(source) == "critical"
        ):
            return _CommandSemantics(
                level="critical",
                effects=tuple(_dedupe([*effects, "code_execution"])),
                confidence="high",
                reasons=("critical literal source piped to shell",),
            )
        if _RANK[semantics.level] > _RANK[highest]:
            highest = semantics.level
        previous = node
    normalized_effects = tuple(_dedupe(effects)) or ("unknown",)
    return _CommandSemantics(
        level=_max_level(_risk_floor_for_effects(normalized_effects), highest),
        effects=normalized_effects,
        confidence="high" if introspection_proven else "medium",
        reasons=tuple(_dedupe(reasons)),
    )


def _inspect_node(
    node: _CommandNode,
    *,
    introspection_proven: bool = False,
) -> _NodeSemantics:
    if introspection_proven:
        return _NodeSemantics(
            level="act_low",
            effects=("read",),
            reasons=("trusted executable requested static version or help output",),
        )
    bif_semantics = _inspect_bif_command(node)
    if bif_semantics is not None:
        return bif_semantics
    return _inspect_legacy_behavior(node)


_BIF_GLOBAL_OPTIONS_WITH_VALUES = frozenset(
    {"--base-url", "--project", "-p", "--output"}
)
_BIF_GLOBAL_FLAGS = frozenset({"--no-color", "--quiet", "-q", "--verbose", "-v"})
_BIF_READ_COMMANDS = frozenset(
    {
        ("doctor",),
        ("project", "list"),
        ("project", "show"),
        ("workflow", "list"),
        ("workflow", "show"),
        ("workflow", "source"),
        ("run", "list"),
        ("run", "show"),
        ("run", "watch"),
        ("run", "logs"),
        ("run", "outputs", "list"),
        ("run", "batch", "show"),
        ("file", "ls"),
        ("file", "cat"),
        ("system", "health"),
        ("system", "stats"),
        ("system", "scheduler-status"),
        ("system", "scheduler-resources"),
        ("system", "gpu"),
        ("events", "stream"),
        ("config", "get"),
        ("config", "show"),
        ("connection", "list"),
        ("connection", "show"),
        ("connection", "test"),
        ("agent", "session", "list"),
        ("agent", "session", "show"),
        ("agent", "snapshot"),
    }
)
_BIF_WRITE_COMMANDS = frozenset(
    {
        ("project", "create"),
        ("project", "use"),
        ("workflow", "register"),
        ("workflow", "bind"),
        ("workflow", "pin"),
        ("run", "submit"),
        ("run", "wizard"),
        ("run", "retry"),
        ("run", "resume"),
        ("run", "batch", "submit"),
        ("run", "outputs", "download"),
        ("file", "download"),
        ("file", "upload"),
        ("file", "scan"),
        ("config", "init"),
        ("config", "set"),
        ("config", "unset"),
        ("config", "use-project"),
        ("connection", "create"),
        ("connection", "update"),
        ("agent", "session", "create"),
        ("agent", "send"),
        ("agent", "steer"),
        ("agent", "respond"),
    }
)
_BIF_DESTRUCTIVE_COMMANDS = frozenset(
    {
        ("project", "delete"),
        ("workflow", "unbind"),
        ("run", "cancel"),
        ("run", "cleanup"),
        ("run", "batch", "cancel"),
        ("file", "rm"),
        ("agent", "session", "delete"),
        ("agent", "cancel"),
        ("connection", "delete"),
    }
)


def _inspect_bif_command(node: _CommandNode) -> _NodeSemantics | None:
    """Classify the public ``bif`` business surface instead of shell syntax.

    The Agent receives a project-scoped credential, so a read-only ``bif``
    request is semantically a read even though the CLI uses HTTP underneath.
    Unknown commands are deliberately treated as destructive: adding a new CLI
    mutation must not silently bypass the Harness confirmation policy.
    """
    unwrapped = _unwrap_command_details(_strip_shell_control_tokens(list(node.tokens)))
    tokens = list(unwrapped.tokens)
    if not tokens or _basename(tokens[0]) != "bif":
        return None
    command = _bif_command_path(tokens[1:])
    if command is None:
        return _NodeSemantics(
            level="destructive",
            effects=("unknown",),
            reasons=("unrecognized bif command requires confirmation",),
        )
    if command in _BIF_READ_COMMANDS:
        return _NodeSemantics(
            level="read",
            effects=("read",),
            reasons=("bif query is read-only",),
        )
    if command in _BIF_WRITE_COMMANDS:
        return _NodeSemantics(
            level="act_high",
            effects=("write",),
            reasons=("bif command changes project state",),
        )
    if command in _BIF_DESTRUCTIVE_COMMANDS:
        return _NodeSemantics(
            level="destructive",
            effects=("delete",),
            reasons=("bif command deletes or stops managed state",),
        )
    return _NodeSemantics(
        level="destructive",
        effects=("unknown",),
        reasons=("unrecognized bif command requires confirmation",),
    )


def _contains_destructive_bif_command(command: str) -> bool:
    return any(
        semantics is not None and semantics.level == "destructive"
        for node in _parse_command(command).nodes
        if (semantics := _inspect_bif_command(node)) is not None
    )


def _bif_command_path(args: list[str]) -> tuple[str, ...] | None:
    index = 0
    while index < len(args):
        value = args[index]
        if value in {"--version", "-V", "--help", "-h"}:
            return ("doctor",)
        if value in _BIF_GLOBAL_FLAGS:
            index += 1
            continue
        if value in _BIF_GLOBAL_OPTIONS_WITH_VALUES:
            if index + 1 >= len(args):
                return None
            index += 2
            continue
        break
    words = args[index:]
    if not words:
        return None
    if any(value in {"--help", "-h"} for value in words):
        return ("doctor",)
    group = {
        "projects": "project",
        "workflows": "workflow",
        "runs": "run",
        "files": "file",
        "connections": "connection",
    }.get(words[0], words[0])
    if group == "doctor":
        return ("doctor",)
    if len(words) < 2:
        return None
    if group == "run" and words[1] in {"outputs", "batch"}:
        return (group, words[1], words[2]) if len(words) >= 3 else None
    if group == "agent" and words[1] == "session":
        return (group, words[1], words[2]) if len(words) >= 3 else None
    return (group, words[1])


def _is_proven_introspection_command(
    text: str,
    nodes: list[_CommandNode],
    *,
    has_dynamic_source: bool,
) -> bool:
    """Prove a single trusted executable can only emit version/help metadata."""
    if has_dynamic_source or len(nodes) != 1 or nodes[0].operator_before is not None:
        return False
    if _has_unquoted_shell_control_operator(text):
        return False
    raw_tokens = list(nodes[0].tokens)
    if any(token and set(token) <= {"<", ">"} for token in raw_tokens):
        return False
    if not raw_tokens:
        return False
    executable = raw_tokens[0]
    if "/" in executable or _basename(executable) != executable:
        return False
    family = _interpreter_family(executable)
    if family is None:
        return False
    allowed_flags = _TRUSTED_INTROSPECTION_FLAGS.get(family)
    args = raw_tokens[1:]
    return bool(allowed_flags and args and all(arg in allowed_flags for arg in args))


def _has_unquoted_shell_control_operator(text: str) -> bool:
    quote: str | None = None
    escaped = False
    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char in {";", "\n", "&", "|"}:
            return True
    return False


def _classify_node(node: _CommandNode) -> RiskLevel:
    env_split = _env_split_command(list(node.tokens))
    if env_split:
        return _classify_node(_CommandNode(tokens=tuple(env_split)))
    tokens, elevated = _unwrap_command(_strip_shell_control_tokens(list(node.tokens)))
    if not tokens:
        return "act_low"
    executable = _basename(tokens[0])
    args = tokens[1:]

    if executable in _SHELLS:
        command_arg = _shell_command_argument(args)
        if command_arg is not None:
            inner = classify_command_level(command_arg)
            return _max_level("destructive" if elevated else "read", inner)
    interpreter = _interpreter_family(executable)
    if interpreter is not None:
        inline_code = _interpreter_inline_code(interpreter, args)
        if inline_code is not None and _inline_code_contains_known_hardline(
            inline_code
        ):
            return "critical"
    if executable == "eval" and args:
        return classify_command_level(" ".join(args))
    if executable in _SHUTDOWN_EXECUTABLES:
        return "critical"
    if executable == "systemctl" and _systemctl_verb(args)[0] in _SHUTDOWN_EXECUTABLES:
        return "critical"
    if executable == "busybox":
        nested = _busybox_command(args)
        if nested:
            return _classify_node(_CommandNode(tokens=tuple(nested)))
    if executable == "init" and next(
        (arg for arg in args if not arg.startswith("-")), None
    ) in {"0", "6"}:
        return "critical"
    if any(
        _is_unsafe_device_write_target(destination)
        for destination in _write_sink_destinations(node)
    ):
        return "critical"
    if executable.startswith("mkfs"):
        targets = [arg for arg in args if not arg.startswith("-")]
        return (
            "critical"
            if any(_is_unsafe_device_write_target(path) for path in targets)
            else "destructive"
        )
    if executable == "rm" and _recursive_rm_targets_root(args):
        return "critical"
    if executable == "chmod" and _recursive_chmod_targets_root(args):
        return "critical"
    if executable == "xargs":
        nested = _xargs_command(args)
        if nested and _xargs_nested_is_hardline(nested):
            return "critical"
    if executable == "find" and _find_is_hardline(args):
        return "critical"

    has_write_redirect = _has_file_output_redirect(tokens)
    if elevated:
        return "destructive"
    if executable in _DESTRUCTIVE_EXECUTABLES:
        return "destructive"
    if executable in _EXTERNAL_EXECUTABLES or executable in _INSTALL_EXECUTABLES:
        return "external"
    if executable == "git":
        return _classify_git(args)
    if executable == "docker":
        return _classify_docker(args)
    if executable == "sort":
        if _has_output_option(args, {"-o", "--output"}):
            return "act_high"
        _, confident = _sort_file_arguments(args)
        return "act_low" if confident else "act_high"
    if executable == "diff":
        if _has_output_option(args, {"--output"}):
            return "act_high"
        _, confident = _diff_file_arguments(args)
        return "act_low" if confident else "act_high"
    if _is_read_only_platform_command(executable, args):
        return "act_low"
    if executable in {"sed", "perl"} and any(arg.startswith("-i") for arg in args):
        return "act_high"
    if executable == "find" and any(
        arg in {"-exec", "-execdir", "-ok", "-okdir", "-delete"} for arg in args
    ):
        return "act_high"
    if executable in _READ_EXECUTABLES:
        return "act_high" if has_write_redirect else "act_low"
    return "act_high"


def _parse_command_nodes(text: str) -> list[_CommandNode]:
    segments: list[tuple[str | None, str]] = []
    start = 0
    quote: str | None = None
    escaped = False
    operator_before: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        operator: str | None = None
        if char == "\n" or char == ";":
            operator = ";"
        elif char == "|" and index > 0 and text[index - 1] == ">":
            index += 1
            continue
        elif char == "&" and (
            (index > 0 and text[index - 1] in {"<", ">"})
            or (index + 1 < len(text) and text[index + 1] == ">")
        ):
            index += 1
            continue
        elif char in {"|", "&"}:
            operator = (
                char * 2 if index + 1 < len(text) and text[index + 1] == char else char
            )
        if operator is None:
            index += 1
            continue
        segments.append((operator_before, text[start:index]))
        operator_before = operator
        index += len(operator)
        start = index
    segments.append((operator_before, text[start:]))

    nodes: list[_CommandNode] = []
    for before, segment in segments:
        try:
            lexer = shlex.shlex(segment, posix=True, punctuation_chars="<>")
            lexer.whitespace_split = True
            lexer.commenters = ""
            tokens = tuple(lexer)
        except ValueError:
            tokens = tuple(segment.split())
        if tokens:
            nodes.append(_CommandNode(tokens=tokens, operator_before=before))
    return nodes


def _unwrap_command(tokens: list[str]) -> tuple[list[str], bool]:
    result = _unwrap_command_details(tokens)
    return list(result.tokens), result.elevated


def _short_option_cluster_match(
    arg: str,
    *,
    target: str,
    no_value_options: set[str],
    consuming_options: set[str],
    optional_value_options: dict[str, re.Pattern[str]] | None = None,
    allow_unknown_no_value: bool = False,
) -> _ShortOptionClusterMatch:
    if not arg.startswith("-") or arg.startswith("--") or arg == "-":
        return _ShortOptionClusterMatch()
    cluster = arg[1:]
    optional_values = optional_value_options or {}
    index = 0
    while index < len(cluster):
        option = cluster[index]
        if option == target:
            return _ShortOptionClusterMatch(
                matched=True,
                value=cluster[index + 1 :] or None,
            )
        if option in consuming_options:
            return _ShortOptionClusterMatch()
        optional_value = optional_values.get(option)
        if optional_value is not None:
            match = optional_value.match(cluster, index + 1)
            if match is not None:
                index = match.end()
            else:
                index += 1
            continue
        if option not in no_value_options and not allow_unknown_no_value:
            return _ShortOptionClusterMatch(ambiguous=True)
        index += 1
    return _ShortOptionClusterMatch()


def _env_split_command(tokens: list[str]) -> list[str] | None:
    if not tokens or _basename(tokens[0]) != "env":
        return None
    index = 1
    while index < len(tokens):
        arg = tokens[index]
        if arg in {"-S", "--split-string"}:
            if index + 1 >= len(tokens):
                return []
            try:
                split = shlex.split(tokens[index + 1])
            except ValueError:
                return []
            return [*split, *tokens[index + 2 :]]
        env_cluster = _short_option_cluster_match(
            arg,
            target="S",
            no_value_options={"0", "i", "v"},
            consuming_options={"C", "u"},
        )
        if env_cluster.matched:
            split_source = env_cluster.value
            remaining = tokens[index + 1 :]
            if split_source is None:
                if not remaining:
                    return []
                split_source = remaining[0]
                remaining = remaining[1:]
            try:
                split = shlex.split(split_source)
            except ValueError:
                return []
            return [*split, *remaining]
        if env_cluster.ambiguous and "S" in arg[1:]:
            return []
        if arg.startswith("--split-string="):
            try:
                split = shlex.split(arg.split("=", 1)[1])
            except ValueError:
                return []
            return [*split, *tokens[index + 1 :]]
        if arg in {"-u", "--unset", "-C", "--chdir"}:
            index += 2
            continue
        if arg.startswith(("--unset=", "--chdir=")):
            index += 1
            continue
        if arg.startswith("-") or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", arg):
            index += 1
            continue
        break
    return None


def _unwrap_command_details(tokens: list[str]) -> _UnwrappedCommand:
    elevated = False
    confident = True
    while tokens:
        while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
            tokens.pop(0)
        if not tokens:
            break
        executable = _basename(tokens[0])
        if executable not in _WRAPPERS:
            break
        tokens.pop(0)
        if executable == "sudo":
            elevated = True
            tokens, wrapper_confident = _skip_wrapper_options(
                tokens,
                no_value={
                    "-A",
                    "--askpass",
                    "-b",
                    "--background",
                    "-E",
                    "--preserve-env",
                    "-H",
                    "--set-home",
                    "-K",
                    "--remove-timestamp",
                    "-k",
                    "--reset-timestamp",
                    "-n",
                    "--non-interactive",
                    "-P",
                    "--preserve-groups",
                    "-S",
                    "--stdin",
                },
                value_options={
                    "-u",
                    "--user",
                    "-g",
                    "--group",
                    "-h",
                    "--host",
                    "-p",
                    "--prompt",
                    "-C",
                    "--close-from",
                    "-T",
                    "--command-timeout",
                    "-R",
                    "--chroot",
                    "-D",
                    "--chdir",
                },
            )
            confident = confident and wrapper_confident
        elif executable == "env":
            if any(
                arg == "-S"
                or _short_option_cluster_match(
                    arg,
                    target="S",
                    no_value_options={"0", "i", "v"},
                    consuming_options={"C", "u"},
                ).matched
                or arg == "--split-string"
                or arg.startswith("--split-string=")
                for arg in tokens
            ):
                confident = False
            tokens, wrapper_confident = _skip_wrapper_options(
                tokens,
                no_value={
                    "-i",
                    "--ignore-environment",
                    "-0",
                    "--null",
                    "-v",
                    "--debug",
                },
                value_options={
                    "-u",
                    "--unset",
                    "-C",
                    "--chdir",
                    "-S",
                    "--split-string",
                },
            )
            confident = confident and wrapper_confident
            while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
                tokens.pop(0)
        elif executable == "timeout":
            tokens, wrapper_confident = _skip_wrapper_options(
                tokens,
                no_value={"--foreground", "--preserve-status", "-v", "--verbose"},
                value_options={"-s", "--signal", "-k", "--kill-after"},
            )
            confident = confident and wrapper_confident
            if tokens:
                tokens.pop(0)
        elif executable == "nice":
            if tokens and re.fullmatch(r"-\d+", tokens[0]):
                tokens.pop(0)
            else:
                tokens, wrapper_confident = _skip_wrapper_options(
                    tokens,
                    no_value=set(),
                    value_options={"-n", "--adjustment"},
                )
                confident = confident and wrapper_confident
        elif executable == "setsid":
            tokens, wrapper_confident = _skip_wrapper_options(
                tokens,
                no_value={"-c", "--ctty", "-f", "--fork", "-w", "--wait"},
                value_options=set(),
            )
            confident = confident and wrapper_confident
        elif executable == "command":
            if tokens[:1] and tokens[0] in {"-v", "-V"}:
                query = tokens[1:2]
                return _UnwrappedCommand(
                    tokens=tuple(["type", *query]),
                    elevated=elevated,
                    confident=confident,
                )
            tokens, wrapper_confident = _skip_wrapper_options(
                tokens,
                no_value={"-p"},
                value_options=set(),
            )
            confident = confident and wrapper_confident
        elif executable == "nohup":
            tokens, wrapper_confident = _skip_wrapper_options(
                tokens,
                no_value=set(),
                value_options=set(),
            )
            confident = confident and wrapper_confident
        elif executable == "exec":
            tokens, wrapper_confident = _skip_wrapper_options(
                tokens,
                no_value={"-c", "-l"},
                value_options={"-a"},
            )
            confident = confident and wrapper_confident
    return _UnwrappedCommand(
        tokens=tuple(tokens), elevated=elevated, confident=confident
    )


def _skip_wrapper_options(
    tokens: list[str],
    *,
    no_value: set[str],
    value_options: set[str],
) -> tuple[list[str], bool]:
    index = 0
    confident = True
    while index < len(tokens):
        option = tokens[index]
        if option == "--":
            index += 1
            break
        if not option.startswith("-") or option == "-":
            break
        if "=" in option and option.split("=", 1)[0] in value_options:
            index += 1
            continue
        if option in no_value:
            index += 1
            continue
        if option not in value_options:
            confident = False
            index += 1
            continue
        index += 1
        if index < len(tokens):
            index += 1
        else:
            confident = False
    return tokens[index:], confident


def _shell_command_argument(args: list[str]) -> str | None:
    for index, arg in enumerate(args):
        if arg in {"-c", "-lc", "-ic"} and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith("-") and "c" in arg[1:] and index + 1 < len(args):
            return args[index + 1]
    return None


def _interpreter_inline_code(executable: str, args: list[str]) -> str | None:
    flags = {"-c"}
    if executable == "node":
        flags = {"-e", "--eval", "-p", "--print"}
    elif executable == "ruby":
        flags = {"-e"}
    elif executable == "perl":
        flags = {"-e", "-E"}
    elif executable == "php":
        flags = {"-r", "-B", "-R", "-F", "-E"}
    for index, arg in enumerate(args):
        if arg in flags and index + 1 < len(args):
            return args[index + 1]
        if executable == "perl" and arg.startswith("-"):
            bundled = _short_option_cluster_match(
                arg,
                target="e",
                no_value_options={
                    "a",
                    "c",
                    "d",
                    "f",
                    "n",
                    "p",
                    "s",
                    "S",
                    "t",
                    "T",
                    "u",
                    "U",
                    "w",
                    "W",
                    "X",
                },
                consuming_options={"F", "I", "M", "V", "i", "m", "x"},
                optional_value_options={
                    "0": re.compile(r"(?:x[0-9A-Fa-f]+|[0-7]*)"),
                    "l": re.compile(r"[0-7]*"),
                },
            )
            if not bundled.matched:
                bundled = _short_option_cluster_match(
                    arg,
                    target="E",
                    no_value_options={
                        "a",
                        "c",
                        "d",
                        "f",
                        "n",
                        "p",
                        "s",
                        "S",
                        "t",
                        "T",
                        "u",
                        "U",
                        "w",
                        "W",
                        "X",
                    },
                    consuming_options={"F", "I", "M", "V", "i", "m", "x"},
                    optional_value_options={
                        "0": re.compile(r"(?:x[0-9A-Fa-f]+|[0-7]*)"),
                        "l": re.compile(r"[0-7]*"),
                    },
                )
            if bundled.matched:
                if bundled.value:
                    return bundled.value
                if index + 1 < len(args):
                    return args[index + 1]
                return ""
            if bundled.ambiguous:
                return ""
        if executable == "ruby" and arg.startswith("-"):
            bundled = _short_option_cluster_match(
                arg,
                target="e",
                no_value_options={
                    "S",
                    "U",
                    "a",
                    "c",
                    "d",
                    "l",
                    "n",
                    "p",
                    "s",
                    "v",
                    "w",
                    "y",
                },
                consuming_options={
                    "C",
                    "E",
                    "F",
                    "I",
                    "i",
                    "r",
                    "x",
                },
                optional_value_options={
                    "0": re.compile(r"[0-7]*"),
                    "K": re.compile(r"[eEsSuUnNaA]?"),
                    "T": re.compile(r"[0-9]*"),
                    "W": re.compile(r"(?:[0-2]|:[A-Za-z][A-Za-z0-9_-]*)?"),
                },
            )
            if bundled.matched:
                if bundled.value:
                    return bundled.value
                if index + 1 < len(args):
                    return args[index + 1]
                return ""
            if bundled.ambiguous:
                return ""
        if executable == "node" and any(
            arg.startswith(f"{flag}=") for flag in {"--eval", "--print"}
        ):
            return arg.split("=", 1)[1]
        if executable == "python" and arg.startswith("-c") and arg != "-c":
            return arg[2:]
        if executable == "ruby" and arg.startswith("-e") and arg != "-e":
            return arg[2:]
        if executable == "php" and arg[:2] in {"-r", "-B", "-R", "-F", "-E"}:
            if len(arg) > 2:
                return arg[2:]
    return None


def _interpreter_family(executable: str) -> str | None:
    for family, pattern in _INLINE_INTERPRETER_PATTERNS:
        if pattern.fullmatch(executable):
            return family
    return None


def _inline_code_contains_known_hardline(code: str) -> bool:
    call_pattern = re.compile(
        r"(?:\bos\s*\.\s*system|\bsystem|\bexec(?:v|ve|vp|vpe)?|"
        r"\bsubprocess\s*\.\s*(?:run|call|check_call|check_output|Popen)|"
        r"(?:\bchild_process|require\s*\(\s*['\"]child_process['\"]\s*\))"
        r"\s*\.\s*(?:exec|execSync|spawn|spawnSync))"
        r"\s*\(([^)]*)\)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in call_pattern.finditer(code):
        literals = [
            value for _quote, value in re.findall(r"(['\"])(.*?)\1", match.group(1))
        ]
        if literals and classify_command_level(" ".join(literals)) == "critical":
            return True
    return False


def _systemctl_verb(args: list[str]) -> tuple[str | None, bool]:
    remaining, confident = _skip_wrapper_options(
        list(args),
        no_value={
            "--ask-password",
            "--no-ask-password",
            "--no-block",
            "--no-legend",
            "--no-pager",
            "--no-wall",
            "--quiet",
            "-q",
            "--runtime",
            "--system",
            "--user",
        },
        value_options={
            "-H",
            "--host",
            "-M",
            "--machine",
            "--root",
            "--image",
            "-t",
            "--type",
            "--state",
            "-p",
            "--property",
        },
    )
    return (remaining[0] if remaining else None), confident


_SHELL_CONTROL_WORDS = frozenset(
    {
        "if",
        "then",
        "elif",
        "else",
        "fi",
        "while",
        "until",
        "for",
        "select",
        "do",
        "done",
        "case",
        "esac",
        "{",
        "}",
    }
)
_SHELL_COMMAND_PREFIX_WORDS = frozenset(
    {"if", "then", "elif", "else", "while", "until", "do", "{"}
)


def _strip_shell_control_tokens(tokens: list[str]) -> list[str]:
    normalized = list(tokens)
    while normalized and normalized[0] in _SHELL_COMMAND_PREFIX_WORDS:
        normalized.pop(0)
    grouped = bool(normalized and normalized[0].startswith("("))
    if grouped:
        normalized[0] = normalized[0][1:]
    while normalized and normalized[-1] in _SHELL_CONTROL_WORDS:
        normalized.pop()
    if grouped and normalized and normalized[-1].endswith(")"):
        normalized[-1] = normalized[-1][:-1]
    return [token for token in normalized if token]


def _literal_shell_source(node: _CommandNode) -> str | None:
    tokens, _ = _unwrap_command(list(node.tokens))
    if not tokens:
        return None
    executable = _basename(tokens[0])
    args = tokens[1:]
    if executable not in {"echo", "printf"} or not args:
        return None
    if args[:1] == ["--"]:
        args = args[1:]
    if not args or any(arg.startswith("-") for arg in args):
        return None
    if executable == "printf" and "%" in args[0]:
        return None
    if any(any(marker in arg for marker in ("$", "`")) for arg in args):
        return None
    return " ".join(args)


def _is_shell_stdin_target(tokens: tuple[str, ...]) -> bool:
    unwrapped, _ = _unwrap_command(list(tokens))
    if not unwrapped:
        return False
    executable = _basename(unwrapped[0])
    if executable in _SHELLS:
        return True
    if executable != "busybox":
        return False
    nested = _busybox_command(unwrapped[1:])
    return bool(nested and _basename(nested[0]) in _SHELLS)


def _assignment_values(node: _CommandNode) -> dict[str, str] | None:
    values: dict[str, str] = {}
    for token in node.tokens:
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", token)
        if match is None:
            return None
        values[match.group(1)] = match.group(2)
    return values or None


def _resolve_dynamic_command_word(word: str, variables: dict[str, str]) -> str | None:
    if not word.startswith("$"):
        return None
    unresolved = False

    def replace(match: re.Match[str]) -> str:
        nonlocal unresolved
        name = match.group(1) or match.group(2)
        value = variables.get(name)
        if value is None:
            unresolved = True
            return ""
        return value

    resolved = re.sub(
        r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)",
        replace,
        word,
    )
    return None if unresolved or "$" in resolved else resolved


def _dynamic_command_hardline(nodes: list[_CommandNode]) -> bool:
    variables: dict[str, str] = {}
    for node in nodes:
        assignments = _assignment_values(node)
        if assignments is not None:
            variables.update(assignments)
            continue
        tokens, _ = _unwrap_command(_strip_shell_control_tokens(list(node.tokens)))
        if not tokens:
            continue
        resolved = _resolve_dynamic_command_word(tokens[0], variables)
        if resolved and classify_command_level(resolved) == "critical":
            return True
    return False


def _has_dynamic_command_execution(nodes: list[_CommandNode]) -> bool:
    for node in nodes:
        tokens, _ = _unwrap_command(_strip_shell_control_tokens(list(node.tokens)))
        if tokens and tokens[0].startswith("$"):
            return True
    return False


def _function_definitions(nodes: list[_CommandNode]) -> dict[str, str]:
    definitions: dict[str, str] = {}
    for node in nodes:
        if not node.tokens:
            continue
        tokens = list(node.tokens)
        name: str | None = None
        body_start = 0
        if tokens[0] == "function" and len(tokens) > 1:
            candidate = tokens[1]
            if candidate.endswith("()"):
                candidate = candidate[:-2]
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
                name = candidate
                body_start = 2
        else:
            match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\(\)\{?", tokens[0])
            if match is not None:
                name = match.group(1)
                body_start = 1
            elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tokens[0]) and tokens[1:2] == [
                "()"
            ]:
                name = tokens[0]
                body_start = 2
            elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tokens[0]) and tokens[1:3] == [
                "(",
                ")",
            ]:
                name = tokens[0]
                body_start = 3
        if name is None:
            continue
        if tokens[body_start : body_start + 1] == ["()"]:
            body_start += 1
        elif tokens[body_start : body_start + 2] == ["(", ")"]:
            body_start += 2
        if tokens[body_start : body_start + 1] == ["{"]:
            body_start += 1
        body = _strip_shell_control_tokens(tokens[body_start:])
        definitions[name] = " ".join(body)
    return definitions


def _invoked_function_hardline(nodes: list[_CommandNode]) -> bool:
    definitions = _function_definitions(nodes)
    if not definitions:
        return False
    for node in nodes:
        if not node.tokens:
            continue
        body = definitions.get(_basename(node.tokens[0]))
        if body and classify_command_level(body) == "critical":
            return True
    return False


def _busybox_command(args: list[str]) -> list[str]:
    index = 0
    while index < len(args) and args[index].startswith("-"):
        if args[index] in {"--help", "--list", "--list-full", "--install"}:
            return []
        index += 1
    return args[index:]


def _has_output_option(args: list[str], options: set[str]) -> bool:
    return bool(_output_option_destinations(args, options))


def _has_file_output_redirect(tokens: list[str]) -> bool:
    return any(
        _redirect_path_token(tokens, index) is not None
        for index, token in enumerate(tokens)
        if token in {">", ">>"}
    )


def _redirect_path_token(tokens: list[str], index: int) -> str | None:
    if index + 1 >= len(tokens):
        return "$UNRESOLVED_MISSING_OUTPUT"
    if tokens[index + 1] == "|":
        return tokens[index + 2] if index + 2 < len(tokens) else None
    if tokens[index + 1] == "&":
        if index + 2 >= len(tokens):
            return "$UNRESOLVED_MISSING_OUTPUT"
        candidate = tokens[index + 2]
        if _is_fd_duplication_word(candidate, after_ampersand=True):
            return None
        return candidate
    candidate = tokens[index + 1]
    return None if _is_fd_duplication_word(candidate) else candidate


def _is_fd_duplication_word(value: str, *, after_ampersand: bool = False) -> bool:
    pattern = r"(?:\d+|-)" if after_ampersand else r"&(?:\d+|-)"
    return bool(re.fullmatch(pattern, value))


def _output_option_destinations(args: list[str], options: set[str]) -> list[str]:
    destinations: list[str] = []
    for index, arg in enumerate(args):
        if arg in options:
            destinations.append(
                args[index + 1]
                if index + 1 < len(args)
                else "$UNRESOLVED_MISSING_OUTPUT"
            )
            continue
        for option in options:
            if option.startswith("--") and arg.startswith(f"{option}="):
                destinations.append(
                    arg.split("=", 1)[1] or "$UNRESOLVED_MISSING_OUTPUT"
                )
            elif (
                option.startswith("-")
                and not option.startswith("--")
                and arg.startswith(option)
                and arg != option
            ):
                destinations.append(arg[len(option) :])
    return _dedupe(destinations)


def _recursive_rm_targets_root(args: list[str]) -> bool:
    recursive = False
    targets: list[str] = []
    options_done = False
    for arg in args:
        if not options_done and arg == "--":
            options_done = True
            continue
        if not options_done and arg.startswith("--"):
            recursive = recursive or arg == "--recursive"
            continue
        if not options_done and arg.startswith("-"):
            recursive = recursive or "r" in arg.lower()
            continue
        targets.append(arg)
    return recursive and any(_rootish_path(target) for target in targets)


def _recursive_chmod_targets_root(args: list[str]) -> bool:
    recursive = any(
        arg == "--recursive" or (arg.startswith("-") and "R" in arg) for arg in args
    )
    return recursive and any(
        _rootish_path(arg) for arg in args if not arg.startswith("-")
    )


def _rootish_path(value: str) -> bool:
    if value in _ROOTISH:
        return True
    if value.startswith("/"):
        normalized = posixpath.normpath("/" + value.lstrip("/"))
        return normalized == "/"
    return False


_SAFE_DEVICE_WRITE_TARGETS = frozenset(
    {"/dev/null", "/dev/zero", "/dev/stdout", "/dev/stderr", "/dev/tty"}
)


def _is_unresolved_sink_path(path: str) -> bool:
    return path.startswith("~") or any(
        marker in path for marker in ("$", "`", "*", "?", "[", "]")
    )


def _is_sensitive_pseudo_device_target(path: str) -> bool:
    normalized = posixpath.normpath(path)
    return normalized in {"/dev/shm", "/dev/pts"} or normalized.startswith(
        ("/dev/shm/", "/dev/pts/")
    )


def _is_unsafe_device_write_target(path: str) -> bool:
    if _is_unresolved_sink_path(path):
        return False
    normalized = posixpath.normpath(path)
    if normalized != "/dev" and not normalized.startswith("/dev/"):
        return False
    if normalized in _SAFE_DEVICE_WRITE_TARGETS:
        return False
    if _is_sensitive_pseudo_device_target(normalized):
        return False
    if re.fullmatch(r"/dev/fd/\d+", normalized):
        return False
    return True


@dataclass(frozen=True)
class _WriteSinkSafety:
    requires_explicit_approval: bool = False
    low_confidence: bool = False
    reasons: tuple[str, ...] = ()
    protected_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class _IndirectExecutionSafety:
    requires_explicit_approval: bool = False
    reasons: tuple[str, ...] = ()


def _analyze_indirect_execution_safety(
    parsed: _ParsedCommand,
    *,
    target: CommandTargetProfile,
) -> _IndirectExecutionSafety:
    nodes = list(parsed.nodes)
    reasons: list[str] = []
    if parsed.process_substitutions:
        reasons.append(
            "process substitution is indirect shell execution and requires explicit approval"
        )
    if parsed.heredoc_bodies:
        reasons.append(
            "heredoc input can supply executable shell source and requires explicit approval"
        )
    if _has_dynamic_command_execution(nodes):
        reasons.append(
            "dynamic command-name expansion cannot be proven safe and requires explicit approval"
        )
    if _function_definitions(nodes):
        reasons.append(
            "shell function execution cannot be proven safe and requires explicit approval"
        )
    for node in nodes:
        unwrapped = _unwrap_command_details(
            _strip_shell_control_tokens(list(node.tokens))
        )
        tokens = list(unwrapped.tokens)
        if not unwrapped.confident:
            reasons.append(
                "wrapper option semantics cannot be proven safe and require explicit approval"
            )
        if not tokens:
            continue
        if _node_has_shell_control_syntax(
            node
        ) and not _remote_read_only_control_node_allowed(node, target):
            reasons.append(
                "compound shell syntax cannot be proven safe and requires explicit approval"
            )
        executable = _basename(tokens[0])
        args = tokens[1:]
        if node.operator_before == "|" and _is_shell_stdin_target(node.tokens):
            reasons.append(
                "piping generated source into a shell requires explicit approval"
            )
        if executable in _SHELLS:
            command_arg = _shell_command_argument(args)
            if command_arg is not None and (
                _is_unresolved_inline_code(command_arg)
                or _contains_danger_literal(command_arg)
            ):
                reasons.append(
                    "unproven shell -c source or danger literal requires explicit approval"
                )
            elif command_arg is not None and _function_definitions(
                _parse_command_nodes(command_arg)
            ):
                reasons.append(
                    "shell -c function execution cannot be proven safe and requires explicit approval"
                )
        elif (interpreter := _interpreter_family(executable)) is not None:
            inline_code = _interpreter_inline_code(interpreter, args)
            if inline_code is not None and _inline_interpreter_requires_approval(
                inline_code,
                interpreter=interpreter,
                args=args,
                target=target,
            ):
                reasons.append(
                    "inline interpreter source cannot be proven side-effect free"
                )
        elif executable == "xargs":
            nested = _xargs_command(args)
            if nested:
                nested_level = classify_command_level(" ".join(nested))
                nested_executable = _basename(nested[0])
                if (
                    nested_level == "destructive"
                    or nested_executable in _SHELLS
                    or _interpreter_family(nested_executable) is not None
                ):
                    reasons.append(
                        "xargs supplies an indirect runtime target to an elevated command"
                    )
                elif _env_split_command(nested) is not None:
                    reasons.append(
                        "xargs delegates through env split-string execution and requires explicit approval"
                    )
        elif executable == "find":
            for nested in _find_nested_commands(args):
                nested_tokens, _ = _unwrap_command(list(nested))
                nested_executable = _basename(nested_tokens[0]) if nested_tokens else ""
                if (
                    nested_executable in _SHELLS
                    or _interpreter_family(nested_executable) is not None
                    or _env_split_command(list(nested)) is not None
                ):
                    reasons.append(
                        "find delegates to an indirect runtime target and requires explicit approval"
                    )
        elif executable == "systemctl" and not _systemctl_verb(args)[1]:
            reasons.append(
                "systemctl option semantics cannot be proven safe and require explicit approval"
            )
    return _IndirectExecutionSafety(
        requires_explicit_approval=bool(reasons),
        reasons=tuple(_dedupe(reasons)),
    )


def _node_has_shell_control_syntax(node: _CommandNode) -> bool:
    if not node.tokens:
        return False
    first = node.tokens[0]
    return (
        first in _SHELL_CONTROL_WORDS or first.startswith("(") or first.startswith("{")
    )


def _remote_read_only_control_node_allowed(
    node: _CommandNode, target: CommandTargetProfile
) -> bool:
    if target.kind != "remote_ssh" or not node.tokens:
        return False
    first = node.tokens[0]
    if first.startswith(("(", "{")):
        return False
    stripped = _strip_shell_control_tokens(list(node.tokens))
    if not stripped:
        return True
    if any("$(" in token or "`" in token for token in stripped):
        return False
    if first == "for":
        return len(stripped) >= 4 and stripped[2] == "in"
    executable = _basename(stripped[0])
    args = stripped[1:]
    if executable in {"[", "test"}:
        return True
    if executable not in _READ_EXECUTABLES and not _is_read_only_platform_command(
        executable, args
    ):
        return False
    if _node_writes(stripped, executable, args):
        return False
    return (
        _RANK[_classify_node(_CommandNode(tokens=tuple(stripped)))] <= _RANK["act_low"]
    )


def _is_unresolved_inline_code(code: str) -> bool:
    stripped = code.strip()
    return not stripped or any(marker in stripped for marker in ("$", "`", "$("))


def _inline_interpreter_requires_approval(
    code: str,
    *,
    interpreter: str,
    args: list[str],
    target: CommandTargetProfile,
) -> bool:
    if (
        _is_unresolved_inline_code(code)
        or _contains_danger_literal(code)
        or _inline_code_contains_known_hardline(code)
    ):
        return True
    return not (
        target.kind == "remote_ssh"
        and interpreter == "python"
        and _uses_separate_inline_flag(args, flag="-c")
    )


def _uses_separate_inline_flag(args: list[str], *, flag: str) -> bool:
    return any(arg == flag and index + 1 < len(args) for index, arg in enumerate(args))


def _contains_danger_literal(code: str) -> bool:
    return bool(
        re.search(
            r"(?:^|[^A-Za-z0-9_])(?:shutdown|reboot|halt|poweroff|mkfs(?:\.[A-Za-z0-9_+-]+)?)(?:$|[^A-Za-z0-9_])",
            code,
            re.IGNORECASE,
        )
        or re.search(r"\brm\b[^\n]{0,80}\s-(?:[^\s]*r[^\s]*f|[^\s]*f[^\s]*r)\b", code)
    )


def _analyze_write_sink_safety(nodes: list[_CommandNode]) -> _WriteSinkSafety:
    aliases: dict[str, str] = {}
    requires_explicit = False
    low_confidence = False
    reasons: list[str] = []
    protected_paths: list[str] = []
    for node in nodes:
        tokens, _ = _unwrap_command(list(node.tokens))
        executable = _basename(tokens[0]) if tokens else ""
        args = tokens[1:]
        if _archive_extracts(executable, args):
            requires_explicit = True
            low_confidence = True
            reasons.append(
                "archive members cannot be proven to avoid protected destinations"
            )
        symlink = _symlink_binding(node)
        if symlink is not None:
            link, target = symlink
            protected_paths.extend(
                item["path"] for item in _protected_resources([link])
            )
            if _is_unresolved_sink_path(link):
                requires_explicit = True
                low_confidence = True
                reasons.append(
                    "indirect or unresolved link destination requires explicit approval"
                )
            aliases[_alias_key(link)] = _resolve_alias_target(
                _symlink_target_path(link, target), aliases
            )
            continue
        destinations = _write_sink_destinations(node)
        for destination in destinations:
            resolved_destination = _resolve_alias_target(destination, aliases)
            protected_paths.extend(
                item["path"] for item in _protected_resources([resolved_destination])
            )
            if _is_unresolved_sink_path(resolved_destination):
                requires_explicit = True
                low_confidence = True
                if resolved_destination != destination:
                    reasons.append(
                        "write destination follows a symlink with an unresolved target"
                    )
                else:
                    reasons.append(
                        "indirect or unresolved write destination requires explicit approval"
                    )
            if _is_sensitive_pseudo_device_target(resolved_destination):
                requires_explicit = True
                if resolved_destination != destination:
                    reasons.append(
                        "write destination follows a symlink into a sensitive pseudo-device subtree"
                    )
                else:
                    reasons.append(
                        "write destination is in a sensitive non-block device subtree"
                    )
        if not destinations:
            potential_paths = _unknown_mutator_protected_paths(node)
            if potential_paths:
                protected_paths.extend(potential_paths)
                requires_explicit = True
                low_confidence = True
                reasons.append(
                    "an unknown non-read command may mutate an explicit protected path"
                )
    return _WriteSinkSafety(
        requires_explicit_approval=requires_explicit,
        low_confidence=low_confidence,
        reasons=tuple(_dedupe(reasons)),
        protected_paths=tuple(_dedupe(protected_paths)),
    )


def _compound_alias_targets_unsafe_device(nodes: list[_CommandNode]) -> bool:
    aliases: dict[str, str] = {}
    for node in nodes:
        symlink = _symlink_binding(node)
        if symlink is not None:
            link, target = symlink
            aliases[_alias_key(link)] = _resolve_alias_target(
                _symlink_target_path(link, target), aliases
            )
            continue
        for destination in _write_sink_destinations(node):
            target = _resolve_alias_target(destination, aliases)
            if target != destination and _is_unsafe_device_write_target(target):
                return True
    return False


def _alias_key(path: str) -> str:
    return path if _is_unresolved_sink_path(path) else posixpath.normpath(path)


def _resolve_alias_target(path: str, aliases: dict[str, str]) -> str:
    current = path
    seen: set[str] = set()
    while True:
        key = _alias_key(current)
        if key in seen:
            return "$UNRESOLVED_SYMLINK_CYCLE"
        seen.add(key)
        target = aliases.get(key)
        if target is None:
            return current
        current = target


def _symlink_target_path(link: str, target: str) -> str:
    if target.startswith(("/", "~", "$")) or _is_unresolved_sink_path(target):
        return target
    parent = posixpath.dirname(link)
    return posixpath.normpath(posixpath.join(parent, target)) if parent else target


def _symlink_binding(node: _CommandNode) -> tuple[str, str] | None:
    tokens, _ = _unwrap_command(list(node.tokens))
    if not tokens or _basename(tokens[0]) != "ln":
        return None
    args = tokens[1:]
    if not any(
        arg == "--symbolic" or (arg.startswith("-") and "s" in arg) for arg in args
    ):
        return None
    positional = [arg for arg in args if not arg.startswith("-")]
    if len(positional) != 2:
        return None
    target, link = positional
    return link, target


def _write_sink_destinations(node: _CommandNode) -> list[str]:
    tokens, _ = _unwrap_command(list(node.tokens))
    if not tokens:
        return []
    destinations: list[str] = []
    for index, token in enumerate(tokens):
        if token not in {">", ">>"}:
            continue
        redirected = _redirect_path_token(tokens, index)
        if redirected is not None:
            destinations.append(redirected)
    executable = _basename(tokens[0])
    args = tokens[1:]
    before_redirect = args[:]
    for marker in (">", ">>", "<", "<<"):
        if marker in before_redirect:
            before_redirect = before_redirect[: before_redirect.index(marker)]
    positional = [arg for arg in before_redirect if not arg.startswith("-")]
    if executable == "tee":
        destinations.extend(positional)
    elif executable in {"cp", "install", "mv"}:
        destinations.extend(_copy_move_destinations(executable, args))
    elif executable == "dd":
        destinations.extend(
            arg.split("=", 1)[1] for arg in args if arg.startswith("of=")
        )
    elif executable.startswith("mkfs"):
        destinations.extend(positional)
    elif executable in {"shred", "truncate"}:
        destinations.extend(positional)
    elif executable in {"sed", "perl"} and any(arg.startswith("-i") for arg in args):
        destinations.extend(_editor_file_arguments(args))
    elif executable == "sort":
        destinations.extend(_output_option_destinations(args, {"-o", "--output"}))
    elif executable == "diff":
        destinations.extend(_output_option_destinations(args, {"--output"}))
    elif executable == "git" and args[:1] == ["diff"]:
        destinations.extend(_output_option_destinations(args[1:], {"--output"}))
    elif executable == "ln":
        destinations.extend(_link_destinations(args))
    elif executable == "tar" and _tar_extracts(args):
        destinations.extend(_tar_directory_destinations(args))
    elif executable == "unzip":
        destinations.extend(_output_option_destinations(args, {"-d"}))
    elif executable == "rsync":
        destinations.extend(_rsync_destinations(args))
    elif executable in {"rm", "rmdir", "touch", "mkdir", "chmod", "chown"}:
        destinations.extend(positional)
    return _dedupe(destinations)


def _link_destinations(args: list[str]) -> list[str]:
    target_directories = _output_option_destinations(args, {"-t", "--target-directory"})
    if target_directories:
        return target_directories
    positional = [arg for arg in args if not arg.startswith("-")]
    return positional[-1:]


def _tar_extracts(args: list[str]) -> bool:
    if any(
        arg in {"-x", "--extract", "--get"}
        or (arg.startswith("-") and not arg.startswith("--") and "x" in arg[1:])
        for arg in args
    ):
        return True
    if not args or args[0].startswith("-"):
        return False
    return bool(re.fullmatch(r"[A-Za-z]+", args[0]) and "x" in args[0])


def _tar_directory_destinations(args: list[str]) -> list[str]:
    destinations = _output_option_destinations(args, {"-C", "--directory"})
    if not args:
        return destinations
    option_word = args[0]
    cluster = option_word[1:] if option_word.startswith("-") else option_word
    if not cluster or not re.fullmatch(r"[A-Za-z]+", cluster):
        return destinations
    operand_index = 1
    value_options = {"b", "C", "f", "g", "I", "K", "L", "M", "N", "T", "V", "X"}
    for option in cluster:
        if option not in value_options:
            continue
        if operand_index >= len(args):
            if option == "C":
                destinations.append("$UNRESOLVED_MISSING_OUTPUT")
            break
        if option == "C":
            destinations.append(args[operand_index])
        operand_index += 1
    return _dedupe(destinations)


def _rsync_destinations(args: list[str]) -> list[str]:
    value_options = {
        "-e",
        "--rsh",
        "-f",
        "--filter",
        "--exclude",
        "--include",
        "--exclude-from",
        "--include-from",
        "--files-from",
        "--rsync-path",
        "--password-file",
        "--log-file",
        "--log-file-format",
        "--backup-dir",
        "--suffix",
        "--temp-dir",
        "--partial-dir",
        "--compare-dest",
        "--copy-dest",
        "--link-dest",
        "--timeout",
        "--contimeout",
        "--bwlimit",
        "--block-size",
        "--checksum-choice",
        "--checksum-seed",
        "--compress-choice",
        "--compress-level",
        "--iconv",
        "--max-delete",
        "--max-size",
        "--min-size",
        "--modify-window",
        "--out-format",
        "--port",
        "--protocol",
        "--read-batch",
        "--sockopts",
        "--skip-compress",
        "--write-batch",
        "--chmod",
        "--chown",
        "--usermap",
        "--groupmap",
        "-M",
        "--remote-option",
        "-B",
        "-T",
    }
    output_options = {
        "--log-file",
        "--backup-dir",
        "--temp-dir",
        "--partial-dir",
        "--write-batch",
        "-T",
    }
    positionals: list[str] = []
    additional_sinks: list[str] = []
    uncertain = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positionals.extend(args[index + 1 :])
            break
        if arg.startswith("--") and "=" in arg:
            option, value = arg.split("=", 1)
            if option in output_options:
                additional_sinks.append(value)
            elif option not in value_options:
                uncertain = True
            index += 1
            continue
        if arg in value_options:
            if index + 1 >= len(args):
                uncertain = True
                break
            if arg in output_options:
                additional_sinks.append(args[index + 1])
            index += 2
            continue
        if arg.startswith(("-e", "-f", "-M")) and len(arg) > 2:
            index += 1
            continue
        temp_dir = _short_option_cluster_match(
            arg,
            target="T",
            no_value_options=set(),
            consuming_options={"B", "M", "e", "f"},
            allow_unknown_no_value=True,
        )
        if temp_dir.matched:
            if temp_dir.value is not None:
                additional_sinks.append(temp_dir.value)
                index += 1
                continue
            if index + 1 >= len(args):
                uncertain = True
                break
            additional_sinks.append(args[index + 1])
            index += 2
            continue
        if arg.startswith("--"):
            uncertain = True
            index += 1
            continue
        if arg.startswith("-"):
            index += 1
            continue
        positionals.append(arg)
        index += 1
    destinations = [*positionals[-1:], *additional_sinks]
    if uncertain:
        destinations.append("$UNRESOLVED_RSYNC_OPTION")
    return destinations


def _unknown_mutator_protected_paths(node: _CommandNode) -> list[str]:
    tokens, _ = _unwrap_command(list(node.tokens))
    if not tokens:
        return []
    executable = _basename(tokens[0])
    args = tokens[1:]
    if (
        executable in _READ_EXECUTABLES
        or executable in _SHELLS
        or _interpreter_family(executable) is not None
        or _is_read_only_platform_command(executable, args)
        or (executable == "git" and _classify_git(args) == "act_low")
        or (executable == "docker" and _classify_docker(args) == "act_low")
    ):
        return []
    candidates = [arg for arg in args if not arg.startswith("-")]
    candidates.extend(
        arg.split("=", 1)[1]
        for arg in args
        if arg.startswith("-") and "=" in arg and arg.split("=", 1)[1]
    )
    return [item["path"] for item in _protected_resources(candidates)]


def _archive_extracts(executable: str, args: list[str]) -> bool:
    if executable == "tar":
        return _tar_extracts(args)
    if executable != "unzip":
        return False
    for arg in args:
        if arg == "--":
            break
        if arg == "--version":
            return False
        if arg.startswith("-") and not arg.startswith("--"):
            flags = arg[1:]
            if "Z" in flags or any(flag in flags for flag in "ltvpc"):
                return False
    return True


def _copy_move_destinations(executable: str, args: list[str]) -> list[str]:
    target_directories: list[str] = []
    positional: list[str] = []
    uncertain = False
    value_options = {
        "-S",
        "--suffix",
        "--context",
    }
    no_value_options: set[str] = set()
    if executable == "cp":
        no_value_options.update(
            {
                "-a",
                "--archive",
                "-f",
                "--force",
                "-i",
                "--interactive",
                "-n",
                "--no-clobber",
                "-R",
                "-r",
                "--recursive",
                "-u",
                "--update",
                "-v",
                "--verbose",
                "-P",
                "--no-dereference",
                "-L",
                "--dereference",
                "-H",
                "-p",
                "--parents",
                "--remove-destination",
                "--strip-trailing-slashes",
                "--attributes-only",
            }
        )
    elif executable == "mv":
        no_value_options.update(
            {
                "-f",
                "--force",
                "-i",
                "--interactive",
                "-n",
                "--no-clobber",
                "-u",
                "--update",
                "-v",
                "--verbose",
                "-T",
                "--no-target-directory",
            }
        )
    else:
        no_value_options.update(
            {
                "-b",
                "-C",
                "--compare",
                "-D",
                "-d",
                "--directory",
                "-p",
                "--preserve-timestamps",
                "-s",
                "--strip",
                "-T",
                "--no-target-directory",
                "-v",
                "--verbose",
            }
        )
    if executable == "install":
        value_options.update(
            {"-g", "--group", "-m", "--mode", "-o", "--owner", "--strip-program"}
        )
    index = 0
    options_done = False
    while index < len(args):
        arg = args[index]
        if not options_done and arg == "--":
            options_done = True
            index += 1
            continue
        if not options_done and arg in {"-t", "--target-directory"}:
            if index + 1 < len(args):
                target_directories.append(args[index + 1])
                index += 2
                continue
            return ["$UNRESOLVED_MISSING_TARGET_DIRECTORY"]
        if not options_done and arg.startswith("--target-directory="):
            target_directories.append(arg.split("=", 1)[1])
            index += 1
            continue
        if not options_done and arg in value_options:
            if index + 1 >= len(args):
                uncertain = True
                break
            index += 2
            continue
        if not options_done and arg in no_value_options:
            index += 1
            continue
        if not options_done and arg.startswith("--") and "=" in arg:
            option, _value = arg.split("=", 1)
            if option not in value_options and option not in {
                "--backup",
                "--preserve",
                "--reflink",
                "--sparse",
            }:
                uncertain = True
            index += 1
            continue
        if not options_done and arg.startswith("-"):
            uncertain = True
            index += 1
            continue
        positional.append(arg)
        index += 1
    destinations = target_directories or positional[-1:]
    if uncertain:
        destinations.append("$UNRESOLVED_COPY_MOVE_OPTION")
    return destinations


def _xargs_command(args: list[str]) -> list[str]:
    takes_value = {
        "-a",
        "--arg-file",
        "-d",
        "--delimiter",
        "-E",
        "--eof",
        "-I",
        "--replace",
        "-L",
        "--max-lines",
        "-n",
        "--max-args",
        "-P",
        "--max-procs",
        "-s",
        "--max-chars",
    }
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            return args[index + 1 :]
        if not arg.startswith("-"):
            return args[index:]
        index += 1
        if arg in takes_value and index < len(args):
            index += 1
    return []


def _xargs_nested_is_hardline(tokens: list[str]) -> bool:
    return classify_command_level(" ".join(tokens)) == "critical"


def _find_nested_commands(args: list[str]) -> list[list[str]]:
    commands: list[list[str]] = []
    for marker in ("-exec", "-execdir", "-ok", "-okdir"):
        start = 0
        while marker in args[start:]:
            index = args.index(marker, start)
            end = next(
                (
                    candidate
                    for candidate in range(index + 1, len(args))
                    if args[candidate] in {";", "\\;", "+"}
                ),
                len(args),
            )
            nested = args[index + 1 : end]
            if nested:
                commands.append(nested)
            start = end + 1
    return commands


def _find_is_hardline(args: list[str]) -> bool:
    roots: list[str] = []
    for arg in args:
        if arg.startswith("-") or arg in {"!", "("}:
            break
        roots.append(arg)
    scans_root = any(_rootish_path(root) for root in roots)
    if scans_root and "-delete" in args:
        return True
    for nested in _find_nested_commands(args):
        level = classify_command_level(" ".join(nested))
        nested_executable = _executable(tuple(nested))
        if level == "critical":
            return True
        if scans_root and (
            level == "destructive"
            or nested_executable in {"rm", "rmdir", "shred", "truncate"}
        ):
            return True
    return False


def _classify_git(args: list[str]) -> RiskLevel:
    if not args:
        return "act_low"
    if args in [["--version"], ["--help"]]:
        return "act_low"
    if args[0].startswith("-"):
        return "act_high"
    subcommand = args[0]
    subargs = args[1:]
    if (subcommand == "reset" and "--hard" in args) or (
        subcommand == "clean" and any(arg.startswith("-f") for arg in args)
    ):
        return "destructive"
    if subcommand in _GIT_EXTERNAL:
        return "external"
    if _git_read_form(subcommand, subargs):
        return "act_low"
    return "act_high"


def _classify_docker(args: list[str]) -> RiskLevel:
    args = _docker_command_args(args)
    if not args:
        return "act_low"
    if args in [["--version"], ["version"]]:
        return "act_low"
    if args[0].startswith("-"):
        return "act_high"
    subcommand = args[0]
    subargs = args[1:]
    if _docker_requires_critical_approval(subcommand, subargs):
        return "critical"
    if subcommand == "system":
        if subargs[:1] == ["df"]:
            return "act_low" if _docker_read_form("info", subargs[1:]) else "act_high"
        return "act_high"
    if subcommand == "compose":
        return _classify_docker_compose(subargs)
    if subcommand in {"image", "container", "volume", "network", "context"}:
        return _classify_docker_group(subcommand, subargs)
    if subcommand in _DOCKER_DESTRUCTIVE:
        return "destructive"
    if subcommand in _DOCKER_EXTERNAL:
        return "external"
    if _docker_read_form(subcommand, subargs):
        return "act_low"
    return "act_high"


def _docker_command_args(args: list[str]) -> list[str]:
    """Strip Docker CLI global options before classifying the subcommand."""
    index = 0
    value_options = {
        "--config",
        "--context",
        "--host",
        "--log-level",
        "--tlscacert",
        "--tlscert",
        "--tlskey",
        "-c",
        "-H",
    }
    while index < len(args):
        arg = args[index]
        if arg == "--":
            return args[index + 1 :]
        if arg in value_options:
            index += 2
            continue
        if (arg.startswith("-c") or arg.startswith("-H")) and len(arg) > 2:
            index += 1
            continue
        if any(
            arg.startswith(f"{option}=")
            for option in value_options
            if option.startswith("--")
        ):
            index += 1
            continue
        if (
            arg in {"--debug", "-D", "--tls", "--tlsverify"}
            or arg.startswith("--tlscacert=")
            or arg.startswith("--tlscert=")
            or arg.startswith("--tlskey=")
        ):
            index += 1
            continue
        break
    return args[index:]


def _docker_requires_critical_approval(subcommand: str, args: list[str]) -> bool:
    if subcommand in {"system", "image", "container", "network", "volume"}:
        if args[:1] == ["prune"]:
            return True
    if subcommand == "compose":
        compose_command, compose_args = _docker_compose_command(args)
        if compose_command == "down" and _docker_volumes_requested(compose_args):
            return True
        return False
    if subcommand not in {"run", "create", "exec"}:
        return False
    if any(arg == "--privileged" or arg.startswith("--privileged=") for arg in args):
        return True
    if subcommand == "exec":
        return False
    return _docker_has_host_escalating_mount(args)


def _docker_has_host_escalating_mount(args: list[str]) -> bool:
    index = 0
    while index < len(args):
        arg = args[index]
        value: str | None = None
        if arg in {"-v", "--volume", "--mount"}:
            if index + 1 < len(args):
                value = args[index + 1]
                index += 1
        elif arg.startswith("--volume=") or arg.startswith("--mount="):
            value = arg.split("=", 1)[1]
        elif arg.startswith("-v") and len(arg) > 2:
            value = arg[2:]
        if value is not None:
            source = posixpath.normpath(_docker_mount_source(value))
            if source == "/" or _docker_socket_path(source):
                return True
        index += 1
    return False


def _docker_mount_source(value: str) -> str:
    if "," in value and any(
        part in {"type=bind", "type=volume"} for part in value.split(",")
    ):
        fields = dict(part.split("=", 1) for part in value.split(",") if "=" in part)
        return fields.get("source") or fields.get("src") or ""
    return value.split(":", 1)[0]


def _docker_socket_path(path: str) -> bool:
    normalized = posixpath.normpath(path)
    return normalized.endswith("/docker.sock") or normalized == "docker.sock"


def _docker_volumes_requested(args: list[str]) -> bool:
    return any(
        arg in {"-v", "--volumes"} or arg.startswith("--volumes=") for arg in args
    )


def _docker_compose_command(args: list[str]) -> tuple[str | None, list[str]]:
    index = 0
    value_options = {
        "--ansi",
        "--env-file",
        "--file",
        "--parallel",
        "--profile",
        "--progress",
        "--project-directory",
        "--project-name",
        "-f",
        "-p",
    }
    while index < len(args):
        arg = args[index]
        if arg in value_options:
            index += 2
            continue
        if any(
            arg.startswith(f"{option}=")
            for option in value_options
            if option.startswith("--")
        ):
            index += 1
            continue
        if arg.startswith("-"):
            index += 1
            continue
        return arg, args[index + 1 :]
    return None, []


def _classify_docker_compose(args: list[str]) -> RiskLevel:
    subcommand, subargs = _docker_compose_command(args)
    if subcommand is None:
        return "act_high"
    if subcommand in {"pull", "push"}:
        return "external"
    if subcommand in {"rm"}:
        return "destructive"
    if subcommand in {"ps", "ls", "logs", "top", "images", "config"}:
        return "act_low"
    if subcommand == "down" and _docker_volumes_requested(subargs):
        return "critical"
    return "act_high"


def _git_read_form(subcommand: str, args: list[str]) -> bool:
    if subcommand == "status":
        return _known_read_args(
            args,
            no_value={
                "-s",
                "--short",
                "-b",
                "--branch",
                "--porcelain",
                "--long",
                "-v",
                "--verbose",
                "--show-stash",
                "--ahead-behind",
                "--no-ahead-behind",
            },
            value_options={"-u", "--untracked-files", "--ignore-submodules"},
            allow_positionals=False,
        )
    if subcommand == "branch":
        return not args or _known_read_args(
            args,
            no_value={
                "-a",
                "--all",
                "-r",
                "--remotes",
                "-l",
                "--list",
                "--show-current",
                "-v",
                "-vv",
                "--verbose",
                "--merged",
                "--no-merged",
            },
            value_options={"--contains", "--no-contains", "--format", "--sort"},
            allow_positionals=True,
            require_read_selector=True,
        )
    if subcommand == "tag":
        return not args or _known_read_args(
            args,
            no_value={"-l", "--list", "--contains", "--no-contains"},
            value_options={"--points-at", "--format", "--sort"},
            allow_positionals=True,
            require_read_selector=True,
        )
    if subcommand == "remote":
        return not args or args == ["-v"] or args == ["--verbose"]
    if subcommand == "config":
        return _git_config_is_read_only(args)
    if subcommand in {
        "log",
        "show",
        "diff",
        "blame",
        "shortlog",
        "reflog",
        "whatchanged",
    }:
        if _has_output_option(args, {"--output"}):
            return False
        return _known_read_args(
            args,
            no_value={
                "--oneline",
                "--stat",
                "--name-only",
                "--name-status",
                "--summary",
                "--check",
                "--patch",
                "-p",
                "--no-patch",
                "-s",
                "--decorate",
                "--graph",
                "--all",
                "--reverse",
                "--raw",
                "--compact-summary",
                "--numstat",
                "--shortstat",
                "--color",
                "--no-color",
                "--cached",
                "--staged",
            },
            value_options={
                "-n",
                "--max-count",
                "--format",
                "--pretty",
                "--since",
                "--until",
                "--author",
                "--grep",
                "--diff-filter",
                "--color",
            },
            allow_positionals=True,
        )
    if subcommand in {"rev-parse", "ls-files", "describe", "cat-file"}:
        return _known_read_args(
            args,
            no_value={
                "--show-toplevel",
                "--show-current",
                "--is-inside-work-tree",
                "--git-dir",
                "--short",
                "--cached",
                "--others",
                "--stage",
                "-t",
                "-p",
                "-s",
            },
            value_options={"--format", "--exclude-standard"},
            allow_positionals=True,
        )
    return False


def _git_config_is_read_only(args: list[str]) -> bool:
    query_actions = {
        "--get",
        "--get-all",
        "--get-regexp",
        "--get-urlmatch",
        "--list",
        "-l",
    }
    read_modifiers = {
        "--show-origin",
        "--show-scope",
        "--name-only",
    }
    if not args:
        return False
    if any(
        arg
        in {
            "--unset",
            "--unset-all",
            "--add",
            "--replace-all",
            "--rename-section",
            "--remove-section",
            "--edit",
        }
        for arg in args
    ):
        return False
    positionals = [arg for arg in args if not arg.startswith("-")]
    unknown_options = [
        arg
        for arg in args
        if arg.startswith("-")
        and arg not in query_actions
        and arg not in read_modifiers
        and not arg.startswith("--type=")
    ]
    if unknown_options:
        return False
    if set(args).intersection(query_actions):
        return True
    return len(positionals) == 1


def _classify_docker_group(group: str, args: list[str]) -> RiskLevel:
    if not args or args[0].startswith("-"):
        return "act_high"
    subcommand = args[0]
    subargs = args[1:]
    if subcommand == "prune":
        return "critical"
    if subcommand == "rm":
        return "destructive"
    if subcommand in {"pull", "push"}:
        return "external"
    allowed: dict[str, set[str]] = {
        "image": {"ls", "list", "inspect", "history"},
        "container": {"ls", "list", "inspect", "logs", "stats", "top", "port"},
        "volume": {"ls", "list", "inspect"},
        "network": {"ls", "list", "inspect"},
        "context": {"ls", "list", "show", "inspect"},
    }
    if subcommand not in allowed[group]:
        return "act_high"
    return "act_low" if _docker_read_form(subcommand, subargs) else "act_high"


def _docker_read_form(subcommand: str, args: list[str]) -> bool:
    if subcommand in {"version", "info"}:
        return _known_read_args(
            args,
            no_value=set(),
            value_options={"-f", "--format"},
            allow_positionals=False,
        )
    if subcommand in {"ps", "images", "ls", "list"}:
        return _known_read_args(
            args,
            no_value={"-a", "--all", "-q", "--quiet", "--no-trunc", "--digests"},
            value_options={"-f", "--filter", "--format"},
            allow_positionals=False,
        )
    if subcommand in {"inspect", "history"}:
        return _known_read_args(
            args,
            no_value={"--size", "--no-trunc"},
            value_options={"-f", "--format", "--type"},
            allow_positionals=True,
        )
    if subcommand == "logs":
        return _known_read_args(
            args,
            no_value={"--details", "-f", "--follow", "-t", "--timestamps"},
            value_options={"--since", "--until", "-n", "--tail"},
            allow_positionals=True,
        )
    if subcommand in {"stats", "top", "port"}:
        return _known_read_args(
            args,
            no_value={"--all", "--no-stream", "--no-trunc"},
            value_options={"--format"},
            allow_positionals=True,
        )
    if subcommand == "show":
        return not args
    return False


def _known_read_args(
    args: list[str],
    *,
    no_value: set[str],
    value_options: set[str],
    allow_positionals: bool,
    require_read_selector: bool = False,
) -> bool:
    selector_seen = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            return allow_positionals and not require_read_selector or selector_seen
        if arg.startswith("--") and "=" in arg:
            option, _value = arg.split("=", 1)
            if option not in value_options and option not in no_value:
                return False
            selector_seen = True
            index += 1
            continue
        if arg in no_value:
            selector_seen = True
            index += 1
            continue
        if arg in value_options:
            selector_seen = True
            if index + 1 >= len(args):
                return False
            index += 2
            continue
        if arg.startswith("-"):
            return False
        if not allow_positionals:
            return False
        index += 1
    return not require_read_selector or selector_seen


def _basename(value: str) -> str:
    return value.rsplit("/", 1)[-1]


def _executable(tokens: tuple[str, ...]) -> str | None:
    unwrapped, _ = _unwrap_command(list(tokens))
    return _basename(unwrapped[0]) if unwrapped else None


def _looks_like_fork_bomb(text: str) -> bool:
    return bool(re.match(r"^\s*:\s*\(\s*\)\s*\{[^\n]*\|[^\n]*&\s*\}\s*;", text))


def _command_substitutions(text: str) -> list[str]:
    substitutions: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote == "'":
            if char == "'":
                quote = None
            index += 1
            continue
        if char == "'" and quote is None:
            quote = "'"
            index += 1
            continue
        if char == '"':
            quote = None if quote == '"' else '"'
            index += 1
            continue
        if char == "$" and index + 1 < len(text) and text[index + 1] == "(":
            end = _matching_parenthesis(text, index + 1)
            if end is None:
                index += 2
                continue
            substitutions.append(text[index + 2 : end])
            index = end + 1
            continue
        if char == "`":
            end = index + 1
            while end < len(text) and text[end] != "`":
                end += 2 if text[end] == "\\" else 1
            if end < len(text):
                substitutions.append(text[index + 1 : end])
                index = end + 1
                continue
        index += 1
    return substitutions


def _process_substitutions(text: str) -> list[str]:
    substitutions: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(text) - 1:
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char in {"<", ">"} and text[index + 1] == "(":
            end = _matching_parenthesis(text, index + 1)
            if end is None:
                index += 2
                continue
            substitutions.append(text[index + 2 : end])
            index = end + 1
            continue
        index += 1
    return substitutions


def _heredoc_bodies(text: str) -> list[str]:
    lines = text.splitlines()
    bodies: list[str] = []
    index = 0
    while index < len(lines):
        match = re.search(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", lines[index])
        if match is None:
            index += 1
            continue
        prefix_nodes = _parse_command_nodes(lines[index][: match.start()])
        receiver = _executable(prefix_nodes[-1].tokens) if prefix_nodes else None
        delimiter = match.group(2)
        body: list[str] = []
        index += 1
        while index < len(lines) and lines[index].lstrip("\t") != delimiter:
            body.append(lines[index])
            index += 1
        if _heredoc_receiver_can_execute(receiver):
            bodies.append("\n".join(body))
        index += 1
    return bodies


def _heredoc_receiver_can_execute(executable: str | None) -> bool:
    if executable is None:
        return True
    if executable in _SHELLS or _interpreter_family(executable) is not None:
        return True
    return executable not in _READ_EXECUTABLES


def _matching_parenthesis(text: str, opening: int) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _max_level(first: RiskLevel, second: RiskLevel) -> RiskLevel:
    return first if _RANK[first] >= _RANK[second] else second


def _strip_heredoc_bodies(text: str) -> str:
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    delimiter: str | None = None
    for line in lines:
        if delimiter is not None:
            if line.rstrip("\r\n") == delimiter:
                delimiter = None
            continue
        output.append(line)
        match = re.search(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line)
        if match:
            delimiter = match.group(2)
    return "".join(output)


def _is_read_only_platform_command(executable: str, args: list[str]) -> bool:
    if executable in {"module", "ml"}:
        verbs = [arg for arg in args if not arg.startswith("-")]
        return bool(verbs) and verbs[0] in {
            "avail",
            "list",
            "show",
            "whatis",
            "help",
        }
    if executable in {"squeue", "sinfo", "sacct", "qstat"}:
        return True
    if executable == "nextflow":
        return args in [["-version"], ["-v"], ["version"], ["info"]]
    if executable == "phoenixcli":
        return _phoenixcli_is_read_only(args)
    return False


def _phoenixcli_is_read_only(args: list[str]) -> bool:
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--no-interactive":
            index += 1
            continue
        if arg in {"--profile", "--config"} and index + 1 < len(args):
            index += 2
            continue
        break
    if args[index : index + 2] != ["pipeline", "list"]:
        return False
    index += 2
    while index < len(args):
        arg = args[index]
        if arg in {"--output", "--limit", "--page", "--sort"} and index + 1 < len(args):
            index += 2
            continue
        if arg in {"--all", "--json"}:
            index += 1
            continue
        return False
    return True


def _inspect_legacy_behavior(node: _CommandNode) -> _NodeSemantics:
    """Adapt one legacy grammar decision into a complete semantic fact set."""
    level = _classify_node(node)
    env_split = _env_split_command(list(node.tokens))
    if env_split:
        return _inspect_node(_CommandNode(tokens=tuple(env_split)))

    effects: list[SemanticEffect] = []
    tokens, elevated = _unwrap_command(list(node.tokens))
    if not tokens:
        if node.tokens and _basename(node.tokens[0]) == "env":
            return _NodeSemantics(
                level=level,
                effects=("read",),
                reasons=("env without a command inspects the current environment",),
            )
        return _NodeSemantics(level=level, effects=("unknown",))
    executable = _basename(tokens[0])
    args = tokens[1:]
    if elevated:
        effects.append("privilege")
    writes = _node_writes(tokens, executable, args)
    if writes:
        effects.append("write")
    if executable in _SHELLS:
        effects.append("code_execution")
        inner = _shell_command_argument(args)
        if inner is not None:
            effects.extend(_analyze_command_semantics(inner).effects)
            return _node_semantics(level, effects)
    if executable == "eval" and args:
        effects.append("code_execution")
        effects.extend(_analyze_command_semantics(" ".join(args)).effects)
        return _node_semantics(level, effects)
    if executable == "busybox":
        nested = _busybox_command(args)
        if nested:
            effects.extend(_inspect_node(_CommandNode(tokens=tuple(nested))).effects)
            return _node_semantics(level, effects)
    if executable == "xargs":
        nested = _xargs_command(args)
        if nested:
            effects.append("code_execution")
            effects.extend(_inspect_node(_CommandNode(tokens=tuple(nested))).effects)
            return _node_semantics(level, effects)
    if executable == "find":
        if "-delete" in args:
            effects.append("delete")
        for nested in _find_nested_commands(args):
            effects.append("code_execution")
            effects.extend(_inspect_node(_CommandNode(tokens=tuple(nested))).effects)
        if effects:
            return _node_semantics(level, effects)
    if executable in {"rm", "rmdir", "shred"}:
        effects.append("delete")
    elif executable in {"kill", "pkill", "killall", *_SHUTDOWN_EXECUTABLES}:
        effects.append("process_control")
    elif executable == "systemctl" and _systemctl_verb(args)[0] in {
        *_SHUTDOWN_EXECUTABLES
    }:
        effects.append("process_control")
    elif executable == "init" and next(
        (arg for arg in args if not arg.startswith("-")), None
    ) in {"0", "6"}:
        effects.append("process_control")
    elif executable.startswith("mkfs"):
        effects.append("write")
    elif _interpreter_family(executable) is not None:
        effects.append("code_execution")
    elif executable in _EXTERNAL_EXECUTABLES or executable in _INSTALL_EXECUTABLES:
        effects.append("network")
        if executable == "rsync":
            effects.append("write")
    elif executable == "git":
        if level == "external":
            effects.append("network")
        elif level == "destructive":
            effects.append("delete")
        elif level == "act_low":
            effects.append("read")
        elif not writes:
            effects.append("unknown")
    elif executable == "docker":
        if level == "external":
            effects.append("network")
        elif level == "destructive":
            effects.append("delete")
        elif level == "act_low":
            effects.append("read")
        else:
            effects.append("code_execution")
    elif writes:
        pass
    elif executable in _READ_EXECUTABLES or _is_read_only_platform_command(
        executable, args
    ):
        effects.append("read")
    else:
        effects.append("unknown")
    return _node_semantics(level, effects)


def _node_semantics(
    level: RiskLevel,
    effects: list[SemanticEffect],
) -> _NodeSemantics:
    normalized = tuple(_dedupe(effects)) or ("unknown",)
    return _NodeSemantics(
        level=level,
        effects=normalized,
        reasons=("node matched a hardline rule",) if level == "critical" else (),
    )


def _node_writes(tokens: list[str], executable: str, args: list[str]) -> bool:
    if _has_file_output_redirect(tokens):
        return True
    if executable in {
        "touch",
        "mkdir",
        "install",
        "cp",
        "mv",
        "tee",
        "truncate",
        "chmod",
        "chown",
        "dd",
        "ln",
        "rsync",
    }:
        return True
    if executable == "tar" and _tar_extracts(args):
        return True
    if executable == "unzip" and _archive_extracts(executable, args):
        return True
    if executable == "sort" and _has_output_option(args, {"-o", "--output"}):
        return True
    if executable == "diff" and _has_output_option(args, {"--output"}):
        return True
    if (
        executable == "git"
        and args[:1] == ["diff"]
        and _has_output_option(args[1:], {"--output"})
    ):
        return True
    return executable in {"sed", "perl"} and any(arg.startswith("-i") for arg in args)


def _referenced_paths(
    nodes: list[_CommandNode], *, target: CommandTargetProfile
) -> tuple[list[str], bool]:
    paths: list[str] = []
    confident = True
    for node in nodes:
        tokens, _ = _unwrap_command(list(node.tokens))
        if not tokens:
            continue
        executable = _basename(tokens[0])
        args = tokens[1:]
        if executable in _SHELLS:
            inner = _shell_command_argument(args)
            if inner is not None:
                inner_paths, inner_confident = _referenced_paths(
                    _parse_command_nodes(_strip_heredoc_bodies(inner)),
                    target=target,
                )
                paths.extend(inner_paths)
                confident = confident and inner_confident
                continue
        for index, token in enumerate(tokens[:-1]):
            if token in {">", ">>", "<", "<<"}:
                redirected = _redirect_path_token(tokens, index)
                if redirected is not None:
                    paths.append(_canonical_reference(redirected, target))
        file_tokens = _tokens_without_redirection_syntax(tokens)
        file_args, node_confident = _file_arguments(
            _basename(file_tokens[0]) if file_tokens else executable,
            file_tokens[1:] if file_tokens else args,
        )
        confident = confident and node_confident
        paths.extend(_canonical_reference(arg, target) for arg in file_args)
    return _dedupe(_bounded_strings(paths, limit=32, width=1000)), confident


def _tokens_without_redirection_syntax(tokens: list[str]) -> list[str]:
    cleaned: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {">", ">>", "<", "<<"}:
            if (
                token in {">", ">>"}
                and cleaned
                and cleaned[-1].isdigit()
                and index + 1 < len(tokens)
                and _is_fd_duplication_word(tokens[index + 1])
            ):
                cleaned.pop()
            index += 2
            continue
        cleaned.append(token)
        index += 1
    return cleaned


def _file_arguments(executable: str, args: list[str]) -> tuple[list[str], bool]:
    file_commands = {
        "cat",
        "head",
        "tail",
        "ls",
        "stat",
        "file",
        "find",
        "du",
        "readlink",
        "realpath",
        "rm",
        "rmdir",
        "shred",
        "touch",
        "mkdir",
        "cp",
        "mv",
        "chmod",
        "chown",
        "sed",
        "perl",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "wc",
        "sort",
        "diff",
        "jq",
    }
    if executable not in file_commands:
        return [], True
    if executable in {"sed", "perl"}:
        return _editor_file_arguments(args), True
    if executable in {"grep", "egrep", "fgrep", "rg"}:
        return _grep_file_arguments(args)
    if executable == "wc":
        return _simple_read_file_arguments(
            args,
            known_flags={
                "-c",
                "-m",
                "-l",
                "-w",
                "-L",
                "--bytes",
                "--chars",
                "--lines",
                "--words",
                "--max-line-length",
            },
        )
    if executable == "sort":
        return _sort_file_arguments(args)
    if executable == "diff":
        return _diff_file_arguments(args)
    if executable == "jq":
        return _jq_file_arguments(args)
    values: list[str] = []
    for arg in args:
        if arg.startswith("-") or arg in {"{}", "+", ";"}:
            continue
        if executable in {"head", "tail"} and arg.isdigit():
            continue
        values.append(arg)
    return values, True


def _grep_file_arguments(args: list[str]) -> tuple[list[str], bool]:
    no_value = {
        "-n",
        "-r",
        "-R",
        "-i",
        "-v",
        "-w",
        "-x",
        "-s",
        "-q",
        "-H",
        "-h",
        "-l",
        "-L",
        "-c",
        "-o",
        "-a",
        "-I",
        "-U",
        "-z",
        "--line-number",
        "--recursive",
        "--ignore-case",
        "--invert-match",
        "--word-regexp",
        "--line-regexp",
        "--quiet",
        "--with-filename",
        "--no-filename",
        "--files-with-matches",
        "--files-without-match",
        "--count",
        "--only-matching",
    }
    pattern_options = {"-e", "--regexp"}
    path_options = {"-f", "--file", "--files-from"}
    value_options = {
        "-m",
        "--max-count",
        "-A",
        "--after-context",
        "-B",
        "--before-context",
        "-C",
        "--context",
        "--include",
        "--exclude",
        "--exclude-dir",
        "--glob",
        "-g",
        "--type",
        "-t",
        "--type-not",
        "-T",
    }
    paths: list[str] = []
    positionals: list[str] = []
    confident = True
    pattern_supplied = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positionals.extend(args[index + 1 :])
            break
        if arg.startswith("--") and "=" in arg:
            option, value = arg.split("=", 1)
            if option in path_options:
                paths.append(value)
                pattern_supplied = True
            elif option in pattern_options:
                pattern_supplied = True
            elif option not in value_options and option not in no_value:
                confident = False
                if _looks_like_path(value):
                    paths.append(value)
            index += 1
            continue
        if arg in no_value:
            index += 1
            continue
        if arg in pattern_options | path_options | value_options:
            if index + 1 >= len(args):
                confident = False
                break
            value = args[index + 1]
            if arg in path_options:
                paths.append(value)
                pattern_supplied = True
            elif arg in pattern_options:
                pattern_supplied = True
            index += 2
            continue
        if arg.startswith("-"):
            confident = False
            index += 1
            continue
        positionals.append(arg)
        index += 1
    if not pattern_supplied and positionals:
        positionals = positionals[1:]
    paths.extend(positionals)
    return paths, confident


def _simple_read_file_arguments(
    args: list[str], *, known_flags: set[str]
) -> tuple[list[str], bool]:
    paths: list[str] = []
    confident = True
    options_done = False
    for arg in args:
        if arg == "--":
            options_done = True
        elif not options_done and arg.startswith("-"):
            if arg not in known_flags:
                confident = False
        else:
            paths.append(arg)
    return paths, confident


def _sort_file_arguments(args: list[str]) -> tuple[list[str], bool]:
    no_value = {
        "-b",
        "-d",
        "-f",
        "-g",
        "-i",
        "-M",
        "-n",
        "-h",
        "-r",
        "-R",
        "-s",
        "-u",
        "-V",
        "-z",
        "--reverse",
        "--unique",
        "--stable",
    }
    value_options = {"-k", "--key", "-t", "--field-separator", "-S", "--buffer-size"}
    path_options = {"-o", "--output", "--random-source", "-T", "--temporary-directory"}
    return _option_aware_paths(args, no_value, value_options, path_options)


def _diff_file_arguments(args: list[str]) -> tuple[list[str], bool]:
    no_value = {
        "-q",
        "-s",
        "-r",
        "-N",
        "-a",
        "-b",
        "-B",
        "-i",
        "-w",
        "-y",
        "-u",
        "-c",
        "--brief",
        "--report-identical-files",
        "--recursive",
        "--unified",
        "--context",
    }
    value_options = {"-U", "-C", "--label", "--exclude", "--exclude-from"}
    return _option_aware_paths(args, no_value, value_options, {"--output"})


def _jq_file_arguments(args: list[str]) -> tuple[list[str], bool]:
    no_value = {
        "-r",
        "-c",
        "-M",
        "-S",
        "-e",
        "-s",
        "-R",
        "-n",
        "-j",
        "--raw-output",
        "--compact-output",
        "--monochrome-output",
        "--sort-keys",
        "--exit-status",
        "--slurp",
        "--raw-input",
        "--null-input",
        "--join-output",
    }
    value_counts = {
        "--arg": 2,
        "--argjson": 2,
        "--slurpfile": 2,
        "--rawfile": 2,
        "--argfile": 2,
        "-L": 1,
    }
    path_value_options = {"--slurpfile", "--rawfile", "--argfile"}
    paths: list[str] = []
    positionals: list[str] = []
    confident = True
    filter_supplied = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positionals.extend(args[index + 1 :])
            break
        if arg in no_value:
            index += 1
            continue
        if arg in {"-f", "--from-file"}:
            if index + 1 >= len(args):
                confident = False
                break
            paths.append(args[index + 1])
            filter_supplied = True
            index += 2
            continue
        if arg in value_counts:
            count = value_counts[arg]
            if index + count >= len(args):
                confident = False
                break
            if arg in path_value_options:
                paths.append(args[index + count])
            index += count + 1
            continue
        if arg.startswith("-"):
            confident = False
            index += 1
            continue
        positionals.append(arg)
        index += 1
    if not filter_supplied and positionals:
        positionals = positionals[1:]
    paths.extend(positionals)
    return paths, confident


def _option_aware_paths(
    args: list[str],
    no_value: set[str],
    value_options: set[str],
    path_options: set[str],
) -> tuple[list[str], bool]:
    paths: list[str] = []
    confident = True
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            paths.extend(args[index + 1 :])
            break
        if arg.startswith("--") and "=" in arg:
            option, value = arg.split("=", 1)
            if option in path_options:
                paths.append(value)
            elif option not in value_options and option not in no_value:
                confident = False
                if _looks_like_path(value):
                    paths.append(value)
            index += 1
            continue
        if arg in no_value:
            index += 1
            continue
        if arg in value_options | path_options:
            if index + 1 >= len(args):
                confident = False
                break
            if arg in path_options:
                paths.append(args[index + 1])
            index += 2
            continue
        if arg.startswith("-"):
            confident = False
            index += 1
            continue
        paths.append(arg)
        index += 1
    return paths, confident


def _editor_file_arguments(args: list[str]) -> list[str]:
    files: list[str] = []
    program_seen = False
    skip_program_argument = False
    for arg in args:
        if skip_program_argument:
            skip_program_argument = False
            program_seen = True
            continue
        if arg in {"-e", "--expression", "-f", "--file"}:
            skip_program_argument = True
            continue
        if arg.startswith("-"):
            continue
        if not program_seen:
            program_seen = True
            continue
        files.append(arg)
    return files


def _looks_like_path(value: str) -> bool:
    return (
        value.startswith(("/", "~", "$", "."))
        or "/" in value
        or value.endswith((".md", ".txt", ".json", ".yaml", ".yml", ".env"))
    )


def _canonical_reference(value: str, target: CommandTargetProfile) -> str:
    if value.startswith(("$", "~")):
        return value
    if value.startswith("/"):
        return posixpath.normpath("/" + value.lstrip("/"))
    if target.working_directory:
        return posixpath.normpath(posixpath.join(target.working_directory, value))
    return value


def _path_is_unresolved(path: str) -> bool:
    return path.startswith(("$", "~")) or "$" in path


def _path_within_roots(path: str, roots: tuple[str, ...]) -> bool:
    if not roots:
        return False
    normalized = posixpath.normpath(path)
    return any(
        normalized == posixpath.normpath(root)
        or normalized.startswith(f"{posixpath.normpath(root).rstrip('/')}/")
        for root in roots
    )


def _protected_resources(paths: list[str]) -> list[dict[str, str]]:
    protected: list[dict[str, str]] = []
    for path in paths:
        lowered = path.casefold()
        kind: str | None = None
        if "/.ssh/" in lowered or lowered.endswith("/.ssh") or "/etc/ssh/" in lowered:
            kind = "ssh"
        elif lowered == "/etc/sudoers" or "/etc/sudoers.d/" in lowered:
            kind = "sudoers"
        elif posixpath.basename(lowered) in {
            ".bashrc",
            ".bash_profile",
            ".zshrc",
            ".profile",
            ".login",
        } or lowered in {"/etc/profile", "/etc/bashrc"}:
            kind = "shell_startup"
        elif posixpath.basename(lowered) in {
            "agents.md",
            "claude.md",
            "gemini.md",
        } or any(
            marker in lowered for marker in ("/.codex/", "/.claude/", "/.agents/")
        ):
            kind = "agent_policy"
        elif posixpath.basename(lowered) in {
            ".env",
            ".netrc",
            "credentials",
            "id_rsa",
            "id_ed25519",
        } or any(marker in lowered for marker in ("/.aws/", "/.config/gcloud/")):
            kind = "credential"
        if kind is not None:
            protected.append({"kind": kind, "path": path})
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in protected:
        key = (item["kind"], item["path"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _bounded_strings(
    values: list[str], *, limit: int = 32, width: int = 500
) -> list[str]:
    return [str(value)[:width] for value in values[:limit]]

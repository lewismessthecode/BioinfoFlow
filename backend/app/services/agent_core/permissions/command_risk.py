"""Quote-aware shell command semantics used by every execution target.

This module deliberately stops short of interpreting a complete shell grammar.
It extracts the command positions and operators needed by the permission layer
without treating quoted arguments or heredoc bodies as executable source.
"""

from __future__ import annotations

import posixpath
import re
import shlex
from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.agent_core.permissions.risk import RiskAssessment, RiskLevel


TargetKind = Literal["local", "remote_ssh", "container"]
SandboxStrength = Literal["enforced", "declared", "none"]
RiskConfidence = Literal["high", "medium", "low"]


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

    def audit_snapshot(self) -> dict[str, Any]:
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


def command_target_profile_from_context(
    context: Any,
    *,
    action_input: dict[str, Any] | None = None,
) -> CommandTargetProfile:
    """Build the canonical command target from one fresh permission context."""
    action_input = action_input or {}
    execution_target = context.execution_target
    target_kind = str(execution_target.get("type") or "local")
    boundary = context.boundary
    roots = tuple(str(root) for root in context.effective_roots)
    if target_kind == "remote_ssh":
        identity = context.remote_identity or {}
        working_directory = roots[0] if roots else None
        return CommandTargetProfile(
            kind="remote_ssh",
            trust_domain=str(identity.get("host") or "remote-ssh"),
            identity=str(identity.get("username"))
            if identity.get("username")
            else None,
            sandbox_strength="none",
            read_roots=roots,
            write_roots=roots,
            working_directory=working_directory,
            network_allowed=True,
            connection_id=str(execution_target.get("connection_id") or "") or None,
        )
    sandbox_disabled = bool(action_input.get("dangerously_disable_sandbox"))
    sandbox_strength: SandboxStrength = (
        "enforced"
        if bool(boundary.get("sandboxed")) and not sandbox_disabled
        else "none"
    )
    return CommandTargetProfile(
        kind="local",
        trust_domain="local-machine",
        identity="local-user",
        sandbox_strength=sandbox_strength,
        read_roots=roots,
        write_roots=roots,
        working_directory=str(action_input.get("cwd") or "")
        or (roots[0] if roots else None),
        network_allowed=(
            True if sandbox_disabled else bool(boundary.get("network_allowed", True))
        ),
    )


def assess_command_risk(
    command: str,
    *,
    target: CommandTargetProfile,
    requested_connection_id: str | None = None,
) -> CommandRiskAssessment:
    level = classify_command_level(command)
    nodes = _parse_command_nodes(_strip_heredoc_bodies(command))
    effects = _command_effects(nodes)
    referenced_paths = _referenced_paths(nodes, target=target)
    protected_resources = _protected_resources(referenced_paths)
    reasons = [f"command semantics classified as {level}"]
    hard_blocked = level == "critical"

    if (
        target.kind == "remote_ssh"
        and requested_connection_id
        and requested_connection_id != target.connection_id
    ):
        hard_blocked = True
        reasons.append(
            "requested remote connection does not match the selected execution target"
        )

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

    if target.kind == "remote_ssh":
        reasons.append(
            "remote commands are bounded by the remote SSH account and server policy, not the working directory"
        )
        confidence: RiskConfidence = "low" if unknown_path else "medium"
    elif target.sandbox_strength == "enforced":
        reasons.append("the local operating-system sandbox enforces the declared roots")
        confidence = "low" if unknown_path else "high"
    else:
        reasons.append("the local command has no enforced operating-system sandbox")
        confidence = "low" if unknown_path else "medium"

    protected_write = bool(protected_resources) and bool(
        {"write", "delete"}.intersection(effects)
    )
    if protected_write:
        reasons.append("the command mutates a protected resource")

    return CommandRiskAssessment(
        level=level,
        reasons=_bounded_strings(reasons),
        affected_resources=[
            {"type": "path", "id": path} for path in referenced_paths[:32]
        ],
        requires_explicit_approval=protected_write,
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
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
_SHUTDOWN_EXECUTABLES = frozenset({"shutdown", "reboot", "halt", "poweroff"})
_ROOTISH = frozenset({"/", "/*", "~", "$HOME", "${HOME}", ".."})

_GIT_READ = frozenset(
    {
        "status",
        "log",
        "diff",
        "show",
        "branch",
        "rev-parse",
        "ls-files",
        "ls-remote",
        "describe",
        "blame",
        "tag",
        "remote",
        "config",
        "cat-file",
        "shortlog",
        "reflog",
        "whatchanged",
    }
)
_GIT_EXTERNAL = frozenset({"push", "pull", "fetch", "clone", "submodule"})
_DOCKER_READ = frozenset(
    {
        "ps",
        "images",
        "image",
        "inspect",
        "logs",
        "version",
        "info",
        "stats",
        "top",
        "port",
        "history",
        "search",
        "context",
    }
)
_DOCKER_EXTERNAL = frozenset({"pull", "push", "login", "logout"})
_DOCKER_DESTRUCTIVE = frozenset({"rm", "rmi", "prune", "kill", "stop", "volume"})


@dataclass(frozen=True)
class _CommandNode:
    tokens: tuple[str, ...]
    operator_before: str | None = None


def classify_command_level(command: str) -> RiskLevel:
    """Return the semantic risk floor for a shell command string."""
    text = (command or "").strip()
    if not text:
        return "act_low"
    if _looks_like_fork_bomb(text):
        return "critical"
    substitutions = _command_substitutions(text)
    if any(classify_command_level(inner) == "critical" for inner in substitutions):
        return "critical"

    nodes = _parse_command_nodes(_strip_heredoc_bodies(text))
    highest: RiskLevel = "act_high" if substitutions or "<(" in text else "read"
    previous: _CommandNode | None = None
    for node in nodes:
        level = _classify_node(node)
        if level == "critical":
            return "critical"
        if (
            previous is not None
            and node.operator_before == "|"
            and _executable(previous.tokens) in {"curl", "wget"}
            and _executable(node.tokens) in _SHELLS
        ):
            return "critical"
        if _RANK[level] > _RANK[highest]:
            highest = level
        previous = node
    return highest


def _classify_node(node: _CommandNode) -> RiskLevel:
    tokens, elevated = _unwrap_command(list(node.tokens))
    if not tokens:
        return "act_low"
    executable = _basename(tokens[0])
    args = tokens[1:]

    if executable in _SHELLS:
        command_arg = _shell_command_argument(args)
        if command_arg is not None:
            inner = classify_command_level(command_arg)
            return _max_level("destructive" if elevated else "read", inner)
    if executable == "eval" and args:
        return classify_command_level(" ".join(args))
    if executable in _SHUTDOWN_EXECUTABLES:
        return "critical"
    if executable == "init" and next(
        (arg for arg in args if not arg.startswith("-")), None
    ) in {"0", "6"}:
        return "critical"
    if executable.startswith("mkfs"):
        return "critical"
    if executable == "dd" and any(
        _is_block_device_assignment(arg, "of") for arg in args
    ):
        return "critical"
    if _redirects_to_block_device(tokens):
        return "critical"
    if executable == "rm" and _recursive_rm_targets_root(args):
        return "critical"
    if executable == "chmod" and _recursive_chmod_targets_root(args):
        return "critical"

    has_write_redirect = any(token in {">", ">>"} for token in tokens)
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
    elevated = False
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
            tokens = _skip_sudo_options(tokens)
        elif executable == "env":
            while tokens and (
                tokens[0].startswith("-")
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0])
            ):
                tokens.pop(0)
        elif executable == "timeout":
            while tokens and tokens[0].startswith("-"):
                tokens.pop(0)
            if tokens:
                tokens.pop(0)
        elif executable == "nice":
            if tokens[:1] == ["-n"]:
                tokens = tokens[2:]
            else:
                while tokens and tokens[0].startswith("-"):
                    tokens.pop(0)
        elif executable == "setsid":
            while tokens and tokens[0].startswith("-"):
                tokens.pop(0)
    return tokens, elevated


def _skip_sudo_options(tokens: list[str]) -> list[str]:
    takes_value = {"-u", "-g", "-h", "-p", "-C", "-T", "-R", "-D"}
    index = 0
    while index < len(tokens) and tokens[index].startswith("-"):
        option = tokens[index]
        index += 1
        if option in takes_value and index < len(tokens):
            index += 1
    return tokens[index:]


def _shell_command_argument(args: list[str]) -> str | None:
    for index, arg in enumerate(args):
        if arg in {"-c", "-lc", "-ic"} and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith("-") and "c" in arg[1:] and index + 1 < len(args):
            return args[index + 1]
    return None


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


def _redirects_to_block_device(tokens: list[str]) -> bool:
    return any(
        tokens[index] in {">", ">>"} and _is_block_device(tokens[index + 1])
        for index in range(len(tokens) - 1)
    )


def _is_block_device_assignment(value: str, key: str) -> bool:
    return value.startswith(f"{key}=") and _is_block_device(value.split("=", 1)[1])


def _is_block_device(path: str) -> bool:
    return bool(re.match(r"^/dev/(?:sd|hd|vd|xvd|nvme|disk|mapper/)", path))


def _classify_git(args: list[str]) -> RiskLevel:
    subcommand = next((arg for arg in args if not arg.startswith("-")), None)
    if subcommand is None:
        return "act_low"
    if (subcommand == "reset" and "--hard" in args) or (
        subcommand == "clean" and any(arg.startswith("-f") for arg in args)
    ):
        return "destructive"
    if subcommand in _GIT_EXTERNAL:
        return "external"
    if subcommand in _GIT_READ:
        return "act_low"
    return "act_high"


def _classify_docker(args: list[str]) -> RiskLevel:
    subcommand = next((arg for arg in args if not arg.startswith("-")), None)
    if subcommand is None:
        return "act_low"
    if subcommand == "system":
        return "destructive" if "prune" in args else "act_low"
    if subcommand in _DOCKER_DESTRUCTIVE:
        return "destructive"
    if subcommand in _DOCKER_EXTERNAL:
        return "external"
    if subcommand in _DOCKER_READ:
        return "act_low"
    return "act_high"


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
        return any(arg in {"avail", "list", "show", "whatis", "help"} for arg in args)
    if executable in {"squeue", "sinfo", "sacct", "qstat", "nextflow"}:
        return True
    if not executable.endswith("cli"):
        return False
    read_verbs = {"list", "get", "show", "status", "describe", "version", "info"}
    write_verbs = {
        "create",
        "delete",
        "remove",
        "submit",
        "cancel",
        "update",
        "set",
        "start",
        "stop",
        "run",
        "launch",
        "register",
        "install",
    }
    words = {arg.casefold() for arg in args if not arg.startswith("-")}
    return bool(words & read_verbs) and not bool(words & write_verbs)


def _command_effects(nodes: list[_CommandNode]) -> list[str]:
    effects: list[str] = []
    for node in nodes:
        tokens, elevated = _unwrap_command(list(node.tokens))
        if not tokens:
            continue
        executable = _basename(tokens[0])
        args = tokens[1:]
        if elevated:
            effects.append("privilege")
        if executable in _SHELLS:
            inner = _shell_command_argument(args)
            if inner is not None:
                effects.extend(
                    _command_effects(_parse_command_nodes(_strip_heredoc_bodies(inner)))
                )
                continue
        if executable in {"rm", "rmdir", "shred"}:
            effects.append("delete")
        elif executable in {"kill", "pkill", "killall", *_SHUTDOWN_EXECUTABLES}:
            effects.append("process_control")
        elif executable in _EXTERNAL_EXECUTABLES or executable in _INSTALL_EXECUTABLES:
            effects.append("network")
        elif _node_writes(tokens, executable, args):
            effects.append("write")
        elif (
            executable in _READ_EXECUTABLES
            or executable in {"git", "docker"}
            or _is_read_only_platform_command(executable, args)
        ):
            effects.append("read")
        else:
            effects.append("execute")
    return _dedupe(effects) or ["execute"]


def _node_writes(tokens: list[str], executable: str, args: list[str]) -> bool:
    if any(token in {">", ">>"} for token in tokens):
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
    }:
        return True
    return executable in {"sed", "perl"} and any(arg.startswith("-i") for arg in args)


def _referenced_paths(
    nodes: list[_CommandNode], *, target: CommandTargetProfile
) -> list[str]:
    paths: list[str] = []
    for node in nodes:
        tokens, _ = _unwrap_command(list(node.tokens))
        if not tokens:
            continue
        executable = _basename(tokens[0])
        args = tokens[1:]
        if executable in _SHELLS:
            inner = _shell_command_argument(args)
            if inner is not None:
                paths.extend(
                    _referenced_paths(
                        _parse_command_nodes(_strip_heredoc_bodies(inner)),
                        target=target,
                    )
                )
                continue
        for index, token in enumerate(tokens[:-1]):
            if token in {">", ">>", "<", "<<"}:
                paths.append(_canonical_reference(tokens[index + 1], target))
        file_args = _file_arguments(executable, args)
        paths.extend(_canonical_reference(arg, target) for arg in file_args)
    return _dedupe(_bounded_strings(paths, limit=32, width=1000))


def _file_arguments(executable: str, args: list[str]) -> list[str]:
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
    }
    if executable not in file_commands:
        return []
    if executable in {"sed", "perl"}:
        return _editor_file_arguments(args)
    values: list[str] = []
    for arg in args:
        if arg.startswith("-") or arg in {"{}", "+", ";"}:
            continue
        if executable in {"head", "tail"} and arg.isdigit():
            continue
        values.append(arg)
    return values


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

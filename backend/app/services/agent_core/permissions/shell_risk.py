"""Heuristic risk classification for free-form shell commands.

The real Bash tool runs arbitrary command strings, so a flat risk level would
either block useful work or auto-run dangerous commands. This classifier maps a
command string to a :class:`RiskLevel` so the existing permission policy can
keep "auto-run safe shell, ask before dangerous shell, hard-block catastrophic
shell" without any special casing downstream.

The mapping under ``guarded_auto`` is:
- ``read`` / ``act_low``  → auto-run (safe inspection, read-only platform/git/docker)
- ``act_high`` / ``destructive`` / ``external`` → ask for approval
- ``critical`` → hard-blocked
"""

from __future__ import annotations

import re

from app.services.agent_core.permissions.risk import RiskLevel


# Catastrophic patterns. These are blocked outright (critical) rather than
# surfaced for approval — there is no safe way to approve `rm -rf /`.
_CRITICAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r":\s*\(\s*\)\s*\{.*\|.*&\s*\}\s*;"),  # fork bomb :(){ :|:& };:
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\b[^\n]*\bof=/dev/"),
    re.compile(r">\s*/dev/(sd|nvme|hd|disk)"),
    re.compile(r"\bof=/dev/(sd|nvme|hd|disk)"),
    re.compile(r"\bchmod\s+(-[a-z]*\s+)*-R[a-z]*\s+[0-7]{3,4}\s+/\s*$"),
    re.compile(r"\b(shutdown|reboot|halt|poweroff|init\s+0|init\s+6)\b"),
    re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba)?sh\b"),  # curl … | sh
)

# Command/process substitution and write redirection hide work from a
# leading-executable scan, so their presence raises the floor to "ask".
_SUBSTITUTION_RE = re.compile(r"\$\(|`|<\(")
_REDIRECT_RE = re.compile(r"(?<![0-9<>&])>>?")

# Root-ish `rm` targets that make a recursive delete catastrophic.
_RM_ROOT_TARGETS = frozenset({"/", "/*", "~", "$HOME", "/.", "/..", ".."})

# Executables that run a following command, masking it from the leading-token
# scan (e.g. `env rm -rf x`). They are unwrapped and the inner command is
# classified instead.
_WRAPPER_EXECUTABLES = frozenset({"env"})

# Read-only leading executables — safe to auto-run.
_READ_EXECUTABLES = frozenset(
    {
        "ls", "cat", "head", "tail", "pwd", "echo", "wc", "file", "stat",
        "tree", "printenv", "date", "whoami", "which", "type", "du",
        "df", "ps", "uname", "hostname", "basename", "dirname", "realpath",
        "readlink", "sort", "uniq", "cut", "tr", "grep", "egrep", "fgrep",
        "rg", "find", "fd", "jq", "yq", "diff", "comm", "column", "nl",
        "true", "false", "test", "id", "groups", "less", "more", "tldr",
        "man", "help", "history",
    }
)

# Network / external-effect executables — ask before running.
_EXTERNAL_EXECUTABLES = frozenset(
    {
        "curl", "wget", "ssh", "scp", "sftp", "rsync", "nc", "ncat",
        "telnet", "ping", "dig", "nslookup", "host", "ftp",
    }
)

# Package managers / installers reach the network — ask before running.
_INSTALL_EXECUTABLES = frozenset(
    {
        "pip", "pip3", "npm", "pnpm", "yarn", "bun", "uv", "apt", "apt-get",
        "yum", "dnf", "brew", "cargo", "go", "gem", "poetry", "conda", "mamba",
    }
)

# Destructive local executables — ask before running.
_DESTRUCTIVE_EXECUTABLES = frozenset(
    {
        "rm", "rmdir", "shred", "truncate", "kill", "pkill", "killall",
        "sudo", "chown", "chmod", "mkfs", "fdisk", "parted", "dd",
    }
)

_GIT_READ_SUBCOMMANDS = frozenset(
    {"status", "log", "diff", "show", "branch", "rev-parse", "ls-files",
     "ls-remote", "describe", "blame", "tag", "remote", "config", "cat-file",
     "shortlog", "reflog", "whatchanged"}
)
_GIT_EXTERNAL_SUBCOMMANDS = frozenset({"push", "pull", "fetch", "clone", "submodule"})
_GIT_DESTRUCTIVE = (("reset", "--hard"), ("clean", "-f"), ("clean", "-d"))

_DOCKER_READ_SUBCOMMANDS = frozenset(
    {"ps", "images", "image", "inspect", "logs", "version", "info", "stats",
     "top", "port", "history", "search", "context", "system"}
)
_DOCKER_DESTRUCTIVE_SUBCOMMANDS = frozenset({"rm", "rmi", "prune", "kill", "stop", "volume", "system"})
_DOCKER_EXTERNAL_SUBCOMMANDS = frozenset({"pull", "push", "login", "logout"})

_OPERATOR_SPLIT = re.compile(r"\|\||&&|\||;|\n")

_RANK: dict[RiskLevel, int] = {
    "read": 0,
    "act_low": 1,
    "external": 2,
    "act_high": 2,
    "destructive": 3,
    "critical": 4,
}


def classify_shell_command(command: str) -> RiskLevel:
    """Classify a shell command string into a :class:`RiskLevel`.

    Catastrophic patterns are ``critical``. Otherwise the command is split on
    shell operators and each segment's leading executable is classified; the
    highest-risk segment wins. Unknown commands default to ``act_high`` (ask).
    """
    text = (command or "").strip()
    if not text:
        return "act_low"

    for pattern in _CRITICAL_PATTERNS:
        if pattern.search(text):
            return "critical"
    if _is_catastrophic_rm(text):
        return "critical"

    # Command/process substitution hides commands the per-segment scan cannot
    # see, so it can never auto-run.
    highest: RiskLevel = "act_high" if _SUBSTITUTION_RE.search(text) else "read"
    for segment in _OPERATOR_SPLIT.split(text):
        level = _classify_segment(segment)
        if level == "critical":
            return "critical"
        if _RANK[level] > _RANK[highest]:
            highest = level
    return highest


def _is_catastrophic_rm(text: str) -> bool:
    """True when an ``rm`` invocation recursively targets a root-ish path."""
    for match in re.finditer(r"\brm\b([^|&;\n]*)", text):
        recursive = False
        targets: list[str] = []
        for token in match.group(1).split():
            if token.startswith("--"):
                recursive = recursive or token == "--recursive"
            elif token.startswith("-"):
                recursive = recursive or "r" in token.lower()
            else:
                # Strip shell quotes so `rm -rf "/"` / `rm -rf '$HOME'` still
                # match the root-target set instead of slipping to destructive.
                targets.append(token.strip("\"'"))
        if recursive and any(target in _RM_ROOT_TARGETS for target in targets):
            return True
    return False


def _classify_segment(segment: str) -> RiskLevel:
    tokens = segment.strip().split()
    if not tokens:
        return "read"
    # Skip leading env-var assignments like `FOO=bar cmd`.
    index = 0
    while index < len(tokens) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[index]):
        index += 1
    if index >= len(tokens):
        return "act_low"
    executable = tokens[index].rsplit("/", 1)[-1]
    rest = tokens[index + 1 :]

    if executable in _WRAPPER_EXECUTABLES:
        # `env [-flags] [VAR=val ...] cmd …` — classify the wrapped command.
        inner = rest
        while inner and (
            inner[0].startswith("-")
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", inner[0])
        ):
            inner = inner[1:]
        return _classify_segment(" ".join(inner)) if inner else "act_low"

    # A write redirection turns any command into a filesystem mutation, even
    # when the leading executable only reads.
    has_write_redirect = bool(_REDIRECT_RE.search(segment))

    if executable in _DESTRUCTIVE_EXECUTABLES:
        return "destructive"
    if executable in _EXTERNAL_EXECUTABLES or executable in _INSTALL_EXECUTABLES:
        return "external"
    if executable == "git":
        return _classify_git(rest)
    if executable == "docker":
        return _classify_docker(rest)
    if executable in {"sed", "perl"} and any(arg.startswith("-i") for arg in rest):
        return "act_high"  # in-place edit
    if executable == "find" and any(
        arg in {"-exec", "-execdir", "-ok", "-okdir", "-delete"} for arg in rest
    ):
        return "act_high"  # find runs an arbitrary command per match
    if executable in _READ_EXECUTABLES:
        return "act_high" if has_write_redirect else "act_low"
    # Unknown executable: be conservative and ask.
    return "act_high"


def _classify_git(args: list[str]) -> RiskLevel:
    subcommand = next((arg for arg in args if not arg.startswith("-")), None)
    if subcommand is None:
        return "act_low"
    for sub, flag in _GIT_DESTRUCTIVE:
        if subcommand == sub and flag in args:
            return "destructive"
    if subcommand in _GIT_EXTERNAL_SUBCOMMANDS:
        return "external"
    if subcommand in _GIT_READ_SUBCOMMANDS:
        return "act_low"
    return "act_high"


def _classify_docker(args: list[str]) -> RiskLevel:
    subcommand = next((arg for arg in args if not arg.startswith("-")), None)
    if subcommand is None:
        return "act_low"
    # `docker system prune` is destructive; `docker system info` is read.
    if subcommand == "system":
        return "destructive" if "prune" in args else "act_low"
    if subcommand in _DOCKER_DESTRUCTIVE_SUBCOMMANDS:
        return "destructive"
    if subcommand in _DOCKER_EXTERNAL_SUBCOMMANDS:
        return "external"
    if subcommand in _DOCKER_READ_SUBCOMMANDS:
        return "act_low"
    return "act_high"  # run, build, exec, start, …

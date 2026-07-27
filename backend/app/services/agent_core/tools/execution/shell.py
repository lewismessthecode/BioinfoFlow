from __future__ import annotations

import asyncio
import fnmatch
import os
import re
import shlex
import shutil
import signal
import tempfile
from collections.abc import Awaitable, Callable
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.path_layout import (
    agent_attachments_root,
    agent_session_attachments_root,
    safe_path_name,
)
from app.services.agent_core.permissions.command_risk import (
    CommandRiskAssessment,
    CommandTargetProfile,
    assess_command_risk,
)
from app.services.agent_core.sandbox import (
    FilesystemPolicy,
    SandboxRunner,
    SandboxUnavailableError,
    local_boundary_from_tool_context,
)
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.agent_core.tools.web.public_url_policy import (
    PublicUrl,
    validate_public_url,
)
from app.utils.exceptions import PermissionDeniedError


class ExecuteShellTool:
    """Run a real shell command via ``bash -lc``.

    Unlike a fixed argv runner, this supports pipes, globs, redirects, and
    ``&&`` chains so the agent can use the shell the way a developer would
    (`ls`, `grep`, `rg`, `find`, `git`, `docker`, …). Safety comes from two
    places: the working directory is constrained to the allowed roots, and the
    command string is risk-classified so the permission policy auto-runs safe
    commands, asks before dangerous or catastrophic ones, and denies explicit
    authorization or target violations.
    """

    spec = AgentToolSpec(
        name="bash",
        description=(
            "Run a shell command via bash. Supports pipes, globs, redirects, and "
            "&& chains. rg/rg --files, jq, and sed are ordinary commands executed "
            "inside this tool. Prefer structured Bioinfoflow platform tools for "
            "projects, workflows, runs, scheduler state, and remote connections. "
            "Use web.search to discover URLs, then agent-browser read/open and "
            "domain-bound snapshot/click/get commands to browse them. "
            "Dangerous commands require approval."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "minLength": 1},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600},
                "output_limit": {"type": "integer", "minimum": 100, "maximum": 50000},
                "description": {"type": "string"},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "exit_code": {"type": "integer"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "cwd": {"type": "string"},
                "command": {"type": "string"},
            },
            "required": ["exit_code", "stdout", "stderr", "cwd", "command"],
        },
        risk_level="act_high",
        read_scope=["workspace"],
        write_scope=["workspace"],
        audit="Execute a shell command via bash.",
        rollback_hint="Inspect command output and generated artifacts; reverse any file changes via version control.",
        timeout_seconds=120,
        artifact_policy={"stdout": True, "stderr": True, "type": "command"},
    )

    def assess_risk(
        self,
        input: dict[str, Any],
        *,
        target: CommandTargetProfile | None = None,
    ) -> CommandRiskAssessment | None:
        command = input.get("command")
        if not isinstance(command, str) or not command.strip():
            return None
        if target is None:
            policy = FilesystemPolicy()
            roots = tuple(str(root) for root in policy.allowed_roots)
            runner = SandboxRunner.from_settings()
            target = CommandTargetProfile(
                kind="local",
                trust_domain="local-machine",
                identity="local-user",
                sandbox_strength="enforced"
                if runner.enabled and runner.available_adapter()
                else "none",
                read_roots=roots,
                write_roots=roots,
                working_directory=str(input.get("cwd") or policy.default_root),
                network_allowed=runner.allow_network,
                sandbox_bypass_requested=False,
            )
        return assess_command_risk(command, target=target)

    def result_error(self, result: dict[str, Any]) -> dict[str, Any] | None:
        exit_code = result.get("exit_code")
        if not isinstance(exit_code, int) or exit_code == 0:
            return None
        return {
            "type": "CommandExitError",
            "message": f"Command exited with code {exit_code}.",
        }

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        boundary = await local_boundary_from_tool_context(context)
        command = input.get("command")
        if not isinstance(command, str) or not command.strip():
            raise PermissionDeniedError("command must be a non-empty string")
        cwd = boundary.policy.require_allowed_dir(
            input.get("cwd") or str(boundary.working_directory)
        )
        timeout = int(input.get("timeout_seconds") or 120)
        output_limit = int(input.get("output_limit") or 16000)
        command = await _normalize_agent_browser_command(command)
        session_attachment_root = agent_session_attachments_root(context.session_id)
        process_cwd, process_env, cleanup_root = _agent_browser_process_context(
            command=command,
            requested_cwd=cwd,
            session_id=context.session_id,
            runtime_root=cwd / ".bioinfoflow-agent-browser",
            base_env=os.environ,
        )
        attachment_store = agent_attachments_root()
        _reject_static_protected_mutation(command, attachment_store, cwd)

        # The OS sandbox — not the risk classifier — is the real boundary. When
        # enabled it confines writes to session capability roots. Bubblewrap also
        # confines reads to those roots; macOS Seatbelt applies permanent deny
        # rules for product source, internal state, and the Docker socket.
        runner = SandboxRunner.from_settings()
        if not runner.enabled:
            raise SandboxUnavailableError(
                "agent bash requires OS sandboxing; AGENT_SANDBOX_ENABLED cannot be false"
            )
        sandbox = runner.build(
            command=command,
            cwd=process_cwd,
            read_roots=[*boundary.read_roots, session_attachment_root],
            write_roots=list(boundary.write_roots),
            protected_roots=list(boundary.protected_roots),
            protected_read_roots=[session_attachment_root],
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *sandbox.argv,
                cwd=str(process_cwd),
                env=process_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError as exc:
                await _kill_process_group(process)
                raise TimeoutError(f"command timed out after {timeout}s") from exc
            except asyncio.CancelledError:
                await _kill_process_group(process)
                raise
        finally:
            if cleanup_root is not None:
                shutil.rmtree(cleanup_root, ignore_errors=True)

        return {
            "exit_code": int(process.returncode or 0),
            "stdout": _limit(stdout.decode("utf-8", errors="replace"), output_limit),
            "stderr": _limit(stderr.decode("utf-8", errors="replace"), output_limit),
            "cwd": str(process_cwd),
            "command": command,
        }


def _limit(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"


_AGENT_BROWSER_BLOCKED_FLAGS = frozenset(
    {
        "--cdp",
        "--auto-connect",
        "--profile",
        "--restore",
        "--state",
        "--proxy",
        "--args",
        "--init-script",
        "--extension",
    }
)
_AGENT_BROWSER_ALLOWED_ACTIONS = frozenset({"read", "open", "snapshot", "click", "get"})
_AGENT_BROWSER_URL_ACTIONS = frozenset({"read", "open"})
_AGENT_BROWSER_SAFE_FLAGS = frozenset({"--session", "--allowed-domains"})


async def _normalize_agent_browser_command(
    command: str,
    *,
    url_validator: Callable[[str], Awaitable[PublicUrl]] = validate_public_url,
) -> str:
    candidate = _agent_browser_candidate(command)
    if candidate is None:
        return command
    if candidate == "ambiguous":
        _raise_agent_browser_error("shell expansion or indirection is not allowed")
    if any(
        marker in command for marker in ("\n", "\r", "$(", "`", "|", ";", "&", ">", "<")
    ):
        _raise_agent_browser_error("shell composition is not allowed")
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise PermissionDeniedError("Invalid agent-browser command") from exc
    if len(tokens) < 2 or Path(tokens[0]).name != "agent-browser":
        _raise_agent_browser_error("must be invoked directly")
    action, positional_arguments = _parse_agent_browser_argv(tokens)
    for token in tokens[1:]:
        flag = token.split("=", 1)[0]
        if flag in _AGENT_BROWSER_BLOCKED_FLAGS:
            _raise_agent_browser_error(f"flag {flag!r} is not allowed")

    if action in _AGENT_BROWSER_URL_ACTIONS:
        if not positional_arguments:
            _raise_agent_browser_error(f"{action} requires a URL")
        if len(positional_arguments) != 1:
            _raise_agent_browser_error(f"{action} accepts exactly one URL")
        validated = await url_validator(positional_arguments[0])
        tokens = _without_allowed_domains(tokens)
        tokens.extend(["--allowed-domains", validated.host])
        return shlex.join(tokens)

    domains = _allowed_domains(tokens)
    if not domains:
        _raise_agent_browser_error("interactive commands require --allowed-domains")
    validated_domains: list[str] = []
    for domain in domains.split(","):
        validated = await url_validator(f"https://{domain.strip()}")
        validated_domains.append(validated.host)
    tokens = _without_allowed_domains(tokens)
    tokens.extend(["--allowed-domains", ",".join(validated_domains)])
    return shlex.join(tokens)


def _agent_browser_candidate(command: str) -> str | None:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;")
        lexer.whitespace_split = True
        shell_tokens = list(lexer)
    except ValueError:
        if "agent-" in command or "agent-browser" in command:
            return "ambiguous"
        return None

    if not _command_tokens_contain_agent_browser(shell_tokens):
        return None
    try:
        direct_tokens = shlex.split(command)
    except ValueError:
        return "ambiguous"
    if direct_tokens and Path(direct_tokens[0]).name == "agent-browser":
        return "direct"
    return "ambiguous"


def _command_tokens_contain_agent_browser(tokens: list[str]) -> bool:
    segment: list[str] = []
    for token in [*tokens, ";"]:
        if re.fullmatch(r"[|&;]+", token):
            if _command_segment_contains_agent_browser(segment):
                return True
            segment = []
            continue
        segment.append(token)
    return False


def _command_segment_contains_agent_browser(tokens: list[str]) -> bool:
    index = 0
    while index < len(tokens) and _is_shell_assignment(tokens[index]):
        index += 1
    if index >= len(tokens):
        return False
    executable = tokens[index]
    if _could_expand_to_agent_browser(executable):
        return True

    executable_name = Path(executable).name
    if executable_name in {"bash", "sh", "zsh"}:
        for flag_index in range(index + 1, len(tokens) - 1):
            flag = tokens[flag_index]
            if flag.startswith("-") and "c" in flag.lstrip("-"):
                return _agent_browser_candidate(tokens[flag_index + 1]) is not None
    if executable_name == "env":
        nested_index = _env_command_index(tokens, index + 1)
        if nested_index is None:
            return False
        return _could_expand_to_agent_browser(tokens[nested_index])
    if executable_name in {"command", "exec", "nohup"}:
        nested_index = index + 1
        while nested_index < len(tokens):
            token = tokens[nested_index]
            if token.startswith("-") or _is_shell_assignment(token):
                nested_index += 1
                continue
            return _could_expand_to_agent_browser(token)
    return False


def _env_command_index(tokens: list[str], start: int) -> int | None:
    value_flags = {"-u", "--unset", "-C", "--chdir", "-S", "--split-string", "--argv0"}
    index = start
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1 if index + 1 < len(tokens) else None
        flag = token.split("=", 1)[0]
        if flag in value_flags:
            index += 1 if "=" in token else 2
            continue
        if token.startswith("-") or _is_shell_assignment(token):
            index += 1
            continue
        return index
    return None


def _is_shell_assignment(token: str) -> bool:
    return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token) is not None


def _could_expand_to_agent_browser(executable: str) -> bool:
    name = Path(executable).name
    if name == "agent-browser":
        return True
    if "$(" in name:
        return True
    brace = re.search(r"\{([^{}]+)\}", name)
    if brace:
        return any(
            _could_expand_to_agent_browser(
                name[: brace.start()] + option + name[brace.end() :]
            )
            for option in brace.group(1).split(",")
        )
    pattern = re.sub(r"\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*", "*", name)
    return fnmatch.fnmatchcase("agent-browser", pattern)


def _agent_browser_process_context(
    *,
    command: str,
    requested_cwd: Path,
    session_id: str,
    runtime_root: Path,
    base_env: Mapping[str, str],
) -> tuple[Path, dict[str, str] | None, Path | None]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return requested_cwd, None, None
    if not tokens or Path(tokens[0]).name != "agent-browser":
        return requested_cwd, None, None

    safe_session_id = safe_path_name(session_id, field_name="agent session id")
    session_root = runtime_root / safe_session_id
    session_root.mkdir(parents=True, exist_ok=True)
    invocation_root = Path(tempfile.mkdtemp(prefix="invocation-", dir=session_root))
    process_cwd = invocation_root / "cwd"
    explicit_config = invocation_root / "config.json"
    home = session_root / "home"
    config_home = session_root / "config"
    data_home = session_root / "data"
    state_home = session_root / "state"
    cache_home = session_root / "cache"
    for directory in (
        process_cwd,
        home,
        config_home,
        data_home,
        state_home,
        cache_home,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    explicit_config.write_text("{}\n", encoding="utf-8")
    explicit_config.chmod(0o600)

    executable_path = base_env.get("AGENT_BROWSER_EXECUTABLE_PATH")
    process_env = {
        key: value
        for key, value in base_env.items()
        if not key.startswith("AGENT_BROWSER_")
        and key.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    }
    process_env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_DATA_HOME": str(data_home),
            "XDG_STATE_HOME": str(state_home),
            "XDG_CACHE_HOME": str(cache_home),
            "AGENT_BROWSER_CONFIG": str(explicit_config),
            "AGENT_BROWSER_NAMESPACE": f"bioinfoflow-{safe_session_id}",
        }
    )
    if executable_path:
        process_env["AGENT_BROWSER_EXECUTABLE_PATH"] = executable_path
    return process_cwd, process_env, invocation_root


def _parse_agent_browser_argv(tokens: list[str]) -> tuple[str, list[str]]:
    action: str | None = None
    positional_arguments: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("-"):
            flag = token.split("=", 1)[0]
            if flag not in _AGENT_BROWSER_SAFE_FLAGS:
                _raise_agent_browser_error(f"flag {flag!r} is not allowed")
            if "=" in token:
                if not token.split("=", 1)[1]:
                    _raise_agent_browser_error(f"flag {flag!r} requires a value")
                index += 1
                continue
            if index + 1 >= len(tokens) or tokens[index + 1].startswith("-"):
                _raise_agent_browser_error(f"flag {flag!r} requires a value")
            index += 2
            continue
        if action is None:
            candidate = token.lower()
            if candidate not in _AGENT_BROWSER_ALLOWED_ACTIONS:
                _raise_agent_browser_error(f"action {candidate!r} is not allowed")
            action = candidate
        else:
            positional_arguments.append(token)
        index += 1
    if action is None:
        _raise_agent_browser_error("an allowed action is required")
    return action, positional_arguments


def _allowed_domains(tokens: list[str]) -> str | None:
    for index, token in enumerate(tokens):
        if token == "--allowed-domains" and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith("--allowed-domains="):
            return token.split("=", 1)[1]
    return None


def _without_allowed_domains(tokens: list[str]) -> list[str]:
    normalized: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--allowed-domains":
            index += 2
            continue
        if token.startswith("--allowed-domains="):
            index += 1
            continue
        normalized.append(token)
        index += 1
    return normalized


def _raise_agent_browser_error(reason: str) -> None:
    raise PermissionDeniedError(f"Unsafe agent-browser command: {reason}")


def _reject_static_protected_mutation(
    command: str, protected_root: Path, cwd: Path
) -> None:
    root = protected_root.expanduser().resolve()
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        _raise_protected_attachment_error()
    if not _references_protected_path(tokens, cwd=cwd, protected_root=root):
        return
    if not _is_explicit_read_only_attachment_command(command, tokens):
        _raise_protected_attachment_error()


def _is_explicit_read_only_attachment_command(command: str, tokens: list[str]) -> bool:
    if "\n" in command or "\r" in command or "$(" in command or "`" in command:
        return False
    if any(re.fullmatch(r"[|&;<>]+", token) for token in tokens):
        return False
    if not tokens:
        return False

    read_only_commands = {
        "cat",
        "file",
        "grep",
        "head",
        "ls",
        "rg",
        "sed",
        "tail",
        "find",
    }
    command_name = Path(tokens[0]).name
    if command_name not in read_only_commands:
        return False
    arguments = tokens[1:]
    if command_name == "sed" and not _sed_is_read_only(arguments):
        return False
    if command_name == "find" and any(
        argument
        in {
            "-delete",
            "-exec",
            "-execdir",
            "-ok",
            "-okdir",
            "-fprint",
            "-fprint0",
            "-fprintf",
            "-fls",
        }
        for argument in arguments
    ):
        return False
    if command_name == "rg" and any(
        argument == "--pre" or argument.startswith("--pre=") for argument in arguments
    ):
        return False
    return True


def _sed_is_read_only(arguments: list[str]) -> bool:
    if any(
        argument in {"-i", "--in-place", "-f", "--file"}
        or argument.startswith(("-i", "--in-place=", "--file="))
        for argument in arguments
    ):
        return False
    scripts: list[str] = []
    for index, argument in enumerate(arguments):
        if argument in {"-e", "--expression"}:
            if index + 1 >= len(arguments):
                return False
            scripts.append(arguments[index + 1])
        elif argument.startswith("--expression="):
            scripts.append(argument.split("=", 1)[1])
    if not scripts:
        scripts = [argument for argument in arguments if not argument.startswith("-")][
            :1
        ]
    return bool(scripts) and not any(
        re.search(r"(?:^|[;{}])\s*(?:\d+(?:,\d+)?|\$|/[^/]*/)?\s*[wWe](?:\s|$)", script)
        or re.search(r"s([^\w\s]).*?\1.*?\1[A-Za-z]*[ewW]", script)
        for script in scripts
    )


def _references_protected_path(
    tokens: list[str], *, cwd: Path, protected_root: Path
) -> bool:
    bioinfoflow_home = protected_root.parents[2]
    for raw_candidate in _path_candidates(tokens):
        raw_candidate = raw_candidate.replace(
            "${BIOINFOFLOW_HOME}", str(bioinfoflow_home)
        ).replace("$BIOINFOFLOW_HOME", str(bioinfoflow_home))
        candidate = Path(raw_candidate).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        try:
            candidate.resolve(strict=False).relative_to(protected_root)
        except (OSError, RuntimeError, ValueError):
            continue
        return True
    return False


def _path_candidates(tokens: list[str]) -> set[str]:
    candidates: set[str] = set()
    pending = list(tokens)
    while pending:
        token = pending.pop()
        if not token or re.fullmatch(r"[|&;<>]+", token):
            continue
        candidates.add(token)
        if "=" in token:
            candidates.add(token.split("=", 1)[1])
        candidates.update(re.findall(r"/[^\s'\";|&<>),]+", token))
        candidates.update(re.findall(r"[rR]?[\"']([^\"']+)[\"']", token))
        if any(character.isspace() for character in token):
            try:
                nested = shlex.split(token)
            except ValueError:
                continue
            if nested != [token]:
                pending.extend(nested)
    return candidates


def _raise_protected_attachment_error() -> None:
    raise PermissionDeniedError("Command targets the protected attachment store")


async def _kill_process_group(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    await process.wait()

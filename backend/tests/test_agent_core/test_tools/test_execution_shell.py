from __future__ import annotations

import asyncio
import os
import shlex
import sys
from pathlib import Path

import pytest

from app.config import settings
from app.repositories.agent_core_repo import AgentActionRepository
from app.models.project import Project
from app.models.workspace import Workspace
from app.path_layout import (
    agent_attachments_root,
    agent_session_attachments_root,
    project_home,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.specs import AgentToolSpec
from app.services.agent_core.tools.execution import ExecuteShellTool
from app.services.agent_core.tools.execution.shell import (
    _agent_browser_process_context,
    _normalize_agent_browser_command,
)
from app.services.agent_core.tools.web.public_url_policy import PublicUrl
from app.utils.exceptions import PermissionDeniedError
from app.workspace import DEFAULT_WORKSPACE_ID


@pytest.fixture(autouse=True)
def _run_shell_without_platform_sandbox_for_tool_tests(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_core.tools.execution.shell.SandboxRunner.build",
        lambda self, **kwargs: type(
            "SandboxResult",
            (),
            {"argv": ["bash", "-lc", kwargs["command"]]},
        )(),
    )


def test_bash_assess_risk_escalates_out_of_root_paths():
    tool = ExecuteShellTool()
    # Safe inspection inside the sandbox auto-runs.
    assert tool.assess_risk({"command": "cat README.md"}).level == "act_low"
    # Reaching an absolute path outside the allowed roots must ask, even though
    # `cat`/`find` are read-only executables.
    assert tool.assess_risk({"command": "cat /etc/passwd"}).level == "act_high"
    assert tool.assess_risk({"command": "find / -maxdepth 1"}).level == "act_high"
    assert tool.assess_risk({"command": "cat $HOME/.ssh/id_rsa"}).level == "act_high"


async def _allow_example_url(url: str) -> PublicUrl:
    assert url.startswith(("http://", "https://"))
    return PublicUrl(url=url, host="example.com")


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["read", "open"])
async def test_agent_browser_url_actions_force_validated_allowed_domain(action: str):
    normalized = await _normalize_agent_browser_command(
        f"agent-browser {action} https://example.com/docs",
        url_validator=_allow_example_url,
    )

    assert shlex.split(normalized) == [
        "agent-browser",
        action,
        "https://example.com/docs",
        "--allowed-domains",
        "example.com",
    ]


@pytest.mark.asyncio
async def test_agent_browser_url_actions_replace_caller_allowed_domains():
    normalized = await _normalize_agent_browser_command(
        "agent-browser open https://example.com --allowed-domains attacker.example",
        url_validator=_allow_example_url,
    )

    assert shlex.split(normalized)[-2:] == ["--allowed-domains", "example.com"]
    assert "attacker.example" not in normalized


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["read", "open"])
async def test_agent_browser_url_actions_parse_safe_global_flags_around_action(
    action: str,
):
    normalized = await _normalize_agent_browser_command(
        f"agent-browser --allowed-domains attacker.example --session work "
        f"{action} --session work https://example.com/docs",
        url_validator=_allow_example_url,
    )

    tokens = shlex.split(normalized)
    assert action in tokens
    assert "https://example.com/docs" in tokens
    assert "attacker.example" not in tokens
    assert tokens[-2:] == ["--allowed-domains", "example.com"]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["read", "open"])
async def test_agent_browser_url_actions_locate_url_after_safe_flag(action: str):
    normalized = await _normalize_agent_browser_command(
        f"agent-browser {action} --session work https://example.com/docs",
        url_validator=_allow_example_url,
    )

    assert "https://example.com/docs" in shlex.split(normalized)


@pytest.mark.asyncio
async def test_agent_browser_interaction_requires_validated_allowed_domains():
    normalized = await _normalize_agent_browser_command(
        "agent-browser snapshot --allowed-domains example.com",
        url_validator=_allow_example_url,
    )

    assert shlex.split(normalized) == [
        "agent-browser",
        "snapshot",
        "--allowed-domains",
        "example.com",
    ]


@pytest.mark.asyncio
async def test_agent_browser_interaction_rejects_missing_allowed_domains():
    with pytest.raises(PermissionDeniedError, match="allowed-domains"):
        await _normalize_agent_browser_command(
            "agent-browser click @e1", url_validator=_allow_example_url
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["back", "close", "download", "screenshot", "wait"])
async def test_agent_browser_rejects_actions_outside_explicit_allowlist(action: str):
    with pytest.raises(PermissionDeniedError, match="agent-browser"):
        await _normalize_agent_browser_command(
            f"agent-browser {action} --allowed-domains example.com",
            url_validator=_allow_example_url,
        )


@pytest.mark.asyncio
async def test_agent_browser_rejects_unapproved_global_flags():
    with pytest.raises(PermissionDeniedError, match="agent-browser"):
        await _normalize_agent_browser_command(
            "agent-browser --json snapshot --allowed-domains example.com",
            url_validator=_allow_example_url,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        'agent-"browser" eval "document.cookie" --allowed-domains example.com',
        "/usr/local/bin/agent-browse? eval document.cookie --allowed-domains example.com",
        "agent-${BROWSER} eval document.cookie --allowed-domains example.com",
        "agent-browse{r,x} eval document.cookie --allowed-domains example.com",
        "$(printf agent-browser) eval document.cookie --allowed-domains example.com",
        "agent-browse$(printf r) eval document.cookie --allowed-domains example.com",
        "$TOOL eval document.cookie --allowed-domains example.com",
        "env -u HOME agent-browser eval document.cookie --allowed-domains example.com",
        "bash -lc 'agent-\"browser\" eval document.cookie --allowed-domains example.com'",
    ],
)
async def test_agent_browser_shell_expansion_candidates_fail_closed(command: str):
    with pytest.raises(PermissionDeniedError, match="agent-browser"):
        await _normalize_agent_browser_command(
            command, url_validator=_allow_example_url
        )


@pytest.mark.asyncio
async def test_ordinary_bash_argument_can_mention_agent_browser() -> None:
    command = "printf '%s' 'agent-browser documentation'"

    normalized = await _normalize_agent_browser_command(
        command, url_validator=_allow_example_url
    )

    assert normalized == command


def test_agent_browser_process_context_isolates_cwd_home_and_dangerous_env(
    tmp_path: Path,
) -> None:
    requested_cwd = tmp_path / "workspace"
    requested_cwd.mkdir()
    (requested_cwd / "agent-browser.json").write_text(
        '{"cdp": "http://127.0.0.1:9222"}', encoding="utf-8"
    )
    isolated_cwd = tmp_path / "browser-runtime" / "session-1" / "cwd"
    isolated_cwd.mkdir(parents=True)
    (isolated_cwd / "agent-browser.json").write_text(
        '{"proxy": "http://127.0.0.1:8080"}', encoding="utf-8"
    )
    base_env = {
        "PATH": "/usr/bin",
        "HOME": "/Users/example",
        "HTTP_PROXY": "http://127.0.0.1:8080",
        "https_proxy": "http://127.0.0.1:8080",
        "AGENT_BROWSER_CDP": "9222",
        "AGENT_BROWSER_PROFILE": "/tmp/profile",
        "AGENT_BROWSER_STATE": "/tmp/state.json",
        "AGENT_BROWSER_PROXY": "http://127.0.0.1:8080",
        "AGENT_BROWSER_INIT_SCRIPT": "/tmp/init.js",
        "AGENT_BROWSER_EXTENSION": "/tmp/ext",
        "AGENT_BROWSER_CONFIG": "/tmp/unsafe-config.json",
        "AGENT_BROWSER_EXECUTABLE_PATH": "/usr/bin/chromium",
    }

    process_cwd, process_env, cleanup_root = _agent_browser_process_context(
        command="agent-browser snapshot --allowed-domains example.com",
        requested_cwd=requested_cwd,
        session_id="session-1",
        runtime_root=tmp_path / "browser-runtime",
        base_env=base_env,
    )

    assert process_cwd != requested_cwd
    assert process_cwd.is_dir()
    assert not (process_cwd / "agent-browser.json").exists()
    assert cleanup_root is not None
    controlled_config = Path(process_env["AGENT_BROWSER_CONFIG"])
    assert controlled_config.parent == cleanup_root
    assert controlled_config.read_text(encoding="utf-8") == "{}\n"
    assert process_env["PATH"] == "/usr/bin"
    assert process_env["AGENT_BROWSER_EXECUTABLE_PATH"] == "/usr/bin/chromium"
    assert process_env["AGENT_BROWSER_NAMESPACE"] == "bioinfoflow-session-1"
    assert process_env["HOME"].startswith(str(tmp_path / "browser-runtime"))
    assert not any(key.lower().endswith("_proxy") for key in process_env)
    assert not any(
        key.startswith("AGENT_BROWSER_")
        and key
        not in {
            "AGENT_BROWSER_CONFIG",
            "AGENT_BROWSER_EXECUTABLE_PATH",
            "AGENT_BROWSER_NAMESPACE",
        }
        for key in process_env
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        "agent-browser open https://example.com --cdp 9222",
        "agent-browser open https://example.com --auto-connect",
        "agent-browser snapshot --allowed-domains example.com --profile /tmp/p",
        "agent-browser snapshot --allowed-domains example.com --restore saved",
        "agent-browser snapshot --allowed-domains example.com --state state.json",
        "agent-browser open https://example.com --proxy http://proxy.example",
        "agent-browser open https://example.com --args --no-sandbox",
        "agent-browser open https://example.com --init-script init.js",
        "agent-browser open https://example.com --extension ext",
        "agent-browser --cdp 9222 snapshot --allowed-domains example.com",
        "agent-browser eval 'document.cookie' --allowed-domains example.com",
        "agent-browser connect ws://example.com",
        "bash -lc 'agent-browser open https://example.com'",
        "agent-browser open https://example.com | cat",
    ],
)
async def test_agent_browser_rejects_bypass_and_eval_connect_surfaces(command: str):
    with pytest.raises(PermissionDeniedError, match="agent-browser"):
        await _normalize_agent_browser_command(
            command, url_validator=_allow_example_url
        )


async def _shell_context(
    db_session,
    *,
    permission_mode: str = "guarded_auto",
) -> tuple[AgentToolDispatcher, AgentToolContext, Path]:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Shell Project",
        description="Controlled execution",
        user_id="dev",
        created_by_user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    db_session.add_all([workspace, project])
    await db_session.commit()
    await db_session.refresh(project)
    workspace_root = project_home(project)
    workspace_root.mkdir(parents=True, exist_ok=True)

    core = AgentCoreService(db_session)
    session = await core.create_session(
        project_id=str(project.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Shell",
        permission_mode=permission_mode,
    )
    turn = await core.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Run a controlled command.",
    )
    return (
        AgentToolDispatcher(db_session, build_default_tool_registry()),
        AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
            project_id=str(project.id),
        ),
        workspace_root,
    )


@pytest.mark.asyncio
async def test_bash_tool_waits_for_approval_for_elevated_command(db_session):
    dispatcher, context, workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bash",
        input={
            "command": f"{sys.executable} -c \"print('should not run')\"",
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )

    assert result.status == "waiting_decision"
    assert result.permission_decision["decision"] == "ask"
    assert result.result is None


@pytest.mark.asyncio
async def test_bash_tool_auto_runs_safe_command_with_pipe_and_glob(db_session):
    dispatcher, context, workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bash",
        input={
            "command": "echo agent-core-ok | cat",
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )

    # A read-only command auto-runs even under guarded_auto, and the pipe works.
    assert result.status == "completed"
    assert result.result["exit_code"] == 0
    assert result.result["stdout"].strip() == "agent-core-ok"

    events = await AgentCoreService(db_session).list_events_for_turn(
        turn_id=context.turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    started = next(event for event in events if event.type == "action.started")
    completed = next(event for event in events if event.type == "action.completed")
    assert started.payload["name"] == "bash"
    assert started.payload["input_preview"] == "echo agent-core-ok | cat"
    assert completed.payload["name"] == "bash"
    assert completed.payload["input_preview"] == "echo agent-core-ok | cat"


@pytest.mark.asyncio
async def test_bash_tool_records_nonzero_exit_as_failed_with_command_result(db_session):
    dispatcher, context, workspace_root = await _shell_context(
        db_session, permission_mode="bypass"
    )
    command = "printf shell-out; printf shell-err >&2; exit 13"

    result = await dispatcher.dispatch(
        tool_name="bash",
        input={"command": command, "cwd": str(workspace_root)},
        context=context,
        permission_mode="bypass",
    )

    expected_result = {
        "exit_code": 13,
        "stdout": "shell-out",
        "stderr": "shell-err",
        "cwd": str(workspace_root.resolve()),
        "command": command,
    }
    assert result.status == "failed"
    assert result.result == expected_result
    assert result.error == {
        "type": "CommandExitError",
        "message": "Command exited with code 13.",
        "category": "tool_result",
        "continuable": True,
    }

    action = await AgentActionRepository(db_session).get_fresh(result.action_id)
    assert action is not None
    assert action.status == "failed"
    assert action.result == expected_result
    assert action.error == result.error

    events = await AgentCoreService(db_session).list_events_for_turn(
        turn_id=context.turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert not any(event.type == "action.completed" for event in events)
    failed = next(event for event in events if event.type == "action.failed")
    assert failed.payload == {
        "action_id": result.action_id,
        "name": "bash",
        "tool_call_id": None,
        "input_preview": command,
        "result": expected_result,
        "error": result.error,
    }


class _InvalidResultErrorTool:
    spec = AgentToolSpec(
        name="bash",
        description="Return a valid result and an invalid semantic error.",
        input_schema={"type": "object", "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        risk_level="read",
    )

    def __init__(self, hook_result=None, hook_exception: Exception | None = None):
        self.hook_result = hook_result
        self.hook_exception = hook_exception

    async def run(self, input, context):
        del input, context
        return {"ok": True}

    def result_error(self, result):
        assert result == {"ok": True}
        if self.hook_exception is not None:
            raise self.hook_exception
        return self.hook_result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hook_result", "expected_message"),
    [
        ({"message": "missing type"}, "non-empty type"),
        ({"type": "Invalid", "message": ""}, "non-empty message"),
        (
            {
                "type": "Invalid",
                "message": "bad payload",
                "continuable": True,
                "payload": ["not", "a", "mapping"],
            },
            "payload must be a dictionary",
        ),
        (
            {
                "type": "Invalid",
                "message": "bad",
                "continuable": True,
                "payload": {"value": object()},
            },
            "JSON-serializable",
        ),
    ],
)
async def test_invalid_tool_result_error_is_normalized_without_leaving_action_running(
    db_session, hook_result, expected_message
):
    _dispatcher, context, _workspace_root = await _shell_context(
        db_session, permission_mode="bypass"
    )
    registry = AgentToolRegistry()
    registry.register(_InvalidResultErrorTool(hook_result=hook_result))

    result = await AgentToolDispatcher(db_session, registry).dispatch(
        tool_name="bash",
        input={},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "failed"
    assert result.result is None
    assert result.error["type"] in {"TypeError", "ValueError"}
    assert expected_message in result.error["message"]
    action = await AgentActionRepository(db_session).get_fresh(result.action_id)
    assert action is not None
    assert action.status == "failed"
    assert action.error == result.error


@pytest.mark.asyncio
async def test_tool_result_error_exception_is_normalized_without_leaving_action_running(
    db_session,
):
    _dispatcher, context, _workspace_root = await _shell_context(
        db_session, permission_mode="bypass"
    )
    registry = AgentToolRegistry()
    registry.register(
        _InvalidResultErrorTool(hook_exception=RuntimeError("hook exploded"))
    )

    result = await AgentToolDispatcher(db_session, registry).dispatch(
        tool_name="bash",
        input={},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "failed"
    assert result.result is None
    assert result.error == {"type": "RuntimeError", "message": "hook exploded"}
    action = await AgentActionRepository(db_session).get_fresh(result.action_id)
    assert action is not None
    assert action.status == "failed"
    assert action.error == result.error


@pytest.mark.asyncio
async def test_bash_tool_cancellation_kills_descendant_processes(db_session):
    _dispatcher, context, workspace_root = await _shell_context(db_session)
    child_pid_file = workspace_root / "shell-child.pid"
    command = f"sleep 30 & echo $! > {shlex.quote(str(child_pid_file))}; wait"
    task = asyncio.create_task(
        ExecuteShellTool().run(
            {"command": command, "cwd": str(workspace_root)},
            context,
        )
    )
    for _ in range(100):
        if child_pid_file.exists():
            break
        await asyncio.sleep(0.01)
    assert child_pid_file.exists()
    child_pid = int(child_pid_file.read_text().strip())

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    for _ in range(100):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        await asyncio.sleep(0.01)

    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


@pytest.mark.asyncio
async def test_bash_tool_requires_approval_for_catastrophic_command_in_bypass(
    db_session, monkeypatch
):
    dispatcher, context, workspace_root = await _shell_context(
        db_session, permission_mode="bypass"
    )
    runs = 0

    async def record_run(self, input, context):
        del self, input, context
        nonlocal runs
        runs += 1
        return {
            "exit_code": 0,
            "stdout": "approved",
            "stderr": "",
            "cwd": str(workspace_root),
            "command": "rm -rf /",
        }

    monkeypatch.setattr(ExecuteShellTool, "run", record_run)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )

    result = await dispatcher.dispatch(
        tool_name="bash",
        input={"command": "rm -rf /", "cwd": str(workspace_root)},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "waiting_decision"
    assert result.permission_decision["decision"] == "ask"
    assert result.permission_decision["risk_level"] == "critical"
    assert result.result is None
    assert runs == 0

    await AgentCoreService(db_session).decide_action(
        action_id=result.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
        note="explicitly approve critical command",
    )
    resumed = await dispatcher.resume_action(
        action_id=result.action_id, context=context
    )

    assert resumed.status == "completed"
    assert resumed.result["stdout"] == "approved"
    assert runs == 1


@pytest.mark.asyncio
async def test_bash_tool_rejects_sandbox_disable_request(db_session):
    dispatcher, context, workspace_root = await _shell_context(
        db_session,
        permission_mode="bypass",
    )
    result = await dispatcher.dispatch(
        tool_name="bash",
        input={
            "command": "pwd",
            "cwd": str(workspace_root),
            "dangerously_disable_sandbox": True,
        },
        context=context,
        permission_mode="bypass",
        automation_mode="autonomous",
    )

    assert result.status == "failed"


@pytest.mark.asyncio
async def test_bash_tool_defaults_cwd_to_active_project(db_session):
    dispatcher, context, workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bash",
        input={"command": "pwd"},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "completed"
    assert result.result["cwd"] == str(workspace_root.resolve())


@pytest.mark.asyncio
async def test_bash_tool_rejects_cwd_outside_allowed_roots(db_session):
    dispatcher, context, _workspace_root = await _shell_context(db_session)

    result = await dispatcher.dispatch(
        tool_name="bash",
        input={"command": "echo hi", "cwd": "/"},
        context=context,
        permission_mode="bypass",
    )

    assert result.status == "failed"
    assert result.error["type"] == "PermissionDeniedError"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_template",
    [
        "printf changed > {path}",
        "sed -i s/before/after/ {path}",
        "rm {path}",
        "chmod 777 {path}",
        "bash -c 'printf changed > {path}'",
        'python -c \'from pathlib import Path; Path("{path}").write_text("changed")\'',
        "dd if=/dev/null of={path}",
        "unknown-command {path}",
        "find {path} -delete",
        "find {path} -exec rm {{}} \\;",
        "find {path} -fprint {path}.txt",
        "find {path} -fprint0 {path}.txt",
        "find {path} -fprintf {path}.txt '%p'",
        "find {path} -fls {path}.txt",
        "sed -n 'w {path}' /dev/null",
        "sed -n '1e touch {path}' /dev/null",
    ],
)
async def test_bash_rejects_static_attachment_store_mutations(
    db_session,
    tmp_path,
    monkeypatch,
    command_template,
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    _dispatcher, context, _workspace_root = await _shell_context(db_session)
    target = (
        agent_session_attachments_root(context.session_id) / "attachment" / "original"
    )
    target.parent.mkdir(parents=True)
    target.write_text("before", encoding="utf-8")

    with pytest.raises(Exception, match="attachment|protected"):
        await ExecuteShellTool().run(
            {"command": command_template.format(path=shlex.quote(str(target)))},
            context,
        )

    assert target.read_text(encoding="utf-8") == "before"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_template",
    ["cat {path} | head", "cat {path}; true", "cat {path}\ntrue"],
)
async def test_bash_rejects_attachment_commands_with_shell_control_operators(
    db_session, tmp_path, monkeypatch, command_template
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    target = agent_attachments_root() / "session" / "attachment" / "original"
    target.parent.mkdir(parents=True)
    target.write_text("before", encoding="utf-8")
    _dispatcher, context, _workspace_root = await _shell_context(db_session)

    with pytest.raises(Exception, match="attachment|protected"):
        await ExecuteShellTool().run(
            {"command": command_template.format(path=shlex.quote(str(target)))},
            context,
        )


@pytest.mark.asyncio
async def test_bash_resolves_external_symlink_aliases_before_attachment_guard(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    _dispatcher, context, workspace_root = await _shell_context(db_session)
    target = (
        agent_session_attachments_root(context.session_id) / "attachment" / "original"
    )
    target.parent.mkdir(parents=True)
    target.write_text("before", encoding="utf-8")
    alias = workspace_root / "attachment-alias"
    alias.symlink_to(target)

    with pytest.raises(Exception, match="attachment|protected"):
        await ExecuteShellTool().run(
            {"command": "unknown-command attachment-alias", "cwd": str(workspace_root)},
            context,
        )

    result = await ExecuteShellTool().run(
        {"command": "cat attachment-alias", "cwd": str(workspace_root)}, context
    )
    assert result["stdout"] == "before"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_template",
    [
        'ATTACHMENT={path} rm "$ATTACHMENT"',
        "rm $BIOINFOFLOW_HOME/state/agent_core/attachments/session/attachment/original",
        'ATTACHMENT=$BIOINFOFLOW_HOME/state/agent_core/attachments/session/attachment/original rm "$ATTACHMENT"',
    ],
)
async def test_bash_rejects_variableized_attachment_mutations(
    db_session, tmp_path, monkeypatch, command_template
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    monkeypatch.setenv("BIOINFOFLOW_HOME", str(tmp_path))
    target = agent_attachments_root() / "session" / "attachment" / "original"
    target.parent.mkdir(parents=True)
    target.write_text("before", encoding="utf-8")
    _dispatcher, context, _workspace_root = await _shell_context(db_session)

    with pytest.raises(Exception, match="attachment|protected"):
        await ExecuteShellTool().run(
            {"command": command_template.format(path=shlex.quote(str(target)))},
            context,
        )

    assert target.read_text(encoding="utf-8") == "before"


@pytest.mark.asyncio
async def test_bash_does_not_reject_unrelated_variableized_rm(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    _dispatcher, context, workspace_root = await _shell_context(db_session)
    target = workspace_root / "ordinary.txt"
    target.write_text("remove", encoding="utf-8")
    monkeypatch.setenv("OTHER", str(target))

    result = await ExecuteShellTool().run({"command": 'rm "$OTHER"'}, context)

    assert result["exit_code"] == 0
    assert not target.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_template",
    [
        "cat {path}",
        "head -n 1 {path}",
        "tail -n 1 {path}",
        "file {path}",
        "rg before {path}",
        "grep before {path}",
        "sed -n 1p {path}",
        "ls {path}",
        "find {path} -maxdepth 0",
    ],
)
async def test_bash_allows_explicit_read_only_attachment_commands(
    db_session,
    tmp_path,
    monkeypatch,
    command_template,
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    _dispatcher, context, _workspace_root = await _shell_context(db_session)
    target = (
        agent_session_attachments_root(context.session_id) / "attachment" / "original"
    )
    target.parent.mkdir(parents=True)
    target.write_text("before", encoding="utf-8")

    result = await ExecuteShellTool().run(
        {"command": command_template.format(path=shlex.quote(str(target)))},
        context,
    )

    assert result["exit_code"] == 0
    assert target.read_text(encoding="utf-8") == "before"


@pytest.mark.asyncio
async def test_bash_sandbox_receives_only_current_session_attachment_root(
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    captured = {}

    def capture_build(self, **kwargs):
        captured.update(kwargs)
        return type("SandboxResult", (), {"argv": ["bash", "-lc", "true"]})()

    monkeypatch.setattr(
        "app.services.agent_core.tools.execution.shell.SandboxRunner.build",
        capture_build,
    )
    _dispatcher, context, _workspace_root = await _shell_context(db_session)
    current_root = agent_session_attachments_root(context.session_id)
    current_root.mkdir(parents=True)

    await ExecuteShellTool().run({"command": "true"}, context)

    assert any(
        current_root.is_relative_to(root) for root in captured["protected_roots"]
    )
    assert captured["protected_read_roots"] == [current_root]


@pytest.mark.asyncio
async def test_bash_tool_resumes_after_approval_without_registering_output_artifact(
    db_session, monkeypatch
):
    dispatcher, context, workspace_root = await _shell_context(db_session)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )

    pending = await dispatcher.dispatch(
        tool_name="bash",
        input={
            "command": f"{sys.executable} -c \"print('before-approval')\"",
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )
    assert pending.status == "waiting_decision"

    decided = await AgentCoreService(db_session).decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
        note="approved for test",
    )
    assert decided.status == "requested"

    resumed = await dispatcher.resume_action(
        action_id=pending.action_id, context=context
    )
    assert resumed.status == "completed"
    assert resumed.result["exit_code"] == 0
    assert resumed.result["stdout"].strip() == "before-approval"

    artifacts = await AgentCoreService(db_session).list_artifacts_for_turn(
        turn_id=context.turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert artifacts == []

    events = await AgentCoreService(db_session).list_events_for_turn(
        turn_id=context.turn_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    event_types = [event.type for event in events]
    assert "action.decision_recorded" in event_types
    assert "action.started" in event_types
    assert "artifact.created" not in event_types
    assert "action.completed" in event_types


@pytest.mark.asyncio
async def test_bash_tool_uses_modified_input_when_approval_changes_command(
    db_session, monkeypatch
):
    dispatcher, context, workspace_root = await _shell_context(db_session)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )

    pending = await dispatcher.dispatch(
        tool_name="bash",
        input={
            "command": f"{sys.executable} -c \"print('old-command')\"",
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )

    decided = await AgentCoreService(db_session).decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="modify",
        note="use safer command",
        modified_input={
            "command": f"{sys.executable} -c \"print('new-command')\"",
            "cwd": str(workspace_root),
        },
    )
    assert decided.status == "requested"

    resumed = await dispatcher.resume_action(
        action_id=pending.action_id, context=context
    )
    assert resumed.status == "completed"
    assert resumed.result["stdout"].strip() == "new-command"
    action = await AgentActionRepository(db_session).get(pending.action_id)
    assert "new-command" in action.input["command"]


@pytest.mark.asyncio
async def test_bash_resume_reassesses_modified_hardline_and_requests_new_approval(
    db_session,
    monkeypatch,
):
    dispatcher, context, workspace_root = await _shell_context(db_session)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None
    )

    pending = await dispatcher.dispatch(
        tool_name="bash",
        input={
            "command": f"{sys.executable} -c \"print('approval candidate')\"",
            "cwd": str(workspace_root),
        },
        context=context,
        permission_mode="guarded_auto",
    )
    await AgentCoreService(db_session).decide_action(
        action_id=pending.action_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="modify",
        note="replace with a different command",
        modified_input={"command": "sudo rm -rf -- /./", "cwd": str(workspace_root)},
    )

    resumed = await dispatcher.resume_action(
        action_id=pending.action_id, context=context
    )
    action = await AgentActionRepository(db_session).get_fresh(pending.action_id)

    assert resumed.status == "waiting_decision"
    assert resumed.permission_decision["decision"] == "ask"
    assert action.risk_level == "critical"
    assert action.permission_context_snapshot["command_risk"]["hard_blocked"] is False
    assert action.permission_context_snapshot["command_risk"]["level"] == "critical"

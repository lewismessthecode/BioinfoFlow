"""bif agent — AgentCore sessions, turns, events, actions, and artifacts."""

from __future__ import annotations

import json
import sys
from typing import Any

import click
import typer

from app.cli.api_helpers import api_delete, api_get, api_post
from app.cli.context import CliContext
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx
from app.cli.render import Renderer
from app.cli.types import ApiError, ApiResponse

agent_app = typer.Typer(
    name="agent",
    help="AgentCore session, turn, action, event, and artifact commands.",
    no_args_is_help=True,
)
session_app = typer.Typer(
    name="session",
    help="Manage AgentCore sessions.",
    no_args_is_help=True,
)
turn_app = typer.Typer(
    name="turn",
    help="Inspect and cancel AgentCore turns.",
    no_args_is_help=True,
)
action_app = typer.Typer(
    name="action",
    help="Approve, reject, or modify AgentCore actions.",
    no_args_is_help=True,
)
artifacts_app = typer.Typer(
    name="artifacts",
    help="List, show, and open AgentCore artifacts.",
    no_args_is_help=True,
)


# -- Session commands --------------------------------------------------------


@session_app.command("create")
@handle_errors
def session_create(
    ctx: typer.Context,
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    title: str | None = typer.Option(None, "--title", help="Session title"),
    role_profile: str = typer.Option(
        "bioinformatician", "--role-profile", help="Agent role profile"
    ),
    permission_mode: str = typer.Option(
        "guarded_auto", "--permission-mode", help="Permission mode"
    ),
    automation_mode: str = typer.Option(
        "assisted", "--automation-mode", help="Automation mode"
    ),
    model_profile_id: str | None = typer.Option(
        None, "--model-profile", help="Default model profile ID"
    ),
) -> None:
    """Create an AgentCore session."""
    cli_ctx, r = unpack_ctx(ctx)
    payload = _compact(
        {
            "project_id": project_id or cli_ctx.project_id,
            "title": title,
            "role_profile": role_profile,
            "permission_mode": permission_mode,
            "automation_mode": automation_mode,
            "default_model_profile_id": model_profile_id,
        }
    )
    resp = cli_ctx.run(api_post(cli_ctx, "/agent/sessions", payload))
    _render_session(r, resp)


@session_app.command("list")
@handle_errors
def session_list(
    ctx: typer.Context,
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
) -> None:
    """List AgentCore sessions."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = project_id or cli_ctx.project_id
    params = {"project_id": pid} if pid else {}
    resp = cli_ctx.run(api_get(cli_ctx, "/agent/sessions", params))
    rows = resp.data if isinstance(resp.data, list) else []
    cols = [
        {"key": "id", "header": "ID"},
        {"key": "title", "header": "Title"},
        {"key": "status", "header": "Status"},
        {"key": "permission_mode", "header": "Permission"},
        {"key": "automation_mode", "header": "Automation"},
        {"key": "updated_at", "header": "Updated"},
    ]
    r.table(cols, rows, resp)


@session_app.command("show")
@handle_errors
def session_show(
    ctx: typer.Context,
    session_id: str = typer.Argument(help="AgentCore session ID"),
) -> None:
    """Show an AgentCore session."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/agent/sessions/{session_id}"))
    _render_session(r, resp)


@session_app.command("state")
@handle_errors
def session_state(
    ctx: typer.Context,
    session_id: str = typer.Argument(help="AgentCore session ID"),
) -> None:
    """Show the durable AgentCore session state projection."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/agent/sessions/{session_id}/state"))
    r.emit_json(resp) if r.is_json else _render_state(r, resp)


@session_app.command("delete")
@handle_errors
def session_delete(
    ctx: typer.Context,
    session_id: str = typer.Argument(help="AgentCore session ID"),
) -> None:
    """Delete an AgentCore session."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_delete(cli_ctx, f"/agent/sessions/{session_id}"))
    r.success(f"Agent session {session_id} deleted.", raw=resp)


# -- Turn/message commands ---------------------------------------------------


@agent_app.command("send")
@handle_errors
def agent_send(
    ctx: typer.Context,
    message: str = typer.Argument(help="Message to send"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    session_id: str | None = typer.Option(
        None, "--session", help="Existing AgentCore session ID"
    ),
    model_profile_id: str | None = typer.Option(
        None, "--model-profile", help="Model profile for this turn"
    ),
) -> None:
    """Send a single message as a new AgentCore turn."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = project_id or cli_ctx.project_id
    cli_ctx.run(_send(cli_ctx, r, pid, message, session_id, model_profile_id))


@agent_app.command("chat")
@handle_errors
def agent_chat(
    ctx: typer.Context,
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    session_id: str | None = typer.Option(
        None, "--session", help="Resume AgentCore session"
    ),
    model_profile_id: str | None = typer.Option(
        None, "--model-profile", help="Model profile for each turn"
    ),
) -> None:
    """Interactive AgentCore chat REPL."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = project_id or cli_ctx.project_id
    cli_ctx.run(_chat_loop(cli_ctx, r, pid, session_id, model_profile_id))


@agent_app.command("events")
@handle_errors
def agent_events(
    ctx: typer.Context,
    turn_id: str = typer.Argument(help="AgentCore turn ID"),
    after_seq: int = typer.Option(0, "--after-seq", min=0, help="Replay after seq"),
) -> None:
    """List persisted AgentCore events for a turn."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(
        api_get(cli_ctx, f"/agent/turns/{turn_id}/events", {"after_seq": after_seq})
    )
    rows = resp.data if isinstance(resp.data, list) else []
    cols = [
        {"key": "seq", "header": "Seq"},
        {"key": "type", "header": "Type"},
        {"key": "visibility", "header": "Visibility"},
        {"key": "created_at", "header": "Created"},
    ]
    r.table(cols, rows, resp)


@agent_app.command("stream")
@handle_errors
def agent_stream(
    ctx: typer.Context,
    session_id: str = typer.Argument(help="AgentCore session ID"),
    after_seq: int = typer.Option(0, "--after-seq", min=0, help="Replay after seq"),
) -> None:
    """Stream AgentCore session events as SSE projections or NDJSON."""
    cli_ctx, r = unpack_ctx(ctx)
    cli_ctx.run(_stream_events(cli_ctx, r, session_id, after_seq))


@turn_app.command("list")
@handle_errors
def turn_list(
    ctx: typer.Context,
    session_id: str = typer.Argument(help="AgentCore session ID"),
) -> None:
    """List turns for an AgentCore session."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/agent/sessions/{session_id}/turns"))
    rows = resp.data if isinstance(resp.data, list) else []
    cols = [
        {"key": "id", "header": "ID"},
        {"key": "input_text", "header": "Input"},
        {"key": "status", "header": "Status"},
        {"key": "created_at", "header": "Created"},
    ]
    r.table(cols, rows, resp)


@turn_app.command("show")
@handle_errors
def turn_show(
    ctx: typer.Context,
    turn_id: str = typer.Argument(help="AgentCore turn ID"),
) -> None:
    """Show an AgentCore turn."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/agent/turns/{turn_id}"))
    _render_turn(r, resp)


@turn_app.command("cancel")
@handle_errors
def turn_cancel(
    ctx: typer.Context,
    turn_id: str = typer.Argument(help="AgentCore turn ID"),
) -> None:
    """Cancel an AgentCore turn."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_post(cli_ctx, f"/agent/turns/{turn_id}/cancel"))
    r.success(f"Agent turn {turn_id} cancelled.", raw=resp)


@turn_app.command("interrupt")
@handle_errors
def turn_interrupt(
    ctx: typer.Context,
    turn_id: str = typer.Argument(help="AgentCore turn ID"),
) -> None:
    """Interrupt an AgentCore turn through the harness interrupt path."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_post(cli_ctx, f"/agent/turns/{turn_id}/interrupt"))
    r.success(f"Agent turn {turn_id} interrupted.", raw=resp)


@agent_app.command("cancel")
@handle_errors
def agent_cancel(
    ctx: typer.Context,
    turn_id: str = typer.Argument(help="AgentCore turn ID"),
) -> None:
    """Cancel an AgentCore turn."""
    turn_cancel(ctx, turn_id)


@agent_app.command("interrupt")
@handle_errors
def agent_interrupt(
    ctx: typer.Context,
    turn_id: str = typer.Argument(help="AgentCore turn ID"),
) -> None:
    """Interrupt an AgentCore turn."""
    turn_interrupt(ctx, turn_id)


@agent_app.command("toolsets")
@handle_errors
def agent_toolsets(ctx: typer.Context) -> None:
    """List AgentCore toolsets exposed by the backend."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, "/agent/toolsets"))
    r.emit_json(resp) if r.is_json else _render_toolsets(r, resp)


# -- Action commands ---------------------------------------------------------


@action_app.command("approve")
@handle_errors
def action_approve(
    ctx: typer.Context,
    action_id: str = typer.Argument(help="AgentCore action ID"),
    note: str | None = typer.Option(None, "--note", help="Decision note"),
) -> None:
    """Approve a waiting AgentCore action."""
    _decide_action(ctx, action_id, "approve", note=note)


@action_app.command("reject")
@handle_errors
def action_reject(
    ctx: typer.Context,
    action_id: str = typer.Argument(help="AgentCore action ID"),
    note: str | None = typer.Option(None, "--note", help="Decision note"),
) -> None:
    """Reject a waiting AgentCore action."""
    _decide_action(ctx, action_id, "reject", note=note)


@action_app.command("modify")
@handle_errors
def action_modify(
    ctx: typer.Context,
    action_id: str = typer.Argument(help="AgentCore action ID"),
    input_json: str = typer.Option(
        ..., "--input-json", help="Modified action input as JSON object"
    ),
    note: str | None = typer.Option(None, "--note", help="Decision note"),
) -> None:
    """Approve a waiting AgentCore action with modified input."""
    try:
        modified_input = json.loads(input_json)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("--input-json must be valid JSON") from exc
    if not isinstance(modified_input, dict):
        raise typer.BadParameter("--input-json must decode to a JSON object")
    _decide_action(ctx, action_id, "modify", note=note, modified_input=modified_input)


# -- Artifact commands -------------------------------------------------------


@artifacts_app.command("list")
@handle_errors
def artifacts_list(
    ctx: typer.Context,
    target_id: str = typer.Argument(help="Turn ID by default, or session ID"),
    scope: str = typer.Option(
        "turn", "--scope", help="Artifact scope: turn or session"
    ),
) -> None:
    """List AgentCore artifacts for a turn or session."""
    if scope not in {"turn", "session"}:
        raise typer.BadParameter("--scope must be 'turn' or 'session'")
    cli_ctx, r = unpack_ctx(ctx)
    endpoint = (
        f"/agent/sessions/{target_id}/artifacts"
        if scope == "session"
        else f"/agent/turns/{target_id}/artifacts"
    )
    resp = cli_ctx.run(api_get(cli_ctx, endpoint))
    rows = resp.data if isinstance(resp.data, list) else []
    cols = [
        {"key": "id", "header": "ID"},
        {"key": "type", "header": "Type"},
        {"key": "title", "header": "Title"},
        {"key": "summary", "header": "Summary"},
        {"key": "created_at", "header": "Created"},
    ]
    r.table(cols, rows, resp)


@artifacts_app.command("show")
@handle_errors
def artifacts_show(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="AgentCore artifact ID"),
) -> None:
    """Show an AgentCore artifact."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/agent/artifacts/{artifact_id}"))
    _render_artifact(r, resp)


@artifacts_app.command("open")
@handle_errors
def artifacts_open(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="AgentCore artifact ID"),
) -> None:
    """Open an AgentCore artifact file path with the operating system."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/agent/artifacts/{artifact_id}"))
    data = resp.data if isinstance(resp.data, dict) else {}
    file_path = data.get("file_path")
    if not file_path:
        raise ApiError(
            code="ARTIFACT_HAS_NO_FILE",
            message=f"Artifact {artifact_id} does not have a file_path.",
            status_code=0,
        )
    click.launch(str(file_path))
    r.success(f"Opened artifact {artifact_id}.", raw=resp)


# -- Async helpers -----------------------------------------------------------


async def _ensure_session(
    cli_ctx: CliContext,
    project_id: str | None,
    session_id: str | None,
) -> tuple[str, bool]:
    """Return an AgentCore session ID, creating a session when needed."""
    if session_id:
        return session_id, False
    resp = await cli_ctx.client.post(
        "/agent/sessions",
        _compact({"project_id": project_id or cli_ctx.project_id}),
    )
    sid = _response_id(resp, "session")
    return sid, True


async def _create_turn(
    cli_ctx: CliContext,
    session_id: str,
    message: str,
    model_profile_id: str | None,
) -> ApiResponse:
    payload = _compact(
        {
            "input_text": message,
            "model_profile_id": model_profile_id,
        }
    )
    return await cli_ctx.client.post(f"/agent/sessions/{session_id}/turns", payload)


async def _send(
    cli_ctx: CliContext,
    r: Renderer,
    project_id: str | None,
    message: str,
    session_id: str | None,
    model_profile_id: str | None,
) -> None:
    sid, created = await _ensure_session(cli_ctx, project_id, session_id)
    if created and not r.is_json and not cli_ctx.quiet:
        cli_ctx.console.print(f"[dim]Session: {sid}[/dim]")
    resp = await _create_turn(cli_ctx, sid, message, model_profile_id)
    if r.is_json:
        r.emit_json(resp)
        return
    data = resp.data if isinstance(resp.data, dict) else {}
    turn_id = data.get("id")
    final_text = data.get("final_text")
    if turn_id and not cli_ctx.quiet:
        cli_ctx.console.print(f"[dim]Turn: {turn_id}[/dim]")
    if final_text:
        cli_ctx.console.print(str(final_text))
    if created and not cli_ctx.quiet:
        cli_ctx.console.print(f"\n[dim]Continue with: bif agent send --session {sid} ...[/dim]")


async def _chat_loop(
    cli_ctx: CliContext,
    r: Renderer,
    project_id: str | None,
    session_id: str | None,
    model_profile_id: str | None,
) -> None:
    """Interactive AgentCore REPL."""
    sid, _created = await _ensure_session(cli_ctx, project_id, session_id)
    if not r.is_json:
        cli_ctx.console.print(f"[dim]Session: {sid}[/dim]")

    try:
        while True:
            user_input = _read_input(r)
            if user_input is None:
                break
            if not user_input:
                continue
            if user_input in ("/exit", "/quit"):
                break

            resp = await _create_turn(cli_ctx, sid, user_input, model_profile_id)
            if r.is_json:
                r.emit_json(resp)
                continue
            data = resp.data if isinstance(resp.data, dict) else {}
            final_text = data.get("final_text")
            if final_text:
                cli_ctx.console.print(str(final_text))
                cli_ctx.console.print()
    except KeyboardInterrupt:
        if not r.is_json:
            cli_ctx.console.print("\n[dim]Exiting chat.[/dim]")


async def _stream_events(
    cli_ctx: CliContext,
    r: Renderer,
    session_id: str,
    after_seq: int,
) -> None:
    async for event in cli_ctx.client.stream_sse(
        f"/agent/sessions/{session_id}/stream",
        {"after_seq": after_seq},
    ):
        r.stream_event(event)


# -- Shared render/utility helpers ------------------------------------------


def _decide_action(
    ctx: typer.Context,
    action_id: str,
    decision: str,
    *,
    note: str | None = None,
    modified_input: dict[str, Any] | None = None,
) -> None:
    cli_ctx, r = unpack_ctx(ctx)
    payload = _compact(
        {
            "decision": decision,
            "note": note,
            "modified_input": modified_input,
        }
    )
    resp = cli_ctx.run(
        api_post(cli_ctx, f"/agent/actions/{action_id}/decision", payload)
    )
    verb = {
        "approve": "approved",
        "reject": "rejected",
        "modify": "modified",
    }[decision]
    r.success(f"Agent action {action_id} {verb}.", raw=resp)


def _render_session(r: Renderer, resp: ApiResponse) -> None:
    data = resp.data if isinstance(resp.data, dict) else {}
    r.detail(
        {
            "ID": data.get("id", ""),
            "Title": data.get("title", ""),
            "Project": data.get("project_id", ""),
            "Status": data.get("status", ""),
            "Role": data.get("role_profile", ""),
            "Permission": data.get("permission_mode", ""),
            "Automation": data.get("automation_mode", ""),
            "Updated": data.get("updated_at", ""),
        },
        title="Agent Session",
        raw=resp,
    )


def _render_turn(r: Renderer, resp: ApiResponse) -> None:
    data = resp.data if isinstance(resp.data, dict) else {}
    r.detail(
        {
            "ID": data.get("id", ""),
            "Session": data.get("session_id", ""),
            "Status": data.get("status", ""),
            "Input": data.get("input_text", ""),
            "Final": data.get("final_text", ""),
            "Created": data.get("created_at", ""),
        },
        title="Agent Turn",
        raw=resp,
    )


def _render_artifact(r: Renderer, resp: ApiResponse) -> None:
    data = resp.data if isinstance(resp.data, dict) else {}
    payload = data.get("payload")
    r.detail(
        {
            "ID": data.get("id", ""),
            "Type": data.get("type", ""),
            "Title": data.get("title", ""),
            "Summary": data.get("summary", ""),
            "File": data.get("file_path", ""),
            "Resource": json.dumps(data.get("resource_ref"), default=str)
            if data.get("resource_ref") is not None
            else "",
            "Payload": json.dumps(payload, default=str) if payload is not None else "",
        },
        title="Agent Artifact",
        raw=resp,
    )


def _render_state(r: Renderer, resp: ApiResponse) -> None:
    data = resp.data if isinstance(resp.data, dict) else {}
    session = data.get("session") if isinstance(data.get("session"), dict) else {}
    turns = data.get("turns") if isinstance(data.get("turns"), list) else []
    events = data.get("events") if isinstance(data.get("events"), list) else []
    r.detail(
        {
            "Session": session.get("id", ""),
            "Project": session.get("project_id", ""),
            "Runtime": session.get("runtime_mode", ""),
            "Turns": str(len(turns)),
            "Events": str(len(events)),
            "Last seq": str(events[-1].get("seq", 0) if events else 0),
        },
        title="Agent State",
        raw=resp,
    )


def _render_toolsets(r: Renderer, resp: ApiResponse) -> None:
    data = resp.data if isinstance(resp.data, dict) else {}
    rows = data.get("toolsets") if isinstance(data.get("toolsets"), list) else []
    normalized = [
        {"name": row.get("name"), "tools": ", ".join(row.get("tools") or [])}
        for row in rows
        if isinstance(row, dict)
    ]
    r.table(
        [{"key": "name", "header": "Toolset"}, {"key": "tools", "header": "Tools"}],
        normalized,
        resp,
    )


def _response_id(resp: ApiResponse, resource: str) -> str:
    data = resp.data if isinstance(resp.data, dict) else {}
    rid = data.get("id")
    if not rid:
        raise ApiError(
            code="INVALID_RESPONSE",
            message=f"Backend did not return an AgentCore {resource} ID.",
            status_code=0,
        )
    return str(rid)


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _read_input(r: Renderer) -> str | None:
    """Read a line of user input; return None on EOF."""
    if r.is_json:
        line = sys.stdin.readline()
        return line.strip() if line else None
    try:
        return input("bif> ")
    except EOFError:
        return None


agent_app.add_typer(session_app, name="session")
agent_app.add_typer(turn_app, name="turn")
agent_app.add_typer(action_app, name="action")
agent_app.add_typer(artifacts_app, name="artifacts")

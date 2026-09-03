"""bif agent — sessions, commands, snapshots, live events, and artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import typer

from app.cli.api_helpers import api_delete, api_download, api_get, api_post
from app.cli.context import CliContext
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx
from app.cli.render import Renderer
from app.cli.types import ApiResponse


agent_app = typer.Typer(
    name="agent",
    help="Use the complete BioinfoFlow Agent Harness.",
    no_args_is_help=True,
)
session_app = typer.Typer(
    name="session",
    help="Create and manage Agent Harness sessions.",
    no_args_is_help=True,
)
artifact_app = typer.Typer(
    name="artifact",
    help="List, inspect, and download Agent Harness artifacts.",
    no_args_is_help=True,
)


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _session_create_payload(
    cli: CliContext,
    *,
    project_id: str | None,
    title: str | None,
    permission_mode: str,
    workspace_access: str = "read_write",
    model_id: str | None = None,
    profile_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    return _compact(
        {
            "project_id": project_id or cli.project_id,
            "title": title,
            "permission_mode": permission_mode,
            "workspace_access": workspace_access,
            "model_id": model_id,
            "profile_id": profile_id,
            "provider": provider,
            "model": model,
        }
    )


def _snapshot_session_id(data: Any) -> str:
    if not isinstance(data, dict):
        raise RuntimeError("Agent session response did not contain a snapshot")
    session = data.get("session")
    if not isinstance(session, dict) or not session.get("id"):
        raise RuntimeError("Agent session snapshot did not contain a session ID")
    return str(session["id"])


@session_app.command("create")
@handle_errors
def session_create(
    ctx: typer.Context,
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    title: str | None = typer.Option(None, "--title", help="Session title"),
    permission_mode: str = typer.Option(
        "ask_dangerous", "--permission-mode", help="Session permission mode"
    ),
    workspace_access: str = typer.Option(
        "read_write", "--workspace-access", help="Session workspace access"
    ),
    model_id: str | None = typer.Option(None, "--model-id", help="Model record ID"),
    profile_id: str | None = typer.Option(
        None, "--profile-id", help="Model profile ID"
    ),
    provider: str | None = typer.Option(None, "--provider", help="Model provider"),
    model: str | None = typer.Option(None, "--model", help="Provider model name"),
) -> None:
    """Create a durable Agent Harness session."""
    cli, renderer = unpack_ctx(ctx)
    response = cli.run(
        api_post(
            cli,
            "/agent/sessions",
            _session_create_payload(
                cli,
                project_id=project_id,
                title=title,
                permission_mode=permission_mode,
                workspace_access=workspace_access,
                model_id=model_id,
                profile_id=profile_id,
                provider=provider,
                model=model,
            ),
        )
    )
    session_id = _snapshot_session_id(response.data)
    renderer.emit_json(response) if renderer.is_json else renderer.success(
        f"Agent session {session_id} created.", raw=response
    )


@session_app.command("list")
@handle_errors
def session_list(ctx: typer.Context) -> None:
    """List Agent Harness sessions."""
    cli, renderer = unpack_ctx(ctx)
    response = cli.run(api_get(cli, "/agent/sessions"))
    renderer.table(
        [
            {"key": "id", "header": "ID"},
            {"key": "title", "header": "Title"},
            {"key": "status", "header": "Status"},
            {"key": "permission_mode", "header": "Permission"},
            {"key": "updated_at", "header": "Updated"},
        ],
        response.data if isinstance(response.data, list) else [],
        response,
    )


@session_app.command("show")
@handle_errors
def session_show(ctx: typer.Context, session_id: str) -> None:
    """Show the authoritative snapshot for a session."""
    cli, renderer = unpack_ctx(ctx)
    renderer.emit_json(cli.run(api_get(cli, f"/agent/sessions/{session_id}/snapshot")))


@session_app.command("delete")
@handle_errors
def session_delete(ctx: typer.Context, session_id: str) -> None:
    """Delete a session and cancel any active run."""
    cli, renderer = unpack_ctx(ctx)
    response = cli.run(api_delete(cli, f"/agent/sessions/{session_id}"))
    renderer.success(f"Agent session {session_id} deleted.", raw=response)


@agent_app.command("send")
@handle_errors
def send(
    ctx: typer.Context,
    message: str,
    session_id: str | None = typer.Option(
        None, "--session", help="Existing session ID; omit to create one"
    ),
    attachment_ids: list[str] | None = typer.Option(
        None, "--attachment", help="Attachment ID; repeat for multiple attachments"
    ),
    project_id: str | None = typer.Option(
        None, "--project", help="Project for an automatically created session"
    ),
    title: str | None = typer.Option(
        None, "--title", help="Title for an automatically created session"
    ),
    permission_mode: str = typer.Option(
        "ask_dangerous",
        "--permission-mode",
        help="Permission mode for an automatically created session",
    ),
    workspace_access: str = typer.Option(
        "read_write",
        "--workspace-access",
        help="Workspace access for an automatically created session",
    ),
) -> None:
    """Send a message, creating a session automatically when needed."""
    cli, renderer = unpack_ctx(ctx)
    created = False
    if session_id is None:
        created_response = cli.run(
            api_post(
                cli,
                "/agent/sessions",
                _session_create_payload(
                    cli,
                    project_id=project_id,
                    title=title,
                    permission_mode=permission_mode,
                    workspace_access=workspace_access,
                ),
            )
        )
        session_id = _snapshot_session_id(created_response.data)
        created = True

    command: dict[str, Any] = {
        "type": "message",
        "parts": [
            {"type": "text", "text": message},
            *(
                {"type": "attachment_ref", "attachment_id": attachment_id}
                for attachment_id in attachment_ids or []
            ),
        ],
    }
    response = _dispatch(cli, session_id, command)

    if renderer.is_json:
        renderer.emit_json(response)
        return
    if created:
        renderer.success(f"Agent session {session_id} created.")
    renderer.success("Agent message accepted.", raw=response)


@agent_app.command("follow-up")
@handle_errors
def follow_up(
    ctx: typer.Context,
    session_id: str,
    message: str,
    attachment_ids: list[str] | None = typer.Option(
        None, "--attachment", help="Attachment ID; repeat for multiple attachments"
    ),
) -> None:
    """Queue a message to start after the active run ends."""
    _dispatch_command(
        ctx,
        session_id,
        {
            "type": "follow_up",
            "parts": [
                {"type": "text", "text": message},
                *(
                    {"type": "attachment_ref", "attachment_id": attachment_id}
                    for attachment_id in attachment_ids or []
                ),
            ],
        },
    )


@agent_app.command("steer")
@handle_errors
def steer(ctx: typer.Context, session_id: str, message: str) -> None:
    """Inject guidance at the active run's next safe point."""
    _dispatch_command(
        ctx,
        session_id,
        {"type": "steer", "parts": [{"type": "text", "text": message}]},
    )


@agent_app.command("respond")
@handle_errors
def respond(
    ctx: typer.Context,
    session_id: str,
    interaction_id: str,
    response_json: str = typer.Option(..., "--response-json"),
) -> None:
    """Answer a pending question, confirmation, or recovery interaction."""
    try:
        response = json.loads(response_json)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("--response-json must be valid JSON") from exc
    if not isinstance(response, dict):
        raise typer.BadParameter("--response-json must be a JSON object")
    _dispatch_command(
        ctx,
        session_id,
        {"type": "respond", "interaction_id": interaction_id, "response": response},
    )


@agent_app.command("cancel")
@handle_errors
def cancel(
    ctx: typer.Context,
    session_id: str,
    reason: str | None = typer.Option(None, "--reason"),
) -> None:
    """Cancel the active run."""
    _dispatch_command(ctx, session_id, {"type": "cancel", "reason": reason})


@agent_app.command("snapshot")
@handle_errors
def snapshot(ctx: typer.Context, session_id: str) -> None:
    """Read the authoritative Session, Run, and history snapshot."""
    cli, renderer = unpack_ctx(ctx)
    renderer.emit_json(cli.run(api_get(cli, f"/agent/sessions/{session_id}/snapshot")))


@agent_app.command("events")
@handle_errors
def events(ctx: typer.Context, session_id: str) -> None:
    """Stream the session snapshot and live Harness events over SSE."""
    cli, renderer = unpack_ctx(ctx)
    cli.run(_stream_events(cli, renderer, session_id))


async def _stream_events(cli: CliContext, renderer: Renderer, session_id: str) -> None:
    async for event in cli.client.stream_sse(f"/agent/sessions/{session_id}/events"):
        renderer.stream_event(event)


@artifact_app.command("list")
@handle_errors
def artifact_list(ctx: typer.Context, session_id: str) -> None:
    """List artifacts created by all runs in a session."""
    cli, renderer = unpack_ctx(ctx)
    response = cli.run(api_get(cli, f"/agent/sessions/{session_id}/artifacts"))
    renderer.table(
        [
            {"key": "id", "header": "ID"},
            {"key": "type", "header": "Type"},
            {"key": "title", "header": "Title"},
            {"key": "run_id", "header": "Run"},
            {"key": "created_at", "header": "Created"},
        ],
        response.data if isinstance(response.data, list) else [],
        response,
    )


@artifact_app.command("show")
@handle_errors
def artifact_show(ctx: typer.Context, artifact_id: str) -> None:
    """Show artifact metadata and structured payload."""
    cli, renderer = unpack_ctx(ctx)
    renderer.emit_json(cli.run(api_get(cli, f"/agent/artifacts/{artifact_id}")))


@artifact_app.command("download")
@handle_errors
def artifact_download(
    ctx: typer.Context,
    artifact_id: str,
    output: Path = typer.Option(..., "--output", "-o", help="Destination path"),
) -> None:
    """Download an artifact file to a local path."""
    cli, renderer = unpack_ctx(ctx)
    path = cli.run(
        api_download(cli, f"/agent/artifacts/{artifact_id}/download", output)
    )
    if renderer.is_json:
        renderer.emit_data({"artifact_id": artifact_id, "path": str(path)})
    else:
        renderer.success(f"Artifact {artifact_id} downloaded to {path}.")


def _dispatch(cli: CliContext, session_id: str, command: dict[str, Any]) -> ApiResponse:
    payload = {**command, "command_id": str(uuid4())}
    return cli.run(api_post(cli, f"/agent/sessions/{session_id}/commands", payload))


def _dispatch_command(
    ctx: typer.Context, session_id: str, command: dict[str, Any]
) -> None:
    cli, renderer = unpack_ctx(ctx)
    response = _dispatch(cli, session_id, command)
    renderer.emit_json(response) if renderer.is_json else renderer.success(
        f"Agent command {command['type']} accepted.", raw=response
    )


agent_app.add_typer(session_app, name="session")
agent_app.add_typer(artifact_app, name="artifact")


__all__ = ["agent_app"]

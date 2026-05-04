"""bif agent — send messages, interactive chat, history, and trace."""

from __future__ import annotations

import json
import sys

import typer

from app.cli.api_helpers import api_get, api_post
from app.cli.types import ApiError
from app.cli.constants import TERMINAL_AGENT_EVENTS
from app.cli.context import CliContext
from app.cli.errors import handle_errors
from app.cli.helpers import require_project, unpack_ctx
from app.cli.render import Renderer

agent_app = typer.Typer(
    name="agent",
    help="Agent interaction and conversation management.",
    no_args_is_help=True,
)


@agent_app.command("send")
@handle_errors
def agent_send(
    ctx: typer.Context,
    message: str = typer.Argument(help="Message to send"),
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    conversation_id: str | None = typer.Option(
        None, "--conversation", help="Existing conversation ID"
    ),
) -> None:
    """Send a single message and stream the response (non-interactive)."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = require_project(cli_ctx, project_id)
    cli_ctx.run(_send(cli_ctx, r, pid, message, conversation_id))


@agent_app.command("chat")
@handle_errors
def agent_chat(
    ctx: typer.Context,
    project_id: str | None = typer.Option(None, "--project", help="Project ID"),
    conversation_id: str | None = typer.Option(
        None, "--conversation", help="Resume conversation"
    ),
) -> None:
    """Interactive chat REPL with the agent."""
    cli_ctx, r = unpack_ctx(ctx)
    pid = require_project(cli_ctx, project_id)
    cli_ctx.run(_chat_loop(cli_ctx, r, pid, conversation_id))


@agent_app.command("history")
@handle_errors
def agent_history(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(help="Conversation ID"),
) -> None:
    """Show conversation message history."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(api_get(cli_ctx, f"/agent/conversations/{conversation_id}"))
    data = resp.data or {}
    if r.is_json:
        r.emit_json(resp)
    else:
        messages = data.get("messages", [])
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            style = "bold cyan" if role == "assistant" else "bold green"
            cli_ctx.console.print(f"[{style}]{role}:[/{style}] {content}")


@agent_app.command("status")
@handle_errors
def agent_status(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(help="Conversation ID"),
) -> None:
    """Check if agent is currently running."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(
        api_get(cli_ctx, f"/agent/conversations/{conversation_id}/status")
    )
    data = resp.data or {}
    r.detail(
        {
            "Conversation": conversation_id,
            "Running": str(data.get("running", False)),
        },
        title="Agent Status",
        raw=resp,
    )


@agent_app.command("cancel")
@handle_errors
def agent_cancel(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(help="Conversation ID"),
) -> None:
    """Cancel a running agent conversation."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(
        api_post(cli_ctx, f"/agent/conversations/{conversation_id}/cancel")
    )
    r.success(f"Agent conversation {conversation_id} cancelled.", raw=resp)


@agent_app.command("trace")
@handle_errors
def agent_trace(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(help="Conversation ID"),
) -> None:
    """Show agent execution trace."""
    cli_ctx, r = unpack_ctx(ctx)
    resp = cli_ctx.run(
        api_get(cli_ctx, f"/agent/conversations/{conversation_id}/trace")
    )
    data = resp.data
    if r.is_json:
        r.emit_json(resp)
    elif isinstance(data, list):
        cols = [
            {"key": "type", "header": "Type"},
            {"key": "tool", "header": "Tool"},
            {"key": "duration_ms", "header": "Duration (ms)"},
            {"key": "timestamp", "header": "Time"},
        ]
        r.table(cols, data, resp)
    else:
        r.detail({"Trace": str(data)}, title="Agent Trace", raw=resp)


# -- Streaming helpers -------------------------------------------------------


async def _ensure_conversation(
    cli_ctx: CliContext, project_id: str, conversation_id: str | None
) -> str:
    """Create a conversation if needed and validate the returned ID."""
    if conversation_id:
        return conversation_id
    conv_resp = await cli_ctx.client.post(
        "/agent/conversations", {"project_id": project_id}
    )
    cid = (conv_resp.data or {}).get("id", "")
    if not cid:
        raise ApiError(
            code="INVALID_RESPONSE",
            message="Backend did not return a conversation ID.",
            status_code=0,
        )
    return cid


def _extract_message_chunk(raw_data: str) -> str:
    """Parse an agent.message SSE event and return the content chunk."""
    try:
        data = json.loads(raw_data)
        return data.get("data", {}).get("content") or data.get("content", "")
    except (json.JSONDecodeError, TypeError):
        return ""


async def _collect_agent_response(
    cli_ctx: CliContext,
    r: Renderer,
    project_id: str,
    conversation_id: str,
    *,
    on_approval: bool = False,
) -> str:
    """Stream SSE events and return the accumulated human-mode text."""
    text = ""
    async for event in cli_ctx.client.stream_sse(
        "/events/stream",
        {"project_id": project_id, "conversation_id": conversation_id},
    ):
        if r.is_json:
            r.stream_event(event)
        else:
            if event.event == "agent.message":
                chunk = _extract_message_chunk(event.data)
                if chunk:
                    text += chunk
            elif on_approval and event.event == "agent.approval.requested":
                await _handle_approval(cli_ctx, event.data)
        if event.event in TERMINAL_AGENT_EVENTS:
            break
    return text


async def _handle_approval(cli_ctx: CliContext, raw_data: str) -> None:
    """Prompt the user to approve or reject an agent tool call."""
    try:
        data = json.loads(raw_data)
        approval_data = data.get("data", data)
        tool = approval_data.get("tool", "unknown")
        cli_ctx.console.print(f"\n[yellow]Approval needed for: {tool}[/yellow]")
        choice = input("[y/n] > ").strip().lower()
        action = "approve" if choice == "y" else "reject"
        approval_id = approval_data.get("approval_id", "")
        if approval_id:
            await cli_ctx.client.post(
                f"/agent/approvals/{approval_id}/resolve",
                {"action": action},
            )
    except (json.JSONDecodeError, TypeError, EOFError):
        pass


def _read_input(r: Renderer) -> str | None:
    """Read a line of user input; return None on EOF."""
    if r.is_json:
        line = sys.stdin.readline()
        return line.strip() if line else None
    try:
        return input("bif> ")
    except EOFError:
        return None


async def _send(
    cli_ctx: CliContext,
    r: Renderer,
    project_id: str,
    message: str,
    conversation_id: str | None,
) -> None:
    """Send a single message, stream SSE response, print final answer."""
    cid = await _ensure_conversation(cli_ctx, project_id, conversation_id)
    new_conversation = conversation_id is None
    if new_conversation and not r.is_json and not cli_ctx.quiet:
        cli_ctx.console.print(f"[dim]Conversation: {cid}[/dim]")
    await cli_ctx.client.post(
        "/agent/message",
        {"conversation_id": cid, "project_id": project_id, "content": message},
    )
    try:
        text = await _collect_agent_response(cli_ctx, r, project_id, cid)
    except KeyboardInterrupt:
        text = ""
    if not r.is_json and text:
        cli_ctx.console.print(text)
        if new_conversation and not cli_ctx.quiet:
            cli_ctx.console.print(
                f"\n[dim]Continue with: bif agent send --conversation {cid} ...[/dim]"
            )


async def _chat_loop(
    cli_ctx: CliContext,
    r: Renderer,
    project_id: str,
    conversation_id: str | None,
) -> None:
    """Interactive REPL — prompt, send, stream, repeat."""
    cid = await _ensure_conversation(cli_ctx, project_id, conversation_id)
    if not r.is_json:
        cli_ctx.console.print(f"[dim]Conversation: {cid}[/dim]")

    try:
        while True:
            user_input = _read_input(r)
            if user_input is None:
                break
            if not user_input:
                continue
            if user_input in ("/exit", "/quit"):
                break

            await cli_ctx.client.post(
                "/agent/message",
                {
                    "conversation_id": cid,
                    "project_id": project_id,
                    "content": user_input,
                },
            )
            answer = await _collect_agent_response(
                cli_ctx, r, project_id, cid, on_approval=True
            )
            if not r.is_json and answer:
                cli_ctx.console.print(answer)
                cli_ctx.console.print()
    except KeyboardInterrupt:
        if not r.is_json:
            cli_ctx.console.print("\n[dim]Exiting chat.[/dim]")

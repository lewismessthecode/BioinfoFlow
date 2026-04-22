"""bif agent approvals — list and resolve pending approvals."""

from __future__ import annotations

import typer

from app.cli.api_helpers import api_get, api_post
from app.cli.errors import handle_errors
from app.cli.helpers import unpack_ctx

approvals_app = typer.Typer(
    name="approvals", help="Manage agent approval requests.", no_args_is_help=True
)


@approvals_app.command("list")
@handle_errors
def approvals_list(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(help="Conversation ID"),
    pending_only: bool = typer.Option(False, "--pending", help="Only show pending"),
) -> None:
    """List approval requests for a conversation."""
    cli_ctx, r = unpack_ctx(ctx)
    endpoint = (
        f"/agent/conversations/{conversation_id}/approvals/pending"
        if pending_only
        else f"/agent/conversations/{conversation_id}/approvals"
    )
    resp = cli_ctx.run(api_get(cli_ctx, endpoint))
    data = resp.data if isinstance(resp.data, list) else []
    cols = [
        {"key": "id", "header": "ID"},
        {"key": "tool", "header": "Tool"},
        {"key": "status", "header": "Status"},
        {"key": "created_at", "header": "Created"},
    ]
    r.table(cols, data, resp)


@approvals_app.command("resolve")
@handle_errors
def approvals_resolve(
    ctx: typer.Context,
    approval_id: str = typer.Argument(help="Approval ID"),
    action: str = typer.Argument(help="Action: approve or reject"),
) -> None:
    """Approve or reject a pending approval."""
    cli_ctx, r = unpack_ctx(ctx)
    if action not in ("approve", "reject"):
        raise typer.BadParameter("Action must be 'approve' or 'reject'")
    resp = cli_ctx.run(
        api_post(cli_ctx, f"/agent/approvals/{approval_id}/resolve", {"action": action})
    )
    verb = "approved" if action == "approve" else "rejected"
    r.success(f"Approval {approval_id} {verb}.", raw=resp)

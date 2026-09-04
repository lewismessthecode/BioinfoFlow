"""Application boundary for Agent mutations that carry public presentation data.

The repository owns the transaction, sequence allocation and lease fence.  This
service owns the only conversion from private tool/interaction inputs to the
versioned, safe data that may become durable conversation history.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from app.services.agent_harness.contracts import ToolProgressView
from app.services.agent_harness.projection import (
    public_interaction_request,
    public_interaction_response,
)
from app.services.agent_harness.tool_projection import (
    public_error_message,
    public_result_details,
    public_tool_details,
    public_tool_progress_view,
)


ToolProgressProjector = Callable[[dict[str, Any], datetime], dict[str, Any]]


class AgentPresentationMutationWriter(Protocol):
    async def update_tool_progress(
        self,
        run_id: str,
        *,
        call_id: str,
        progress_projector: ToolProgressProjector,
    ) -> dict[str, Any]: ...

    async def commit_waiting_interaction(
        self, session_id: str, **values: Any
    ) -> Any: ...

    async def commit_interaction_response(
        self, session_id: str, **values: Any
    ) -> Any: ...

    async def begin_approved_tool_execution(
        self, session_id: str, **values: Any
    ) -> Any: ...


class AgentPresentationMutationService:
    """Prepare public Agent data while retaining repository atomic mutations."""

    def __init__(self, repository: AgentPresentationMutationWriter) -> None:
        self.repository = repository

    async def update_tool_progress(
        self,
        run_id: str,
        *,
        call_id: str,
        name: str,
        status: str,
        group_id: str | None = None,
        execution_mode: str | None = None,
        arguments: dict[str, Any] | None = None,
        output_summary: str | None = None,
        error: str | None = None,
    ) -> ToolProgressView:
        """Atomically replace one progress record with its safe public form."""

        del group_id, execution_mode  # Stored metadata is immutable after creation.

        def project(existing: dict[str, Any], now: datetime) -> dict[str, Any]:
            source_arguments = (
                arguments
                if arguments is not None
                else existing.get("arguments")
                if isinstance(existing.get("arguments"), dict)
                else {}
            )
            public_output = public_error_message(output_summary)
            public_error = public_error_message(error)
            existing_details = [
                detail
                for detail in existing.get("public_details") or []
                if isinstance(detail, dict)
                and detail.get("kind") not in {"output", "error"}
            ]
            input_details = existing_details or [
                detail.model_dump(mode="json")
                for detail in public_tool_details(name, source_arguments)
            ]
            raw: dict[str, Any] = {
                **existing,
                "call_id": call_id,
                "group_id": existing["group_id"],
                "execution_mode": existing["execution_mode"],
                "name": name,
                "display_name": existing["display_name"],
                "category": existing["category"],
                "summary": existing["summary"],
                "arguments": {},
                "status": status,
                "revision": int(existing.get("revision") or 0) + 1,
                "public_details": [
                    *input_details,
                    *[
                        detail.model_dump(mode="json")
                        for detail in public_result_details(
                            output_summary=public_output,
                            error=public_error,
                        )
                    ],
                ],
            }
            if public_output is not None:
                raw["output_summary"] = public_output
            if public_error is not None:
                raw["error"] = public_error
            if status == "running" and raw.get("started_at") is None:
                raw["started_at"] = now
            if status in {"completed", "failed", "blocked", "cancelled"}:
                raw["completed_at"] = now
            return public_tool_progress_view(raw).model_dump(mode="json")

        stored = await self.repository.update_tool_progress(
            run_id,
            call_id=call_id,
            progress_projector=project,
        )
        return ToolProgressView.model_validate(stored)

    async def commit_waiting_interaction(
        self,
        session_id: str,
        *,
        request_payload: dict[str, Any],
        **values: Any,
    ) -> Any:
        request = dict(request_payload)
        request["request"] = public_interaction_request(request_payload["request"])
        return await self.repository.commit_waiting_interaction(
            session_id,
            request_payload=request,
            **values,
        )

    async def commit_interaction_response(
        self,
        session_id: str,
        *,
        response: dict[str, Any],
        **values: Any,
    ) -> Any:
        return await self.repository.commit_interaction_response(
            session_id,
            response=public_interaction_response(response),
            **values,
        )

    async def begin_approved_tool_execution(
        self,
        session_id: str,
        *,
        response: dict[str, Any],
        call: dict[str, Any],
        **values: Any,
    ) -> Any:
        call_id = str(call.get("call_id") or "")
        name = str(call.get("name") or "unknown")

        def project(existing: dict[str, Any], now: datetime) -> dict[str, Any]:
            return public_tool_progress_view(
                {
                    **existing,
                    "call_id": call_id,
                    "group_id": existing["group_id"],
                    "execution_mode": existing["execution_mode"],
                    "name": name,
                    "display_name": existing["display_name"],
                    "category": existing["category"],
                    "summary": existing["summary"],
                    "arguments": existing.get("arguments") or {},
                    "status": "running",
                    "revision": int(existing.get("revision") or 0) + 1,
                    "started_at": existing.get("started_at") or now,
                }
            ).model_dump(mode="json")

        return await self.repository.begin_approved_tool_execution(
            session_id,
            response=public_interaction_response(response),
            call=call,
            progress_projector=project,
            **values,
        )


__all__ = [
    "AgentPresentationMutationService",
    "AgentPresentationMutationWriter",
    "ToolProgressProjector",
]

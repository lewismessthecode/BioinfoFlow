from __future__ import annotations

from typing import Protocol

from app.models.agent_harness import (
    AgentHarnessEntry,
    AgentHarnessRun,
    AgentHarnessSession,
)
from app.services.agent_harness.contracts import (
    ActiveRunView,
    AssistantDraftView,
    PendingInteractionView,
    SessionSnapshot,
    SessionView,
    ToolProgressView,
)
from app.services.agent_harness.projection import (
    entry_contract,
    pending_interaction_entry_view,
    public_model_summary,
    run_view,
)
from app.services.agent_harness.tool_projection import public_tool_progress_view


class SnapshotRepository(Protocol):
    async def get_session(self, session_id: str) -> AgentHarnessSession | None: ...

    async def list_runs(self, session_id: str) -> list[AgentHarnessRun]: ...

    async def list_entries(self, session_id: str) -> list[AgentHarnessEntry]: ...


class AgentHarnessSnapshotService:
    """Build the stable public projection of an Agent session."""

    def __init__(self, repository: SnapshotRepository) -> None:
        self.repository = repository

    async def build(self, session_id: str) -> SessionSnapshot:
        session = await self.repository.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        runs = await self.repository.list_runs(session_id)
        run = next(
            (
                item
                for item in reversed(runs)
                if item.status in ("queued", "running", "waiting_user")
            ),
            None,
        )
        entries = await self.repository.list_entries(session_id)
        active_run = (
            ActiveRunView(
                run=run_view(run),
                assistant_draft=self._assistant_draft(run),
                tool_progress=self._tool_progress(run),
                pending_interaction=self._pending_interaction(run, entries),
            )
            if run is not None
            else None
        )
        return SessionSnapshot(
            session=SessionView.model_validate(
                {
                    "id": session.id,
                    "user_id": session.user_id,
                    "workspace_id": session.workspace_id,
                    "project_id": session.project_id,
                    "title": session.title,
                    "model": public_model_summary(session.model_snapshot),
                    "permission_mode": session.permission_mode,
                    "workspace_access": session.workspace_access,
                    "settings_revision": session.settings_revision,
                    "environment_scope": session.environment_scope or {"mode": "auto"},
                    "status": session.status,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                }
            ),
            runs=[run_view(item) for item in runs],
            entries=[
                entry_contract(entry)
                for entry in entries
                if entry.type not in {"compaction", "context_update"}
            ],
            active_run=active_run,
        )

    @staticmethod
    def _assistant_draft(run: AgentHarnessRun | None) -> AssistantDraftView | None:
        if run is None or not run.draft:
            return None
        return AssistantDraftView.model_validate(run.draft)

    @staticmethod
    def _tool_progress(run: AgentHarnessRun | None) -> list[ToolProgressView]:
        if run is None or not run.tool_progress:
            return []
        return [public_tool_progress_view(item) for item in run.tool_progress]

    @staticmethod
    def _pending_interaction(
        run: AgentHarnessRun | None,
        entries: list[AgentHarnessEntry],
    ) -> PendingInteractionView | None:
        if run is None or run.status != "waiting_user":
            return None
        pending: dict[str, AgentHarnessEntry] = {}
        for entry in entries:
            if str(entry.run_id) != str(run.id):
                continue
            interaction_id = str(entry.payload.get("interaction_id") or "")
            if not interaction_id:
                continue
            if entry.type == "interaction_request":
                pending[interaction_id] = entry
            elif entry.type == "interaction_response":
                pending.pop(interaction_id, None)
        if not pending:
            return None
        request = max(pending.values(), key=lambda item: item.sequence)
        return pending_interaction_entry_view(request)

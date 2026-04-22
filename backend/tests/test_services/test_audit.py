from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.project import Project
from app.services.audit_service import AuditService


@pytest.mark.asyncio
async def test_audit_service_logs_and_lists_run_events(db_session):
    project = Project(
        name=f"Audit Project {uuid4()}", storage_mode="managed", external_root_path=None, user_id="dev"
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    service = AuditService(db_session)
    await service.log(
        action="run.created",
        resource_type="run",
        resource_id="run_audit_123",
        project_id=str(project.id),
        actor="api",
        details={"status": "queued"},
    )
    await service.log(
        action="run.completed",
        resource_type="run",
        resource_id="run_audit_123",
        project_id=str(project.id),
        actor="scheduler",
        details={"status": "completed"},
    )

    entries = await service.list_for_resource("run", "run_audit_123")

    by_action = {entry.action: entry for entry in entries}
    assert set(by_action) == {"run.created", "run.completed"}
    assert by_action["run.created"].actor == "api"
    assert by_action["run.completed"].details["status"] == "completed"

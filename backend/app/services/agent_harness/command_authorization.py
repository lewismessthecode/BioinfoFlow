"""Authorization for references embedded in Agent commands.

This is an application seam between the HTTP command route and the file,
workflow, run and attachment repositories.  It validates every referenced
resource before a command reaches the runtime and normalizes accepted paths.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import AuthUser
from app.repositories.agent_harness_repo import AgentHarnessAttachmentRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.project_workflow_binding_repo import (
    ProjectWorkflowBindingRepository,
)
from app.services.agent_harness.contracts import (
    AgentCommand,
    InputAttachmentRefPart,
    InputDirectoryRefPart,
    InputFileRefPart,
    InputRunRefPart,
    InputWorkflowRefPart,
    MessageCommand,
    SteerCommand,
)
from app.services.file_service import FileService
from app.services.run_service import RunService
from app.services.workflow_service import WorkflowService
from app.utils.authorization import can_access_project
from app.utils.exceptions import BadRequestError, NotFoundError, PermissionDeniedError


async def authorize_command_parts(
    db: AsyncSession,
    *,
    session_id: str,
    project_id: str | None,
    command: AgentCommand,
    user: AuthUser,
) -> None:
    """Validate and normalize resource references in a message or steer command."""

    if not isinstance(command, (MessageCommand, SteerCommand)):
        return

    attachment_ids = []
    for part in command.parts:
        if isinstance(part, InputAttachmentRefPart):
            attachment_ids.append(str(part.attachment_id))
        elif isinstance(part, (InputFileRefPart, InputDirectoryRefPart)):
            if part.attachment_id is not None:
                attachment_ids.append(str(part.attachment_id))
    attachments_by_id = {}
    if attachment_ids:
        try:
            attachments = await AgentHarnessAttachmentRepository(
                db
            ).require_ids_for_session(
                attachment_ids,
                session_id=session_id,
                workspace_id=user.workspace_id,
                user_id=user.id,
            )
        except LookupError as exc:
            raise NotFoundError("One or more attachments were not found") from exc
        attachments_by_id = {str(item.id): item for item in attachments}

    file_service = FileService(db)
    for part in command.parts:
        if isinstance(part, (InputFileRefPart, InputDirectoryRefPart)):
            if part.attachment_id is not None:
                attachment = attachments_by_id[str(part.attachment_id)]
                is_directory = attachment.kind == "folder"
                if isinstance(part, InputFileRefPart) and is_directory:
                    raise BadRequestError("file_ref must reference a file")
                if isinstance(part, InputDirectoryRefPart) and not is_directory:
                    raise BadRequestError("directory_ref must reference a directory")
                continue
            assert part.project_id is not None
            assert part.path is not None
            try:
                target, root = await file_service.resolve_path(
                    project_id=str(part.project_id),
                    path=part.path,
                    user_id=user.id,
                    workspace_id=user.workspace_id,
                )
            except (FileNotFoundError, PermissionError, PermissionDeniedError) as exc:
                raise NotFoundError("Referenced path was not found") from exc
            if isinstance(part, InputFileRefPart) and not target.is_file():
                raise BadRequestError("file_ref must reference a file")
            if isinstance(part, InputDirectoryRefPart) and not target.is_dir():
                raise BadRequestError("directory_ref must reference a directory")
            part.path = target.relative_to(root).as_posix()
        elif isinstance(part, InputWorkflowRefPart):
            workflow_id = str(part.workflow_id)
            workflow = await WorkflowService(db).get_workflow(workflow_id)
            if workflow is None:
                raise NotFoundError("Referenced workflow was not found")
            if part.scope == "project":
                assert part.project_id is not None
                referenced_project_id = str(part.project_id)
                project = await ProjectRepository(db).get(referenced_project_id)
                if project is None or not can_access_project(
                    project,
                    user_id=user.id,
                    workspace_id=user.workspace_id,
                ):
                    raise NotFoundError("Referenced workflow was not found")
                if not await ProjectWorkflowBindingRepository(db).is_enabled(
                    project_id=referenced_project_id,
                    workflow_id=workflow_id,
                ):
                    raise NotFoundError("Referenced workflow was not found")
        elif isinstance(part, InputRunRefPart):
            try:
                run = await RunService(db).get_run(
                    part.run_id,
                    user_id=user.id,
                    workspace_id=user.workspace_id,
                )
            except PermissionDeniedError as exc:
                raise NotFoundError("Referenced run was not found") from exc
            if run is None or str(run.project_id) != project_id:
                raise NotFoundError("Referenced run was not found")
            part.run_id = str(run.run_id)


__all__ = ["authorize_command_parts"]

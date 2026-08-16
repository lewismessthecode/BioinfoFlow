from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.auth.session import AuthUser
from app.repositories.project_repo import ProjectRepository
from app.schemas.common import SuccessEnvelope
from app.services.agent_harness.starter_prompts import (
    InMemoryStarterPromptCache,
    StarterPromptService,
)
from app.services.agent_harness.starter_prompt_generation import (
    build_starter_prompt_generator,
)
from app.utils.authorization import can_access_project
from app.utils.exceptions import NotFoundError
from app.utils.responses import success_response


router = APIRouter(prefix="/agent", tags=["agent"])
_cache = InMemoryStarterPromptCache()


class StarterPromptsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompts: list[str]
    source: str
    refresh_pending: bool


@router.get(
    "/starter-prompts",
    response_model=SuccessEnvelope[StarterPromptsRead],
)
async def get_starter_prompts(
    request: Request,
    background_tasks: BackgroundTasks,
    project_id: UUID = Query(),
    locale: str = Query(default="en", min_length=2, max_length=20),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_key = str(project_id)
    project = await ProjectRepository(db).get(project_key)
    if (
        project is None
        or str(project.workspace_id) != user.workspace_id
        or not can_access_project(
            project,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
    ):
        raise NotFoundError(f"Project not found: {project_key}")
    context = {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "storage_mode": project.storage_mode,
        "project_root": project.project_root,
    }
    service = StarterPromptService(
        cache=_cache,
        generate=build_starter_prompt_generator(
            db,
            workspace_id=user.workspace_id,
            user_id=user.id,
        ),
    )
    result = await service.resolve(project=context, locale=locale)
    if result.refresh_required:
        background_tasks.add_task(service.refresh, project=context, locale=locale)
    return success_response(
        StarterPromptsRead(
            prompts=list(result.prompts),
            source=result.source,
            refresh_pending=result.refresh_required,
        ).model_dump(mode="json"),
        request=request,
    )

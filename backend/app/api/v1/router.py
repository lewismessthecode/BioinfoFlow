from fastapi import APIRouter

from app.api.v1.batch import router as batch_router
from app.api.v1.events import router as events_router
from app.api.v1.files import router as files_router
from app.api.v1.images import router as images_router
from app.api.v1.agent import router as agent_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.project_workflows import router as project_workflows_router
from app.api.v1.projects import router as projects_router
from app.api.v1.providers import router as providers_router
from app.api.v1.runs import router as runs_router
from app.api.v1.scheduler import router as scheduler_router
from app.api.v1.stats import router as stats_router
from app.api.v1.storage import router as storage_router
from app.api.v1.system import router as system_router
from app.api.v1.terminal import router as terminal_router
from app.api.v1.user_settings import router as user_settings_router
from app.api.v1.workflows import router as workflows_router

api_router = APIRouter()
api_router.include_router(projects_router)
api_router.include_router(project_workflows_router)
api_router.include_router(workflows_router)
api_router.include_router(files_router)
api_router.include_router(storage_router)
api_router.include_router(images_router)
api_router.include_router(events_router)
api_router.include_router(batch_router)
api_router.include_router(runs_router)
api_router.include_router(notifications_router)
api_router.include_router(scheduler_router)
api_router.include_router(agent_router)
api_router.include_router(stats_router)
api_router.include_router(system_router)
api_router.include_router(terminal_router)
api_router.include_router(user_settings_router)
api_router.include_router(providers_router)

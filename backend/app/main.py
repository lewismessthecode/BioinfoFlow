from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.exceptions import RequestValidationError

from app.api.v1.router import api_router
from app.config import settings
from app.database import close_db, init_db, verify_database_schema_current
from app.engine.local import LocalBackend
from app.path_layout import assert_identity_mount, ensure_platform_layout
from app.runtime.background_tasks import background_tasks
from app.runtime.jobs import recover_stale_runs
from app.runtime.task_runner import task_runner
from app.scheduler.config import SchedulerConfig
from app.scheduler.monitor import ResourceMonitor
from app.scheduler.scheduler import RunScheduler
from app.services.workspace_service import WorkspaceService
from app.services.run_dispatch import (
    SchedulerDispatcher,
    set_run_dispatcher,
    set_run_scheduler,
)
from app.services.llm.bootstrap import sync_environment_llm_catalog
from app.startup_logging import log_startup_banner, log_startup_summary
from app.services.terminal_service import terminal_manager
from app.utils.exceptions import AppError, http_error_code
from app.utils.logging import (
    bind_request_id,
    clear_request_context,
    configure_logging,
    get_logger,
)
from app.utils.responses import error_response


configure_logging(settings.debug)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle hooks."""
    log_startup_banner(settings)
    logger.info("startup.begin", app=settings.app_name, version=settings.app_version)
    assert_identity_mount()
    ensure_platform_layout()
    log_startup_summary(settings)
    logger.info("startup.platform_layout.ready")
    await init_db()
    await verify_database_schema_current()
    logger.info("startup.database.ready")
    async with app.state_db_session() as session:
        workspace_service = WorkspaceService(session)
        await workspace_service.ensure_default_workspace()
        await sync_environment_llm_catalog(session)
        await session.commit()
    logger.info("startup.workspace.ready")
    scheduler: RunScheduler | None = None
    monitor: ResourceMonitor | None = None
    monitor = ResourceMonitor(sample_interval=30.0)
    scheduler = RunScheduler(
        config=SchedulerConfig.from_settings(settings),
        backend=LocalBackend(),
        monitor=monitor,
    )
    await scheduler.start()
    logger.info(
        "startup.scheduler.ready",
        total_slots=scheduler.config.effective_total_slots(),
        max_workers=scheduler.config.effective_max_workers(),
        queue_depth_limit=scheduler.config.max_queue_depth,
    )
    if monitor is not None:
        await monitor.start()
        logger.info(
            "startup.resource_monitor.ready",
            sample_interval_seconds=settings.scheduler_resource_sample_interval,
        )
    set_run_scheduler(scheduler)
    set_run_dispatcher(SchedulerDispatcher(scheduler))
    await recover_stale_runs(
        stale_after_minutes=settings.scheduler_stale_timeout_minutes
    )
    logger.info(
        "startup.run_recovery.complete",
        stale_after_minutes=settings.scheduler_stale_timeout_minutes,
    )
    await task_runner.start()
    logger.info("startup.task_runner.ready")
    await background_tasks.start()
    logger.info("startup.background_tasks.ready")
    logger.info("startup.ready")
    yield
    logger.info("shutdown.begin")
    await terminal_manager.shutdown()
    logger.info("shutdown.terminals.complete")
    if monitor is not None:
        await monitor.stop()
        logger.info("shutdown.resource_monitor.complete")
    if scheduler is not None:
        await scheduler.stop()
        logger.info("shutdown.scheduler.complete")
    set_run_scheduler(None)
    set_run_dispatcher(None)
    await background_tasks.stop()
    logger.info("shutdown.background_tasks.complete")
    await task_runner.stop()
    logger.info("shutdown.task_runner.complete")
    await close_db()
    logger.info("shutdown.database.complete")


@asynccontextmanager
async def _state_db_session():
    from app.api.deps import get_db

    get_db_dep = app.dependency_overrides.get(get_db, get_db)
    agen = get_db_dep()
    session = await agen.__anext__()
    try:
        yield session
    finally:
        await agen.aclose()


app = FastAPI(
    title=f"{settings.app_name} API",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)
app.state_db_session = _state_db_session

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_hosts,
)


@app.middleware("http")
async def bind_request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID")
    bind_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        clear_request_context()
    return response


app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    logger.warning("app.error", code=exc.code, message=exc.message)
    return error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        request=request,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    logger.info("app.validation_error", errors=exc.errors())
    return error_response(
        code="VALIDATION_ERROR",
        message="Validation error",
        status_code=422,
        details=exc.errors(),
        request=request,
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    code = http_error_code(exc.status_code)
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    logger.warning("app.http_error", code=code, status=exc.status_code)
    return error_response(
        code=code,
        message=message or code,
        status_code=exc.status_code,
        request=request,
    )


@app.exception_handler(Exception)
async def handle_unhandled_exception(request: Request, exc: Exception):
    logger.exception(
        "app.unhandled_exception",
        path=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
        error=str(exc)[:200],
    )
    return error_response(
        code="INTERNAL_ERROR",
        message="Internal server error",
        status_code=500,
        request=request,
    )

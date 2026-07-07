from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING
from urllib.parse import unquote

from app.config import settings
from app.utils.exceptions import BadRequestError

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.workflow import Workflow

_SAFE_PATH_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class ResolvedAssetPath:
    source_id: str
    relative_path: str
    path: Path


def bioinfoflow_home() -> Path:
    return Path(settings.bioinfoflow_home).resolve()


def state_root() -> Path:
    return settings.state_root.resolve()


def skills_root() -> Path:
    return settings.skills_root.resolve()


def auth_root() -> Path:
    return state_root() / "auth"


def workflows_root() -> Path:
    return settings.workflow_registry_root.resolve()


def run_uploads_root() -> Path:
    return state_root() / "run_uploads"


def project_run_uploads_root(project: Project | str) -> Path:
    project_id = safe_path_name(
        str(project.id) if not isinstance(project, str) else project,
        field_name="project id",
    )
    return run_uploads_root() / project_id


def local_workflows_root() -> Path:
    return workflows_root() / "local"


def workflow_home(workflow_id: str) -> Path:
    return local_workflows_root() / safe_path_name(
        workflow_id, field_name="workflow id"
    )


def workflow_bundle_home(workflow_id: str) -> Path:
    return workflow_home(workflow_id) / "bundle"


def workflow_metadata_path(workflow_id: str) -> Path:
    return workflow_home(workflow_id) / "metadata.json"


def workflow_entrypoint_path(workflow: Workflow) -> Path:
    return safe_join(
        workflow_bundle_home(str(workflow.id)),
        workflow.entrypoint_relpath,
        escape_message="workflow entrypoint escapes bundle",
    )


def sources_root() -> Path:
    return settings.sources_root.resolve()


def deliveries_root() -> Path:
    return settings.deliveries_root.resolve()


def reference_root() -> Path:
    return settings.reference_root.resolve()


def database_root() -> Path:
    return settings.database_root.resolve()


def projects_root() -> Path:
    return settings.projects_root.resolve()


def project_home(
    project: Project | str, *, external_root_path: str | None = None
) -> Path:
    if isinstance(project, str):
        if external_root_path:
            return Path(external_root_path).expanduser().resolve()
        return (
            projects_root() / safe_path_name(project, field_name="project id")
        ).resolve()

    storage_mode = str(getattr(project, "storage_mode", "managed") or "managed")
    if storage_mode == "external":
        override = external_root_path or getattr(project, "external_root_path", None)
        if not override:
            raise ValueError("external project requires external_root_path")
        return Path(str(override)).expanduser().resolve()
    if storage_mode == "remote":
        raise BadRequestError("Remote projects do not have a local project root")
    return (projects_root() / str(project.id)).resolve()


def project_data_root(
    project: Project | str, *, external_root_path: str | None = None
) -> Path:
    return project_home(project, external_root_path=external_root_path) / "data"


def project_runs_root(
    project: Project | str, *, external_root_path: str | None = None
) -> Path:
    return project_home(project, external_root_path=external_root_path) / "runs"


def run_home(
    project: Project | str, run_id: str, *, external_root_path: str | None = None
) -> Path:
    return project_runs_root(
        project, external_root_path=external_root_path
    ) / safe_path_name(
        run_id,
        field_name="run id",
    )


def run_input_root(
    project: Project | str, run_id: str, *, external_root_path: str | None = None
) -> Path:
    return run_home(project, run_id, external_root_path=external_root_path) / "input"


def run_input_request_root(
    project: Project | str, run_id: str, *, external_root_path: str | None = None
) -> Path:
    return (
        run_input_root(project, run_id, external_root_path=external_root_path)
        / "request"
    )


def run_manifest_materialized_root(
    project: Project | str, run_id: str, *, external_root_path: str | None = None
) -> Path:
    return (
        run_input_root(project, run_id, external_root_path=external_root_path)
        / "materialized"
    )


def run_materialized_attachments_root(
    project: Project | str, run_id: str, *, external_root_path: str | None = None
) -> Path:
    return (
        run_manifest_materialized_root(
            project,
            run_id,
            external_root_path=external_root_path,
        )
        / "attachments"
    )


def run_input_attachments_root(
    project: Project | str, run_id: str, *, external_root_path: str | None = None
) -> Path:
    return (
        run_input_root(project, run_id, external_root_path=external_root_path)
        / "attachments"
    )


def run_engine_root(
    project: Project | str, run_id: str, *, external_root_path: str | None = None
) -> Path:
    return run_home(project, run_id, external_root_path=external_root_path) / "engine"


def run_engine_workspace(
    project: Project | str,
    run_id: str,
    engine: str,
    *,
    external_root_path: str | None = None,
) -> Path:
    return (
        run_engine_root(project, run_id, external_root_path=external_root_path)
        / _normalize_engine_dir(engine)
        / "work"
    )


def run_results_root(
    project: Project | str, run_id: str, *, external_root_path: str | None = None
) -> Path:
    return run_home(project, run_id, external_root_path=external_root_path) / "results"


def run_audit_root(
    project: Project | str, run_id: str, *, external_root_path: str | None = None
) -> Path:
    return run_home(project, run_id, external_root_path=external_root_path) / "audit"


def ensure_project_layout(
    project: Project | str, *, external_root_path: str | None = None
) -> None:
    project_data_root(project, external_root_path=external_root_path).mkdir(
        parents=True, exist_ok=True
    )
    project_runs_root(project, external_root_path=external_root_path).mkdir(
        parents=True, exist_ok=True
    )


def ensure_run_layout(
    project: Project | str,
    run_id: str,
    *,
    engine: str,
    external_root_path: str | None = None,
) -> None:
    run_home(project, run_id, external_root_path=external_root_path).mkdir(
        parents=True,
        exist_ok=False,
    )
    run_input_root(project, run_id, external_root_path=external_root_path).mkdir()
    run_engine_workspace(
        project, run_id, engine, external_root_path=external_root_path
    ).mkdir(parents=True)
    run_results_root(project, run_id, external_root_path=external_root_path).mkdir()
    run_audit_root(project, run_id, external_root_path=external_root_path).mkdir()


def ensure_platform_layout() -> None:
    for path in (
        state_root(),
        skills_root(),
        auth_root(),
        workflows_root(),
        deliveries_root(),
        reference_root(),
        database_root(),
        projects_root(),
        settings.nextflow_cache_root.resolve(),
        settings.miniwdl_cache_root.resolve(),
    ):
        path.mkdir(parents=True, exist_ok=True)


def assert_identity_mount() -> None:
    """Enforce Path Contract v3: host path == container path.

    When the backend runs in a container, BIOINFOFLOW_HOME_HOST must equal the
    resolved BIOINFOFLOW_HOME. That invariant lets miniwdl task containers use
    the same absolute paths the backend sees, removing every host↔container
    translation layer from the code path. Bare-metal runs (uvicorn directly on
    the host) leave BIOINFOFLOW_HOME_HOST empty and skip the check.
    """
    home = bioinfoflow_home()
    host_home = (settings.bioinfoflow_home_host or "").strip()
    if not host_home:
        return
    if Path(host_home).resolve() != home:
        raise RuntimeError(
            "Path Contract v3 violated: "
            f"BIOINFOFLOW_HOME_HOST={host_home!r} must equal "
            f"BIOINFOFLOW_HOME={str(home)!r}. "
            f"Fix docker-compose with: -v {home}:{home}"
        )


def safe_join(root: Path, relative_path: str, *, escape_message: str) -> Path:
    parts = _validated_relative_parts(relative_path, escape_message=escape_message)
    resolved_root = root.resolve()
    target = resolved_root.joinpath(*parts).resolve()
    if not target.is_relative_to(resolved_root):
        raise PermissionError(escape_message)
    return target


def path_relative_to(root: Path, target: Path) -> str:
    return str(target.resolve().relative_to(root.resolve()))


def resolve_asset(project: Project, asset_uri: str) -> ResolvedAssetPath:
    if not asset_uri.startswith("asset://"):
        raise ValueError("invalid asset uri")

    remainder = asset_uri[len("asset://") :]
    source_id, sep, rest = remainder.partition("/")
    if not source_id:
        raise ValueError("invalid asset uri")

    if source_id == "project":
        rel = _normalize_relative_path(rest or ".")
        return ResolvedAssetPath(
            source_id="project",
            relative_path=rel,
            path=safe_join(
                project_data_root(project),
                rel,
                escape_message="asset path escapes project data",
            ),
        )

    if source_id == "results":
        run_id, sep, nested = rest.partition("/")
        if not sep or not run_id.strip():
            raise ValueError("results asset uri requires run id")
        run_id = safe_path_name(run_id.strip(), field_name="run id")
        rel = _normalize_relative_path(nested or ".")
        return ResolvedAssetPath(
            source_id="results",
            relative_path=f"{run_id}/{rel}",
            path=safe_join(
                run_results_root(project, run_id),
                rel,
                escape_message="asset path escapes run results",
            ),
        )

    if source_id == "deliveries":
        rel = _normalize_relative_path(rest or ".")
        return ResolvedAssetPath(
            source_id="deliveries",
            relative_path=rel,
            path=safe_join(
                deliveries_root(),
                rel,
                escape_message="asset path escapes deliveries",
            ),
        )

    if source_id == "reference":
        rel = _normalize_relative_path(rest or ".")
        return ResolvedAssetPath(
            source_id="reference",
            relative_path=rel,
            path=safe_join(
                reference_root(),
                rel,
                escape_message="asset path escapes reference",
            ),
        )

    if source_id == "database":
        rel = _normalize_relative_path(rest or ".")
        return ResolvedAssetPath(
            source_id="database",
            relative_path=rel,
            path=safe_join(
                database_root(),
                rel,
                escape_message="asset path escapes database",
            ),
        )

    if source_id == "run_upload":
        rel = _normalize_relative_path(rest or ".")
        return ResolvedAssetPath(
            source_id="run_upload",
            relative_path=rel,
            path=safe_join(
                project_run_uploads_root(project),
                rel,
                escape_message="asset path escapes run upload staging",
            ),
        )

    raise FileNotFoundError("invalid asset source")


def _normalize_relative_path(value: str) -> str:
    raw = unquote((value or ".").strip()) or "."
    normalized = raw.replace("\\", "/")
    return normalized if normalized else "."


def _validated_relative_parts(value: str, *, escape_message: str) -> tuple[str, ...]:
    normalized = _normalize_relative_path(value)
    if "\x00" in normalized:
        raise PermissionError(escape_message)
    if (
        PurePosixPath(normalized).is_absolute()
        or PureWindowsPath(normalized).is_absolute()
    ):
        raise PermissionError(escape_message)

    parts: list[str] = []
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise PermissionError(escape_message)
        parts.append(part)
    return tuple(parts)


def safe_path_name(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_PATH_NAME_RE.fullmatch(normalized):
        raise ValueError(f"invalid {field_name}")
    return normalized


def normalize_engine_dir(engine: str) -> str:
    normalized = str(engine or "").strip().lower()
    return safe_path_name(normalized or "unknown", field_name="engine")


def _normalize_engine_dir(engine: str) -> str:
    return normalize_engine_dir(engine)


def nextflow_work_dir(run_id: str) -> Path:
    return settings.nextflow_cache_root.resolve() / safe_path_name(
        run_id,
        field_name="run id",
    )


@dataclass(frozen=True, slots=True)
class RunLayout:
    """Frozen per-run directory layout.

    Consumers (engine adapters, archive, cleanup) read attributes from this
    dataclass instead of concatenating path tokens by hand. ``path_layout.py``
    is the only module that knows the literal directory names — any drift
    between callers becomes a compile error instead of a silent mount mishap.
    """

    home: Path
    input: Path
    request: Path
    materialized: Path
    attachments: Path
    materialized_attachments: Path
    engine_workspace: Path
    results: Path
    audit: Path

    @classmethod
    def for_run(
        cls,
        project,
        run_id: str,
        engine: str,
        *,
        external_root_path: str | None = None,
    ) -> "RunLayout":
        home = run_home(project, run_id, external_root_path=external_root_path)
        return cls(
            home=home,
            input=run_input_root(
                project, run_id, external_root_path=external_root_path
            ),
            request=run_input_request_root(
                project, run_id, external_root_path=external_root_path
            ),
            materialized=run_manifest_materialized_root(
                project, run_id, external_root_path=external_root_path
            ),
            attachments=run_input_attachments_root(
                project, run_id, external_root_path=external_root_path
            ),
            materialized_attachments=run_materialized_attachments_root(
                project, run_id, external_root_path=external_root_path
            ),
            engine_workspace=run_engine_workspace(
                project, run_id, engine, external_root_path=external_root_path
            ),
            results=run_results_root(
                project, run_id, external_root_path=external_root_path
            ),
            audit=run_audit_root(
                project, run_id, external_root_path=external_root_path
            ),
        )

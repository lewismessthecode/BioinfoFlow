from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.path_layout import (
    database_root,
    deliveries_root,
    projects_root,
    reference_root,
)
from app.services.docker_service import DockerService

logger = logging.getLogger(__name__)

# How long a mount snapshot is considered fresh. Picked short enough
# that a remount/reattach is reflected within one human-scale action
# but long enough that back-to-back WDL tasks aren't re-querying Docker.
_MOUNT_CACHE_TTL_SECONDS = 60.0
_mount_cache: tuple[tuple["ContainerPathMapping", ...], float] | None = None


def _reset_mount_cache() -> None:
    """Invalidate the mount-mapping cache. Used by tests."""
    global _mount_cache
    _mount_cache = None


@dataclass(frozen=True)
class ContainerPathMapping:
    container_root: Path
    host_root: Path
    read_only: bool = True


def configured_shared_mounts() -> tuple[ContainerPathMapping, ...]:
    """Shared read-only roots visible to every task container.

    Under Path Contract v3 (identity mount), host path == container path, so
    every mapping has `host_root == container_root`.
    """
    roots = (deliveries_root(), reference_root(), database_root())
    return tuple(
        ContainerPathMapping(container_root=r, host_root=r, read_only=True)
        for r in roots
    )


def configured_run_mounts(
    host_dir: str | os.PathLike[str],
) -> tuple[ContainerPathMapping, ...]:
    """Per-run mounts exposed to every task container for this run.

    Mounts are sibling-only — never nested — because Docker Swarm silently
    demotes a rw child mount to ro when its parent is also mounted ro.
    That's how a `results/` nested under a ro `project_root/` ended up
    un-writable in production: the deaf pipeline's `Prepare_wt.pl` quietly
    failed to create `$outdir/Sample.info`, then died reading it back with
    the misleading "Main ERROR read sample list error".

    `host_dir` is the miniwdl task working directory. We derive
    project_id and run_id from its position under `projects_root()`.
    """
    task_dir = Path(host_dir)
    try:
        relative = task_dir.relative_to(projects_root())
    except ValueError:
        return ()

    if len(relative.parts) < 3 or relative.parts[1] != "runs":
        return ()

    run_id = relative.parts[2]
    run_root = projects_root() / relative.parts[0] / "runs" / run_id

    input_root = run_root / "input"
    results_root = run_root / "results"

    return (
        ContainerPathMapping(
            container_root=input_root,
            host_root=input_root,
            read_only=True,
        ),
        ContainerPathMapping(
            container_root=results_root,
            host_root=results_root,
            read_only=False,
        ),
    )


# ---------------------------------------------------------------------------
# Escape hatch: legacy host↔container translation
# ---------------------------------------------------------------------------
# Preserved only for emergency diagnosis of a broken deployment, gated behind
# `settings.allow_path_translation`. Normal deployments rely on identity
# mount and keep this off.


def docker_mount_path_mappings() -> tuple[ContainerPathMapping, ...]:
    """Return the current container's bind mounts, cached with a short TTL.

    Gated behind ``settings.allow_path_translation`` — this is the
    emergency escape hatch for broken identity-mount deployments and is
    off by default under Path Contract v3. Previously used
    ``@lru_cache(maxsize=1)`` which snapshot once per process; the TTL
    (60 s) keeps back-to-back tasks cheap while still surfacing
    remounts promptly.
    """
    if not settings.allow_path_translation:
        return ()

    logger.warning(
        "BIOINFOFLOW_ALLOW_PATH_TRANSLATION is enabled: emergency escape hatch. "
        "Disable once the deployment is fixed to use identity mount "
        "(host path == container path)."
    )

    global _mount_cache
    now = time.monotonic()
    if _mount_cache is not None and now - _mount_cache[1] < _MOUNT_CACHE_TTL_SECONDS:
        return _mount_cache[0]

    container_id = _current_container_id()
    if not container_id:
        _mount_cache = ((), now)
        return ()

    try:
        container = DockerService().client.containers.get(container_id)
    except Exception:
        _mount_cache = ((), now)
        return ()

    mappings: list[ContainerPathMapping] = []
    for mount in list(container.attrs.get("Mounts") or []):
        source = str(mount.get("Source") or "").strip()
        destination = str(mount.get("Destination") or "").strip()
        if not source or not destination:
            continue
        container_root = Path(destination)
        host_root = Path(source)
        if not container_root.is_absolute() or not host_root.is_absolute():
            continue
        mappings.append(
            ContainerPathMapping(
                container_root=container_root,
                host_root=host_root,
            )
        )

    mappings.sort(key=lambda item: len(item.container_root.parts), reverse=True)
    result = tuple(mappings)
    _mount_cache = (result, now)
    return result


def _current_container_id() -> str | None:
    hostname = (os.environ.get("HOSTNAME") or "").strip()
    if re.fullmatch(r"[0-9a-f]{12,64}", hostname):
        return hostname

    cgroup = Path("/proc/self/cgroup")
    if not cgroup.exists():
        return None

    try:
        for line in cgroup.read_text(encoding="utf-8").splitlines():
            token = line.rsplit("/", 1)[-1].strip()
            if re.fullmatch(r"[0-9a-f]{12,64}", token):
                return token
            if token.endswith(".scope"):
                token = token.removesuffix(".scope")
                if token.startswith("docker-"):
                    token = token.removeprefix("docker-")
                if re.fullmatch(r"[0-9a-f]{12,64}", token):
                    return token
    except OSError:
        return None
    return None

"""Filesystem paths whose readable contents grant external write authority."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import settings


def sensitive_capability_paths() -> tuple[Path, ...]:
    home = Path.home()
    candidates = [
        Path(settings.state_root),
        Path("/proc"),
        Path("/dev/fd"),
        Path("/var/run/docker.sock"),
        Path("/run/docker.sock"),
        home / ".ssh",
        home / ".aws",
        home / ".azure",
        home / ".kube",
        home / ".docker",
        home / ".config" / "gcloud",
        home / ".config" / "gh",
        home / ".git-credentials",
        home / ".netrc",
    ]
    better_auth_db_path = str(settings.better_auth_db_path or "").strip()
    if better_auth_db_path:
        candidates.append(Path(better_auth_db_path))
    try:
        database_url = make_url(settings.database_url)
    except Exception:
        database_url = None
    if (
        database_url is not None
        and database_url.get_backend_name() == "sqlite"
        and database_url.database
        and database_url.database != ":memory:"
    ):
        candidates.append(Path(database_url.database))
    for name in (
        "DOCKER_CONFIG",
        "AWS_SHARED_CREDENTIALS_FILE",
        "AWS_CONFIG_FILE",
        "AZURE_CONFIG_DIR",
        "CLOUDSDK_CONFIG",
        "GH_CONFIG_DIR",
        "NETRC",
        "SSH_AUTH_SOCK",
    ):
        value = os.environ.get(name, "").strip()
        if value:
            candidates.append(Path(value))
    kubeconfig = os.environ.get("KUBECONFIG", "")
    candidates.extend(
        Path(item)
        for item in kubeconfig.split(os.pathsep)
        if item.strip()
    )
    docker_socket = str(getattr(settings, "docker_socket", "") or "")
    if docker_socket.startswith("unix://"):
        candidates.append(Path(docker_socket.removeprefix("unix://")))
    docker_host = os.environ.get("DOCKER_HOST", "")
    if docker_host.startswith("unix://"):
        candidates.append(Path(docker_host.removeprefix("unix://")))
    result: list[Path] = []
    for candidate in candidates:
        resolved = candidate.expanduser().resolve(strict=False)
        if resolved not in result:
            result.append(resolved)
    return tuple(result)


def require_safe_workspace_root(root: Path) -> Path:
    """Reject workspaces that contain, or live inside, ambient capabilities."""

    resolved = root.expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise RuntimeError(f"sandbox workspace root is not a directory: {resolved}")
    if resolved == Path("/") or any(
        _is_relative_to(resolved, sensitive)
        or _is_relative_to(sensitive, resolved)
        for sensitive in sensitive_capability_paths()
    ):
        raise RuntimeError(
            f"sandbox workspace overlaps a protected capability path: {resolved}"
        )
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

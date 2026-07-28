from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def _source_compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def _compose(filename: str) -> dict:
    return yaml.safe_load((ROOT / filename).read_text(encoding="utf-8"))


def _render_compose(*filenames: str, env_file: str | None = None) -> dict:
    command = ["docker", "compose"]
    if env_file is not None:
        command.extend(["--env-file", env_file])
    for filename in filenames:
        command.extend(["-f", filename])
    command.extend(["config", "--format", "yaml"])

    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return yaml.safe_load(result.stdout)


def _docker_socket_mount(backend: dict) -> dict:
    return next(
        volume
        for volume in backend["volumes"]
        if isinstance(volume, dict) and volume.get("target") == "/var/run/docker.sock"
    )


def test_source_compose_uses_optional_env_file() -> None:
    compose = _source_compose()

    for service_name in ("backend", "frontend"):
        assert compose["services"][service_name]["env_file"] == [
            {"path": ".env", "required": False}
        ]


def test_source_compose_defaults_to_loopback_dev_auth() -> None:
    compose = _source_compose()
    backend = compose["services"]["backend"]
    frontend = compose["services"]["frontend"]

    assert backend["ports"] == [
        "${BIOINFOFLOW_BIND_HOST:-127.0.0.1}:${BACKEND_PORT:-8000}:8000"
    ]
    assert frontend["ports"] == [
        "${BIOINFOFLOW_BIND_HOST:-127.0.0.1}:${FRONTEND_PORT:-3000}:3000"
    ]
    assert backend["environment"]["AUTH_MODE"] == "${AUTH_MODE:-}"
    assert backend["environment"]["AUTH_ENABLED"] == "${AUTH_ENABLED:-false}"
    assert frontend["environment"]["AUTH_MODE"] == "${AUTH_MODE:-}"
    assert frontend["environment"]["AUTH_ENABLED"] == "${AUTH_ENABLED:-false}"
    assert frontend["build"]["args"]["NEXT_PUBLIC_AUTH_MODE"] == "${AUTH_MODE:-}"
    assert (
        frontend["build"]["args"]["NEXT_PUBLIC_AUTH_ENABLED"]
        == "${AUTH_ENABLED:-false}"
    )


@pytest.mark.parametrize(
    "filename",
    ["docker-compose.yml", "docker-compose.local.yml", "docker-compose.prod.yml"],
)
def test_compose_backends_disable_seccomp_without_privileged_escalation(
    filename: str,
) -> None:
    backend = _compose(filename)["services"]["backend"]

    assert backend["security_opt"] == ["seccomp:unconfined"]
    assert backend.get("privileged", False) is False
    assert "SYS_ADMIN" not in backend.get("cap_add", [])


@pytest.mark.parametrize(
    ("filename", "env_file"),
    [
        ("docker-compose.yml", None),
        ("docker-compose.local.yml", "scripts/tests/fixtures/local.env"),
        ("docker-compose.prod.yml", None),
    ],
)
def test_compose_backends_use_the_writable_host_socket_contract(
    filename: str,
    env_file: str | None,
) -> None:
    raw_backend = _compose(filename)["services"]["backend"]
    raw_mount = _docker_socket_mount(raw_backend)

    assert "DOCKER_SOCKET_PATH" in raw_mount["source"]
    assert raw_mount["read_only"] is False
    assert raw_backend["environment"]["DOCKER_SOCKET"] == (
        "unix:///var/run/docker.sock"
    )

    rendered_backend = _render_compose(filename, env_file=env_file)["services"][
        "backend"
    ]
    rendered_mount = _docker_socket_mount(rendered_backend)

    assert rendered_mount["source"] == "/var/run/docker.sock"
    assert rendered_mount.get("read_only", False) is False
    assert rendered_backend["environment"]["DOCKER_SOCKET"] == (
        "unix:///var/run/docker.sock"
    )


def test_gpu_override_preserves_backend_socket_and_seccomp_contracts() -> None:
    backend = _render_compose("docker-compose.yml", "docker-compose.gpu.yml")[
        "services"
    ]["backend"]
    socket_mount = _docker_socket_mount(backend)

    assert backend["security_opt"] == ["seccomp:unconfined"]
    assert backend.get("privileged", False) is False
    assert "SYS_ADMIN" not in backend.get("cap_add", [])
    assert socket_mount["source"] == "/var/run/docker.sock"
    assert socket_mount.get("read_only", False) is False
    assert backend["environment"]["DOCKER_SOCKET"] == "unix:///var/run/docker.sock"


def test_docker_guide_explains_seccomp_tradeoff() -> None:
    guide = (ROOT / "docs" / "getting-started" / "docker.md").read_text(
        encoding="utf-8"
    )
    normalized_guide = " ".join(guide.split())

    assert "disables Docker's seccomp syscall filter" in normalized_guide
    assert "validated custom seccomp profile" in normalized_guide


def test_published_image_compose_fails_closed_to_personal_auth() -> None:
    compose = yaml.safe_load(
        (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    )

    assert compose["services"]["backend"]["environment"]["AUTH_MODE"] == "personal"
    assert compose["services"]["frontend"]["environment"]["AUTH_MODE"] == "personal"


def test_env_example_is_optional_local_customization() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "AUTH_MODE=dev" in env_example
    assert "# AUTH_BOOTSTRAP_OWNER_EMAIL=" in env_example
    assert "# AUTH_BOOTSTRAP_OWNER_PASSWORD=" in env_example
    assert "# ANTHROPIC_API_KEY=" in env_example
    assert "BIOINFOFLOW_BIND_HOST=127.0.0.1" in env_example
    assert "# BIOINFOFLOW_BIND_HOST=0.0.0.0" in env_example


def test_backend_env_example_scopes_compose_socket_path_to_repo_root() -> None:
    env_example = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")

    assert "# DOCKER_SOCKET_PATH=" not in env_example
    assert "repo-root `.env`" in env_example
    assert "shell that starts Docker Compose" in env_example
    assert "# DOCKER_SOCKET=unix:///var/run/docker.sock" in env_example


def test_security_docs_describe_the_bash_only_docker_socket_exception() -> None:
    security = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")
    normalized_security = " ".join(security.split())

    assert (
        "explicitly denying BioinfoFlow product source, internal state databases, and the Docker socket"
        not in normalized_security
    )
    assert "Bash-only exception" in normalized_security
    assert "Bubblewrap bind" in normalized_security
    assert "Seatbelt exact network-outbound rule" in normalized_security
    assert "full Docker daemon authority" in normalized_security


def test_local_image_compose_uses_the_shared_bind_host_override() -> None:
    compose = yaml.safe_load(
        (ROOT / "docker-compose.local.yml").read_text(encoding="utf-8")
    )

    assert compose["services"]["backend"]["ports"] == [
        "${BIOINFOFLOW_BIND_HOST:-127.0.0.1}:${BACKEND_PORT:-8000}:8000"
    ]
    assert compose["services"]["frontend"]["ports"] == [
        "${BIOINFOFLOW_BIND_HOST:-127.0.0.1}:${FRONTEND_PORT:-3000}:3000"
    ]


def test_frontend_image_defaults_to_dev_auth_without_build_args() -> None:
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")

    assert "ARG NEXT_PUBLIC_AUTH_MODE=dev" in dockerfile

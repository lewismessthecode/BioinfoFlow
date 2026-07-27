from __future__ import annotations

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def _source_compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def _compose(filename: str) -> dict:
    return yaml.safe_load((ROOT / filename).read_text(encoding="utf-8"))


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

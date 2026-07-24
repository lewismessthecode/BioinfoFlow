from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _source_compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


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

    assert backend["ports"] == ["127.0.0.1:${BACKEND_PORT:-8000}:8000"]
    assert frontend["ports"] == ["127.0.0.1:${FRONTEND_PORT:-3000}:3000"]
    assert backend["environment"]["AUTH_MODE"] == "${AUTH_MODE:-dev}"
    assert frontend["environment"]["AUTH_MODE"] == "${AUTH_MODE:-dev}"
    assert frontend["build"]["args"]["NEXT_PUBLIC_AUTH_MODE"] == "${AUTH_MODE:-dev}"


def test_env_example_is_optional_local_customization() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "AUTH_MODE=dev" in env_example
    assert "# AUTH_BOOTSTRAP_OWNER_EMAIL=" in env_example
    assert "# AUTH_BOOTSTRAP_OWNER_PASSWORD=" in env_example
    assert "# ANTHROPIC_API_KEY=" in env_example


def test_frontend_image_defaults_to_dev_auth_without_build_args() -> None:
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")

    assert "ARG NEXT_PUBLIC_AUTH_MODE=dev" in dockerfile

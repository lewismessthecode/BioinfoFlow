from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "backend/scripts/docker-entrypoint.sh"
DOCKERFILE = ROOT / "backend/Dockerfile"
COMPOSE = ROOT / "docker-compose.prod.yml"


def assert_contains(text: str, needle: str) -> None:
    if needle not in text:
        raise AssertionError(f"Expected to find {needle!r} in:\n{text}")


def assert_not_contains(text: str, needle: str) -> None:
    if needle in text:
        raise AssertionError(f"Did not expect to find {needle!r} in:\n{text}")


def test_entrypoint_uses_installed_venv_tools() -> None:
    text = ENTRYPOINT.read_text()
    assert_contains(text, "/app/.venv/bin/alembic upgrade head")
    assert_not_contains(text, "uv run alembic upgrade head")


def test_dockerfile_runs_uvicorn_without_uv_run() -> None:
    text = DOCKERFILE.read_text()
    assert_contains(text, 'ENV PATH="/app/.venv/bin:$PATH"')
    assert_contains(text, 'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]')
    assert_not_contains(text, 'CMD ["uv", "run", "uvicorn"')


def test_prod_healthcheck_grace_period_is_extended() -> None:
    text = COMPOSE.read_text()
    assert_contains(text, "start_period: 120s")


if __name__ == "__main__":
    tests = [
        test_entrypoint_uses_installed_venv_tools,
        test_dockerfile_runs_uvicorn_without_uv_run,
        test_prod_healthcheck_grace_period_is_extended,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")

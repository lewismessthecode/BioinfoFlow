from __future__ import annotations

from pathlib import Path


def _dockerfile() -> str:
    return (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(
        encoding="utf-8"
    )


def test_backend_dockerfile_installs_app_before_final_uv_sync():
    """`COPY app app` must precede the final `uv sync` that installs the
    project. The engine spawns miniwdl via `python -m app.engine._miniwdl_entry`,
    so the venv python inside the image must be able to import the `app`
    package — otherwise the subprocess fails before registering our
    container backend and task containers miss the identity mounts.
    """
    dockerfile = _dockerfile()

    copy_app_index = dockerfile.index("COPY app app")
    # The deps-only prep layer uses `--no-install-project`; the project
    # itself gets installed by the final `uv sync --frozen --no-dev` (no
    # `--no-install-project` flag). `rfind` lands on that final invocation.
    final_sync_index = dockerfile.rfind("uv sync --frozen --no-dev")
    assert final_sync_index != -1, "expected a project-install `uv sync` step"
    assert (
        "--no-install-project"
        not in dockerfile[
            final_sync_index : final_sync_index + len("uv sync --frozen --no-dev") + 30
        ]
    ), "the final uv sync must install the project, not just deps"

    assert copy_app_index < final_sync_index, (
        "backend/Dockerfile must copy the app package before the final "
        "`uv sync` installs the project, otherwise `python -m "
        "app.engine._miniwdl_entry` cannot import the bioinfoflow backend "
        "class and task containers lose their identity mounts."
    )


def test_backend_dockerfile_exports_app_pythonpath_for_workspace_subprocesses():
    """Engine subprocesses run with the user workspace as cwd, not `/app`.

    The production image strips source to legacy pyc files under `/app/app`,
    then spawns miniwdl with `/app/.venv/bin/python -m app.engine._miniwdl_entry`.
    Setting PYTHONPATH makes that module import independent of the current
    workspace and the exact project-install mode used by uv.
    """
    dockerfile = _dockerfile()

    assert 'PYTHONPATH="/app"' in dockerfile


def test_backend_dockerfile_keeps_project_venv_first_after_installing_uv():
    """The later uv PATH declaration must not hide the project virtualenv.

    Docker expands repeated ``ENV PATH=...`` declarations in a way that can
    leave only the base image PATH in the final container.  The entrypoint
    invokes ``python`` and ``uvicorn`` by name, so the final declaration must
    explicitly keep ``/app/.venv/bin`` ahead of the system interpreter.
    """
    dockerfile = _dockerfile()

    assert 'ENV PATH="/root/.local/bin:/app/.venv/bin:$PATH"' in dockerfile


def test_backend_dockerfile_installs_btop_for_scheduler_monitor():
    """The btop WebSocket spawns inside the backend container.

    Installing btop on the Compose host cannot satisfy that process lookup, so
    the release image must carry the binary itself.
    """
    dockerfile = _dockerfile()

    package_block = dockerfile.split("apt-get install -y --no-install-recommends", 1)[1]
    package_block = package_block.split("&&", 1)[0]
    assert "btop" in package_block.split(), (
        "backend/Dockerfile must install btop because /scheduler/btop/ws "
        "spawns the monitor inside the backend container"
    )


def test_backend_image_excludes_retired_agent_browser_runtime():
    dockerfile = _dockerfile()

    assert "agent-browser" not in dockerfile
    assert "AGENT_BROWSER_EXECUTABLE_PATH" not in dockerfile
    assert "chromium" not in dockerfile


def test_backend_dependencies_exclude_retired_harness_packages():
    backend_root = Path(__file__).resolve().parents[1]
    pyproject = (backend_root / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (backend_root / "uv.lock").read_text(encoding="utf-8")

    for retired in ("duckduckgo-search", "hermes-agent"):
        assert retired not in pyproject
        assert f'name = "{retired}"' not in lockfile

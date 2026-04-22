from __future__ import annotations

from pathlib import Path


def test_backend_dockerfile_installs_app_before_final_uv_sync():
    """`COPY app app` must precede the final `uv sync` that installs the
    project. The engine spawns miniwdl via `python -m app.engine._miniwdl_entry`,
    so the venv python inside the image must be able to import the `app`
    package — otherwise the subprocess fails before registering our
    container backend and task containers miss the identity mounts.
    """
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(
        encoding="utf-8"
    )

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

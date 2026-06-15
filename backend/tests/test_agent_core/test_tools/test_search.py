from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings
from app.services.agent_core.tools.search import GlobTool, GrepTool
from app.services.agent_core.tools.specs import AgentToolContext
from app.utils.exceptions import BadRequestError
from app.utils.exceptions import PermissionDeniedError


def _context() -> AgentToolContext:
    return AgentToolContext(db=None, workspace_id="w", user_id="dev", session_id="s", turn_id="t")  # type: ignore[arg-type]


@pytest.fixture()
def search_dir():
    base = Path(settings.bioinfoflow_home).expanduser().resolve() / "agent_search_test"
    base.mkdir(parents=True, exist_ok=True)
    (base / "alpha.txt").write_text("hello marker world\nsecond line\n", encoding="utf-8")
    (base / "beta.txt").write_text("nothing here\n", encoding="utf-8")
    yield base
    for child in base.glob("*"):
        child.unlink()
    base.rmdir()


@pytest.mark.asyncio
async def test_grep_finds_matches_within_allowed_root(search_dir):
    result = await GrepTool().run(
        {"pattern": "marker", "path": str(search_dir)}, _context()
    )
    assert result["count"] == 1
    match = result["matches"][0]
    assert match["path"].endswith("alpha.txt")
    assert match["line_number"] == 1
    assert "marker" in match["line"]


@pytest.mark.asyncio
async def test_grep_rejects_path_outside_allowed_roots():
    with pytest.raises(PermissionDeniedError):
        await GrepTool().run({"pattern": "x", "path": "/etc"}, _context())


@pytest.mark.asyncio
async def test_grep_rejects_parent_traversal_glob(search_dir, monkeypatch):
    monkeypatch.setattr("app.services.agent_core.tools.search.grep.shutil.which", lambda _name: None)

    with pytest.raises(BadRequestError):
        await GrepTool().run(
            {"pattern": "marker", "path": str(search_dir), "glob": "../*"},
            _context(),
        )


@pytest.mark.asyncio
async def test_glob_lists_files_within_allowed_root(search_dir):
    result = await GlobTool().run(
        {"pattern": "*.txt", "path": str(search_dir)}, _context()
    )
    assert result["count"] == 2
    names = sorted(Path(p).name for p in result["paths"])
    assert names == ["alpha.txt", "beta.txt"]


@pytest.mark.asyncio
async def test_glob_rejects_absolute_pattern(search_dir):
    with pytest.raises(Exception):
        await GlobTool().run({"pattern": "/etc/*", "path": str(search_dir)}, _context())


@pytest.mark.asyncio
async def test_glob_rejects_parent_traversal_pattern(search_dir):
    with pytest.raises(BadRequestError):
        await GlobTool().run({"pattern": "../*", "path": str(search_dir)}, _context())

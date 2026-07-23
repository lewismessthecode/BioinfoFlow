from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services.agent_core.tools import files as file_tools
from app.utils.exceptions import BadRequestError


def _tool():
    tool_type = getattr(file_tools, "ApplyPatchTool", None)
    assert tool_type is not None, "files.apply_patch must be implemented"
    return tool_type()


def _context():
    return SimpleNamespace()


@pytest.mark.asyncio
async def test_apply_patch_supports_create_replace_and_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    monkeypatch.setattr(settings, "repo_root", str(tmp_path))
    replace_path = tmp_path / "replace.txt"
    delete_path = tmp_path / "delete.txt"
    replace_path.write_text("before\n", encoding="utf-8")
    delete_path.write_text("remove me\n", encoding="utf-8")

    result = await _tool().run(
        {
            "operations": [
                {
                    "op": "replace",
                    "path": "replace.txt",
                    "old_text": "before",
                    "new_text": "after",
                },
                {"op": "create", "path": "created.txt", "content": "created\n"},
                {"op": "delete", "path": "delete.txt"},
            ]
        },
        _context(),
    )

    assert replace_path.read_text(encoding="utf-8") == "after\n"
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "created\n"
    assert not delete_path.exists()
    assert result == {
        "operations": [
            {"op": "replace", "path": str(replace_path), "replacements": 1},
            {"op": "create", "path": str(tmp_path / "created.txt"), "bytes_written": 8},
            {"op": "delete", "path": str(delete_path)},
        ]
    }


@pytest.mark.asyncio
async def test_apply_patch_validates_every_operation_before_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    monkeypatch.setattr(settings, "repo_root", str(tmp_path))
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("before\n", encoding="utf-8")
    second.write_text("unchanged\n", encoding="utf-8")

    with pytest.raises(BadRequestError, match="old_text was not found"):
        await _tool().run(
            {
                "operations": [
                    {
                        "op": "replace",
                        "path": "first.txt",
                        "old_text": "before",
                        "new_text": "after",
                    },
                    {
                        "op": "replace",
                        "path": "second.txt",
                        "old_text": "missing",
                        "new_text": "changed",
                    },
                ]
            },
            _context(),
        )

    assert first.read_text(encoding="utf-8") == "before\n"
    assert second.read_text(encoding="utf-8") == "unchanged\n"


@pytest.mark.asyncio
async def test_apply_patch_rejects_conflicting_resolved_paths_before_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    monkeypatch.setattr(settings, "repo_root", str(tmp_path))
    target = tmp_path / "target.txt"
    target.write_text("before\n", encoding="utf-8")

    with pytest.raises(BadRequestError, match="same path"):
        await _tool().run(
            {
                "operations": [
                    {
                        "op": "replace",
                        "path": "target.txt",
                        "old_text": "before",
                        "new_text": "after",
                    },
                    {"op": "delete", "path": str(target)},
                ]
            },
            _context(),
        )

    assert target.read_text(encoding="utf-8") == "before\n"


@pytest.mark.asyncio
async def test_apply_patch_rejects_create_over_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    monkeypatch.setattr(settings, "repo_root", str(tmp_path))
    target = tmp_path / "existing.txt"
    target.write_text("keep\n", encoding="utf-8")

    with pytest.raises(BadRequestError, match="already exists"):
        await _tool().run(
            {
                "operations": [
                    {"op": "create", "path": "existing.txt", "content": "replace\n"}
                ]
            },
            _context(),
        )

    assert target.read_text(encoding="utf-8") == "keep\n"


@pytest.mark.asyncio
async def test_apply_patch_rolls_back_prior_mutation_when_later_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "bioinfoflow_home", str(tmp_path))
    monkeypatch.setattr(settings, "repo_root", str(tmp_path))
    target = tmp_path / "target.txt"
    target.write_text("before\n", encoding="utf-8")
    original_write_text = Path.write_text
    calls = 0

    def fail_second_write(self, data, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated disk failure")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_second_write)

    with pytest.raises(RuntimeError, match="file patch apply failed"):
        await _tool().run(
            {
                "operations": [
                    {"op": "create", "path": "created.txt", "content": "new\n"},
                    {
                        "op": "replace",
                        "path": "target.txt",
                        "old_text": "before",
                        "new_text": "after",
                    },
                ]
            },
            _context(),
        )

    assert not (tmp_path / "created.txt").exists()
    assert target.read_text(encoding="utf-8") == "before\n"

"""Tests for GET /system/directories endpoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_list_directories_returns_envelope(async_client, tmp_path):
    """GET /system/directories returns a standard API envelope."""
    sub = tmp_path / "alpha"
    sub.mkdir()

    resp = await async_client.get(
        "/api/v1/system/directories", params={"path": str(tmp_path)}
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["success"] is True
    assert "data" in body
    assert "meta" in body


@pytest.mark.asyncio
async def test_list_directories_returns_subdirectories(async_client, tmp_path):
    """Endpoint lists only directories, not files."""
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "dir_b").mkdir()
    (tmp_path / "file.txt").write_text("hello")

    resp = await async_client.get(
        "/api/v1/system/directories", params={"path": str(tmp_path)}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["path"] == str(tmp_path)
    names = [d["name"] for d in data["directories"]]
    assert "dir_a" in names
    assert "dir_b" in names
    assert "file.txt" not in names


@pytest.mark.asyncio
async def test_list_directories_sorted_alphabetically(async_client, tmp_path):
    """Directories are returned in alphabetical order."""
    for name in ["charlie", "alpha", "bravo"]:
        (tmp_path / name).mkdir()

    resp = await async_client.get(
        "/api/v1/system/directories", params={"path": str(tmp_path)}
    )
    data = resp.json()["data"]
    names = [d["name"] for d in data["directories"]]
    # Filter to only the directories we created (tmp_path may contain other fixtures)
    created = [n for n in names if n in {"alpha", "bravo", "charlie"}]
    assert created == ["alpha", "bravo", "charlie"]


@pytest.mark.asyncio
async def test_list_directories_includes_parent(async_client, tmp_path):
    """Response includes the parent directory path."""
    child = tmp_path / "subdir"
    child.mkdir()

    resp = await async_client.get(
        "/api/v1/system/directories", params={"path": str(child)}
    )
    data = resp.json()["data"]
    assert data["parent"] == str(tmp_path)


@pytest.mark.asyncio
async def test_list_directories_hides_hidden_by_default(async_client, tmp_path):
    """Hidden directories (starting with .) are excluded by default."""
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible").mkdir()

    resp = await async_client.get(
        "/api/v1/system/directories", params={"path": str(tmp_path)}
    )
    names = [d["name"] for d in resp.json()["data"]["directories"]]
    assert "visible" in names
    assert ".hidden" not in names


@pytest.mark.asyncio
async def test_list_directories_shows_hidden_when_requested(async_client, tmp_path):
    """show_hidden=true includes hidden directories."""
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible").mkdir()

    resp = await async_client.get(
        "/api/v1/system/directories",
        params={"path": str(tmp_path), "show_hidden": "true"},
    )
    names = [d["name"] for d in resp.json()["data"]["directories"]]
    assert ".hidden" in names
    assert "visible" in names


@pytest.mark.asyncio
async def test_list_directories_blocklisted_path(async_client):
    """Blocklisted paths return 403."""
    resp = await async_client.get(
        "/api/v1/system/directories", params={"path": "/proc"}
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["success"] is False


@pytest.mark.asyncio
async def test_list_directories_not_found(async_client):
    """Non-existent path returns 404."""
    missing = Path.home() / ".bioinfoflow-definitely-missing-directory"
    resp = await async_client.get(
        "/api/v1/system/directories",
        params={"path": str(missing)},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False


@pytest.mark.asyncio
async def test_list_directories_rejects_paths_outside_allowed_roots(async_client):
    """Absolute paths outside the configured local roots return 403."""
    resp = await async_client.get("/api/v1/system/directories", params={"path": "/etc"})
    assert resp.status_code == 403
    body = resp.json()
    assert body["success"] is False


@pytest.mark.asyncio
async def test_list_directories_permission_error(async_client, tmp_path):
    """Permission errors return 403."""
    with patch("app.api.v1.system.os.scandir", side_effect=PermissionError("nope")):
        resp = await async_client.get(
            "/api/v1/system/directories", params={"path": str(tmp_path)}
        )
    assert resp.status_code == 403
    body = resp.json()
    assert body["success"] is False


@pytest.mark.asyncio
async def test_list_directories_tilde_resolves_to_home(async_client):
    """Path '~' resolves to the user's home directory."""
    resp = await async_client.get("/api/v1/system/directories", params={"path": "~"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["path"] == str(Path.home())


@pytest.mark.asyncio
async def test_list_directories_each_entry_has_full_path(async_client, tmp_path):
    """Each directory entry includes the full absolute path."""
    (tmp_path / "mydir").mkdir()

    resp = await async_client.get(
        "/api/v1/system/directories", params={"path": str(tmp_path)}
    )
    entries = resp.json()["data"]["directories"]
    # Find our specific entry (tmp_path may contain fixture dirs)
    mydir_entries = [e for e in entries if e["name"] == "mydir"]
    assert len(mydir_entries) == 1
    assert mydir_entries[0]["path"] == str(tmp_path / "mydir")

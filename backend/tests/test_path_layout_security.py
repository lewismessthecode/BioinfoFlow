from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.path_layout import resolve_asset, safe_join


def test_safe_join_rejects_parent_directory_segments(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(PermissionError, match="path escapes source"):
        safe_join(root, "reads/../sample.fastq.gz", escape_message="path escapes source")


def test_safe_join_rejects_absolute_paths_even_inside_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    target = root / "sample.fastq.gz"

    with pytest.raises(PermissionError, match="path escapes source"):
        safe_join(root, str(target), escape_message="path escapes source")


def test_resolve_results_asset_rejects_traversal_run_id(tmp_path, monkeypatch):
    monkeypatch.setattr("app.path_layout.settings.bioinfoflow_home", str(tmp_path))

    project = SimpleNamespace(id="project-1", storage_mode="managed")

    with pytest.raises(ValueError, match="invalid run id"):
        resolve_asset(project, "asset://results/../report.txt")

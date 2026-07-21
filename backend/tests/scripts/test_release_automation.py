from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


def read_repo_file(path: str) -> str:
    candidate = REPO_ROOT / path
    assert candidate.is_file(), f"missing release file: {path}"
    return candidate.read_text(encoding="utf-8")


def test_release_version_is_synchronized() -> None:
    version = read_repo_file("version.txt").strip()
    backend = tomllib.loads(read_repo_file("backend/pyproject.toml"))
    backend_lock = tomllib.loads(read_repo_file("backend/uv.lock"))
    frontend = json.loads(read_repo_file("frontend/package.json"))
    openapi = json.loads(read_repo_file("docs/contracts/openapi-v1.json"))
    runtime_version = Settings.model_fields["app_version"].get_default()

    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert backend["project"]["version"] == version
    locked_backend = next(
        package
        for package in backend_lock["package"]
        if package["name"] == "bioinfoflow-backend"
    )
    assert locked_backend["version"] == version
    assert frontend["version"] == version
    assert openapi["info"]["version"] == version
    assert runtime_version == version


def test_release_please_uses_numeric_pre_major_versions() -> None:
    config = json.loads(read_repo_file("release-please-config.json"))
    manifest = json.loads(read_repo_file(".release-please-manifest.json"))
    package = config["packages"]["."]

    assert config["bootstrap-sha"] == "ffae4af3c28a5285220cac59db389ca84cac307c"
    assert manifest["."] == "0.1.0"
    assert package["release-type"] == "simple"
    assert package["package-name"] == "bioinfoflow"
    assert package["include-v-in-tag"] is False
    assert package["include-component-in-tag"] is False
    assert package["bump-minor-pre-major"] is True
    assert package["bump-patch-for-minor-pre-major"] is False
    assert "pull-request-title-pattern" not in package

    extra_files = {
        (entry["type"], entry["path"], entry.get("jsonpath"))
        for entry in package["extra-files"]
    }
    assert ("toml", "backend/pyproject.toml", "$.project.version") in extra_files
    assert (
        "generic",
        "backend/uv.lock",
        None,
    ) in extra_files
    assert (
        'version = "0.1.0"  # x-release-please-version'
        in read_repo_file("backend/uv.lock")
    )
    assert ("json", "frontend/package.json", "$.version") in extra_files
    assert ("generic", "backend/app/config.py", None) in extra_files
    assert (
        "json",
        "docs/contracts/openapi-v1.json",
        "$.info.version",
    ) in extra_files


def test_changelog_starts_with_curated_initial_release() -> None:
    changelog = read_repo_file("CHANGELOG.md")

    assert "## [0.1.0] - 2026-07-21" in changelog
    assert "first formally tracked release" in changelog
    assert "### Highlights" in changelog
    assert "#1" not in changelog
    assert "#146" not in changelog


def test_main_container_workflow_only_publishes_development_tags() -> None:
    workflow = read_repo_file(".github/workflows/container-release.yml")

    assert ":main" in workflow
    assert ":sha-${{ needs.detect.outputs.short_sha }}" in workflow
    assert ":latest" not in workflow


def test_formal_release_workflow_publishes_numeric_aliases() -> None:
    workflow = read_repo_file(".github/workflows/release-please.yml")

    assert "googleapis/release-please-action@v4" in workflow
    assert "actions: write" in workflow
    assert 'gh workflow run ci.yml --ref "$head_branch"' in workflow
    assert "publish_version:" in workflow
    assert "include-v-in-tag" not in workflow
    assert ":${{ needs.release.outputs.version }}" in workflow
    assert ":${{ needs.release.outputs.major_minor }}" in workflow
    assert ":${{ needs.release.outputs.major }}" in workflow
    assert ":latest" in workflow

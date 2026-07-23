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

    assert "type=raw,value=main,enable=${{ github.ref == 'refs/heads/main' }}" in workflow
    assert "type=sha,prefix=sha-,enable=${{ github.ref == 'refs/heads/main' }}" in workflow
    assert (
        "type=raw,value=latest,enable=${{ inputs.release_version != '' }}"
        in workflow
    )
    assert "type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}" not in workflow


def test_formal_release_workflow_publishes_numeric_aliases() -> None:
    workflow = read_repo_file(".github/workflows/release-please.yml")
    installer_workflow = read_repo_file(".github/workflows/release.yml")
    container_workflow = read_repo_file(".github/workflows/container-release.yml")

    assert "googleapis/release-please-action@v4" in workflow
    assert "actions: write" in workflow
    assert "secrets.RELEASE_PLEASE_TOKEN || secrets.GITHUB_TOKEN" in workflow
    assert 'gh workflow run ci.yml --ref "$head_branch"' in workflow
    assert "publish_version:" in workflow
    assert "include-v-in-tag" not in workflow
    assert (
        'gh workflow run release.yml --ref "$tag_name" '
        '-f release_version="$version"'
        in workflow
    )
    assert "publish-images:" not in workflow

    assert "release_version:" in installer_workflow
    assert "^[0-9]+\\.[0-9]+\\.[0-9]+$" in installer_workflow
    assert "release_version: ${{ needs.resolve.outputs.version }}" in installer_workflow
    assert "release_major_minor: ${{ needs.resolve.outputs.major_minor }}" in installer_workflow
    assert "release_major: ${{ needs.resolve.outputs.major }}" in installer_workflow

    assert "type=raw,value=${{ inputs.release_version }}" in container_workflow
    assert "type=raw,value=${{ inputs.release_major_minor }}" in container_workflow
    assert "type=raw,value=${{ inputs.release_major }}" in container_workflow
    assert "type=raw,value=latest,enable=${{ inputs.release_version != '' }}" in container_workflow


def test_pull_request_delivery_is_explicit_and_strict() -> None:
    configuration = read_repo_file("scripts/github/configure-repo.sh")
    release_workflow = read_repo_file(".github/workflows/release-please.yml")

    assert '"strict": true' in configuration
    assert '"approval_policy": "first_time_contributors_new_to_github"' in configuration
    assert '"can_approve_pull_request_reviews": false' in configuration
    assert not (REPO_ROOT / ".github/workflows/pr-automation.yml").exists()
    assert not (REPO_ROOT / ".github/workflows/approve-trusted-workflows.yml").exists()
    assert 'gh workflow run ci.yml --ref "$head_branch"' in release_workflow


def test_ci_delivery_gate_fails_closed_and_covers_release_inputs() -> None:
    workflow = read_repo_file(".github/workflows/ci.yml")

    assert "installer_changed:" in workflow
    assert "workflows_changed:" in workflow
    assert "scripts/install.sh" in workflow
    assert "scripts/tests/" in workflow
    assert "bundled-skills/" in workflow
    assert "docker-compose.local.yml" in workflow
    assert "^\\.github/workflows/" in workflow
    assert "go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.7" in workflow
    assert 'if [ "$BACKEND_CHANGED" = "true" ] && [ "$BACKEND_RESULT" != "success" ]; then' in workflow
    assert 'if [ "$FRONTEND_CHANGED" = "true" ] && [ "$result" != "success" ]; then' in workflow
    assert 'if [ "$DOCKER_CHANGED" = "true" ] && [ "$DOCKER_RESULT" != "success" ]; then' in workflow
    assert 'if [ "$INSTALLER_CHANGED" = "true" ] && [ "$INSTALLER_RESULT" != "success" ]; then' in workflow
    assert 'if [ "$WORKFLOWS_CHANGED" = "true" ] && [ "$WORKFLOWS_RESULT" != "success" ]; then' in workflow


def test_installer_release_uses_only_the_immutable_numeric_tag() -> None:
    workflow = read_repo_file(".github/workflows/release.yml")

    assert '[ "$GITHUB_REF_NAME" != "$version" ]' in workflow
    assert "main recovery workflow" not in workflow
    assert workflow.count("ref: ${{ needs.resolve.outputs.version }}") >= 2
    assert "permissions:\n  contents: read\n" in workflow
    assert "assets:\n    name: attach installer assets" in workflow
    assert "      contents: write" in workflow


def test_release_pull_requests_cannot_be_auto_merged() -> None:
    workflow = read_repo_file(".github/workflows/auto-merge.yml")

    assert "!startsWith(github.event.pull_request.head.ref, 'release-please--')" in workflow


def test_formal_release_packages_and_smoke_tests_native_skills() -> None:
    workflow = read_repo_file(".github/workflows/release.yml")

    assert "bioinfoflow-skills.tar.gz" in workflow
    assert "tar -czf" in workflow
    assert "bundled-skills" in workflow
    assert "sha256sum install.sh docker-compose.local.yml bioinfoflow-skills.tar.gz" in workflow
    assert "dist/bioinfoflow-skills.tar.gz" in workflow
    assert 'test -f "$HOME/.bioinfoflow/skills/ngs-analysis-router/SKILL.md"' in workflow
    assert 'test -f "$HOME/.bioinfoflow/skills/ngs-runtime-env/SKILL.md"' in workflow

    skills_root = REPO_ROOT / "bundled-skills"
    assert (skills_root / "ngs-analysis-router" / "SKILL.md").is_file()
    assert (skills_root / "ngs-runtime-env" / "scripts" / "ngs_preflight.py").is_file()

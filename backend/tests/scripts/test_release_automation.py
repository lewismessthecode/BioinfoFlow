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
    version = read_repo_file("version.txt").strip()

    assert config["bootstrap-sha"] == "ffae4af3c28a5285220cac59db389ca84cac307c"
    assert manifest["."] == version
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
        f'version = "{version}"  # x-release-please-version'
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
    initial_release = changelog.split("## [0.1.0] - 2026-07-21", maxsplit=1)[1]

    assert "## [0.1.0] - 2026-07-21" in changelog
    assert "first formally tracked release" in initial_release
    assert "### Highlights" in initial_release
    assert re.search(r"\[#\d+\]", initial_release) is None


def test_container_workflow_only_publishes_formal_release_tags() -> None:
    workflow = read_repo_file(".github/workflows/container-release.yml")

    assert "workflow_call:" in workflow
    assert "on:\n  push:" not in workflow
    assert "on:\n  workflow_dispatch:" not in workflow
    assert "type=raw,value=main" not in workflow
    assert "type=sha" not in workflow
    assert "type=raw,value=${{ inputs.release_version }}" in workflow
    assert "type=raw,value=${{ inputs.release_major_minor }}" in workflow
    assert "type=raw,value=${{ inputs.release_major }}" in workflow
    assert "type=raw,value=latest" in workflow


def test_formal_release_workflow_publishes_numeric_aliases() -> None:
    workflow = read_repo_file(".github/workflows/release-please.yml")
    installer_workflow = read_repo_file(".github/workflows/release.yml")
    container_workflow = read_repo_file(".github/workflows/container-release.yml")

    assert "googleapis/release-please-action@v5" in workflow
    assert "actions: write" not in workflow
    assert "secrets.RELEASE_PLEASE_TOKEN" in workflow
    assert "secrets.GITHUB_TOKEN" not in workflow
    assert "gh workflow run" not in workflow
    assert "publish_version:" not in workflow
    assert "include-v-in-tag" not in workflow
    assert "uses: ./.github/workflows/release.yml" in workflow
    assert "needs.release-please.outputs.release_created == 'true'" in workflow
    assert "release_version: ${{ needs.release-please.outputs.tag_name }}" in workflow
    assert "publish-images:" not in workflow

    assert "workflow_call:" in installer_workflow
    assert "workflow_dispatch:" in installer_workflow
    assert "release_version:" in installer_workflow
    assert "^[0-9]+\\.[0-9]+\\.[0-9]+$" in installer_workflow
    assert "release_version: ${{ needs.resolve.outputs.version }}" in installer_workflow
    assert "release_major_minor: ${{ needs.resolve.outputs.major_minor }}" in installer_workflow
    assert "release_major: ${{ needs.resolve.outputs.major }}" in installer_workflow

    assert "type=raw,value=${{ inputs.release_version }}" in container_workflow
    assert "type=raw,value=${{ inputs.release_major_minor }}" in container_workflow
    assert "type=raw,value=${{ inputs.release_major }}" in container_workflow
    assert "type=raw,value=latest" in container_workflow


def test_pull_request_delivery_is_explicit_and_strict() -> None:
    configuration = read_repo_file("scripts/github/configure-repo.sh")
    release_workflow = read_repo_file(".github/workflows/release-please.yml")

    assert '"strict": true' in configuration
    assert '"approval_policy": "first_time_contributors_new_to_github"' in configuration
    assert '"can_approve_pull_request_reviews": false' in configuration
    assert not (REPO_ROOT / ".github/workflows/pr-automation.yml").exists()
    assert not (REPO_ROOT / ".github/workflows/approve-trusted-workflows.yml").exists()
    assert not (REPO_ROOT / ".github/workflows/auto-merge.yml").exists()
    assert "secrets.RELEASE_PLEASE_TOKEN" in release_workflow
    assert "gh workflow run ci.yml" not in release_workflow


def test_ci_delivery_gate_fails_closed_and_covers_release_inputs() -> None:
    workflow = read_repo_file(".github/workflows/ci.yml")

    assert "installer_changed:" in workflow
    assert "workflows_changed:" in workflow
    assert "scripts/install.sh" in workflow
    assert "scripts/tests/" in workflow
    assert "bundled-skills/" in workflow
    assert "docker-compose.local.yml" in workflow
    assert "^\\.github/workflows/" in workflow
    assert "go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.12" in workflow
    assert "merge_group:" in workflow
    assert "required:\n    name: CI" in workflow
    assert 'case "${changed}:${result}"' in workflow
    assert 'require_result "$BACKEND_CHANGED" "$BACKEND_RESULT"' in workflow
    assert 'require_result "$FRONTEND_CHANGED" "$FRONTEND_LINT_RESULT"' in workflow
    assert 'require_result "$FRONTEND_CHANGED" "$FRONTEND_BUILD_RESULT"' in workflow
    assert 'require_result "$AGENT_BROWSER_CHANGED" "$AGENT_SHELL_RESULT"' in workflow
    assert 'require_result "$DOCKER_CHANGED" "$DOCKER_RESULT"' in workflow
    assert 'require_result "$INSTALLER_CHANGED" "$INSTALLER_RESULT"' in workflow
    assert 'require_result "$WORKFLOWS_CHANGED" "$WORKFLOWS_RESULT"' in workflow
    assert "frontend/components/bioinfoflow/terminal/" in workflow
    assert "frontend/components/ui/resize-handle\\.tsx" in workflow
    assert "frontend/app/\\(app\\)/layout\\.tsx" in workflow
    assert "backend/app/services/terminal" in workflow
    assert "Upload Agent shell Playwright report and diagnostics" in workflow


def test_installer_release_uses_only_the_immutable_numeric_tag() -> None:
    workflow = read_repo_file(".github/workflows/release.yml")

    assert "workflow_call:" in workflow
    assert "ref: ${{ inputs.release_version }}" in workflow
    assert 'git rev-parse "refs/tags/${version}^{commit}"' in workflow
    assert "GITHUB_REF_NAME" not in workflow
    assert workflow.count("ref: ${{ needs.resolve.outputs.version }}") >= 2
    assert "permissions:\n  contents: read\n" in workflow
    assert "assets:\n    name: attach installer assets" in workflow
    assert "      contents: write" in workflow


def test_release_pull_requests_cannot_be_auto_merged() -> None:
    assert not (REPO_ROOT / ".github/workflows/auto-merge.yml").exists()
    assert "must not be auto-merged" in read_repo_file(
        "docs/development/github-ci-cd.md"
    )


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

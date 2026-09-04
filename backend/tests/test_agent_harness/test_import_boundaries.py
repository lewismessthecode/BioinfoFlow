from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_production_harness_and_agent_api_do_not_import_agent_core() -> None:
    production_files = [
        *sorted((BACKEND_ROOT / "app/services/agent_harness").glob("*.py")),
        *sorted((BACKEND_ROOT / "app/api/v1").glob("agent*.py")),
    ]

    violations = {
        str(path.relative_to(BACKEND_ROOT)): sorted(
            module
            for module in _imports(path)
            if module.startswith("app.services.agent_core")
        )
        for path in production_files
        if any(
            module.startswith("app.services.agent_core") for module in _imports(path)
        )
    }

    assert violations == {}


def test_agent_loop_does_not_depend_on_agent_trace_implementation() -> None:
    loop_path = BACKEND_ROOT / "app/services/agent_harness/loop.py"

    assert not any(
        module.startswith("app.services.agent_trace") for module in _imports(loop_path)
    )


def test_agent_harness_repository_does_not_import_presentation_projectors() -> None:
    """Public redaction belongs to the application/presentation seam, not SQL."""

    repository_path = BACKEND_ROOT / "app/repositories/agent_harness_repo.py"
    imported_modules = _imports(repository_path)

    assert "app.services.agent_harness.projection" not in imported_modules
    assert "app.services.agent_harness.tool_projection" not in imported_modules
    assert "app.services.agent_harness.snapshot" not in imported_modules

    tree = ast.parse(repository_path.read_text(encoding="utf-8"))
    imported_contract_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "app.services.agent_harness.contracts"
        for alias in node.names
    }
    repository_methods = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "SessionSnapshot" not in imported_contract_names
    assert "snapshot" not in repository_methods


def test_only_presentation_mutation_service_calls_presentation_mutations() -> None:
    """Keep all UI-facing durable writes behind the application seam."""

    mutation_names = {
        "update_tool_progress",
        "commit_waiting_interaction",
        "commit_interaction_response",
        "begin_approved_tool_execution",
    }
    allowed = (
        BACKEND_ROOT / "app/services/agent_harness/presentation_mutation_service.py"
    )
    violations: dict[str, list[str]] = {}
    for path in (BACKEND_ROOT / "app").rglob("*.py"):
        if path == allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = sorted(
            {
                node.func.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in mutation_names
                and not (
                    isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "presentation_mutations"
                    and isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == "self"
                )
            }
        )
        if calls:
            violations[str(path.relative_to(BACKEND_ROOT))] = calls

    assert violations == {}


def test_artifact_storage_has_its_own_module_and_assets_is_compatibility_export() -> (
    None
):
    """Attachment ingestion and artifact publication use separate seams."""

    artifact_path = BACKEND_ROOT / "app/services/agent_harness/artifact_service.py"
    assets_path = BACKEND_ROOT / "app/services/agent_harness/assets.py"
    artifact_tree = ast.parse(artifact_path.read_text(encoding="utf-8"))
    assets_tree = ast.parse(assets_path.read_text(encoding="utf-8"))

    artifact_classes = {
        node.name for node in artifact_tree.body if isinstance(node, ast.ClassDef)
    }
    assets_classes = {
        node.name for node in assets_tree.body if isinstance(node, ast.ClassDef)
    }

    assert "AgentHarnessArtifactService" in artifact_classes
    assert "AgentHarnessArtifactService" not in assets_classes

    from app.services.agent_harness.artifact_service import (
        AgentHarnessArtifactService as implementation,
    )
    from app.services.agent_harness.assets import (
        AgentHarnessArtifactService as compatibility_export,
    )

    assert compatibility_export is implementation

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
        BACKEND_ROOT / "app/api/v1/agent.py",
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

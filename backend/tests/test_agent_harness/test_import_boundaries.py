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
        module.startswith("app.services.agent_trace")
        for module in _imports(loop_path)
    )

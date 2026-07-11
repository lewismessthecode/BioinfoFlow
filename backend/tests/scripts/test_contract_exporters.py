from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = BACKEND_ROOT / "scripts"


def _run_exporter(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_ROOT / script_name), *args],
        cwd=BACKEND_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )


def _command_by_path(contract: dict[str, Any], path: str) -> dict[str, Any]:
    pending = [contract["command"]]
    while pending:
        command = pending.pop()
        if command["path"] == path:
            return command
        pending.extend(command["commands"])
    raise AssertionError(f"command path not found: {path}")


def _parameter_by_python_name(
    command: dict[str, Any], python_name: str
) -> dict[str, Any]:
    return next(
        parameter
        for parameter in command["parameters"]
        if parameter["python_name"] == python_name
    )


def test_openapi_export_is_deterministic_and_preserves_full_schema(
    tmp_path: Path,
) -> None:
    from app.main import app

    output_path = tmp_path / "openapi.json"
    result = _run_exporter("export_openapi_contract.py", str(output_path))

    assert result.returncode == 0, result.stderr
    expected_schema = app.openapi()
    expected_text = json.dumps(
        expected_schema,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    assert output_path.read_text() == expected_text

    exported_schema = json.loads(expected_text)
    assert exported_schema == expected_schema
    operation_ids = {
        operation["operationId"]
        for path_item in exported_schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert operation_ids
    assert exported_schema["components"]["schemas"] == expected_schema["components"][
        "schemas"
    ]


def test_cli_export_is_deterministic_and_captures_visible_command_tree(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "cli.json"

    first = _run_exporter("export_cli_contract.py", str(output_path))
    assert first.returncode == 0, first.stderr
    first_text = output_path.read_text()

    second = _run_exporter("export_cli_contract.py", str(output_path))
    assert second.returncode == 0, second.stderr
    assert output_path.read_text() == first_text

    contract = json.loads(first_text)
    assert contract["schema_version"] == 1
    assert contract["command"]["path"] == "bif"
    assert [command["name"] for command in contract["command"]["commands"]] == [
        "agent",
        "config",
        "doctor",
        "events",
        "file",
        "open",
        "project",
        "run",
        "system",
        "workflow",
    ]

    root_project = _parameter_by_python_name(contract["command"], "project")
    assert root_project == {
        "aliases": ["-p"],
        "default": None,
        "help": "Project ID to use (overrides default from config).",
        "kind": "option",
        "name": "--project",
        "python_name": "project",
        "required": False,
    }

    run_submit = _command_by_path(contract, "bif run submit")
    assert run_submit["help"] == "Submit a new run."
    assert _parameter_by_python_name(run_submit, "workflow_id") == {
        "aliases": [],
        "default": None,
        "help": "Workflow ID",
        "kind": "option",
        "name": "--workflow",
        "python_name": "workflow_id",
        "required": True,
    }

    config_set = _command_by_path(contract, "bif config set")
    assert _parameter_by_python_name(config_set, "key") == {
        "aliases": [],
        "default": None,
        "help": "Config key to set",
        "kind": "argument",
        "name": "KEY",
        "python_name": "key",
        "required": True,
    }

    file_upload = _command_by_path(contract, "bif file upload")
    assert _parameter_by_python_name(file_upload, "overwrite")["aliases"] == [
        "--no-overwrite"
    ]


def test_cli_export_does_not_initialize_cli_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.cli import main as cli_main
    from scripts import export_cli_contract

    def fail_if_initialized(*args: object, **kwargs: object) -> None:
        raise AssertionError("CLI runtime was initialized during contract export")

    monkeypatch.setattr(cli_main.ConfigStore, "__init__", fail_if_initialized)

    contract = export_cli_contract.build_contract()

    assert contract["command"]["path"] == "bif"


@pytest.mark.parametrize(
    "script_name",
    ["export_openapi_contract.py", "export_cli_contract.py"],
)
def test_check_mode_detects_contract_drift(
    script_name: str,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "contract.json"
    write_result = _run_exporter(script_name, str(output_path))
    assert write_result.returncode == 0, write_result.stderr

    matching_result = _run_exporter(script_name, "--check", str(output_path))
    assert matching_result.returncode == 0, matching_result.stderr

    output_path.write_text("{}\n")
    drift_result = _run_exporter(script_name, "--check", str(output_path))

    assert drift_result.returncode != 0
    assert "drift" in drift_result.stderr.lower()
    assert str(output_path) in drift_result.stderr

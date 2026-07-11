from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = BACKEND_ROOT / "scripts"


def _run_exporter(
    script_name: str,
    *args: str,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(env_overrides or {})
    return subprocess.run(
        [sys.executable, str(SCRIPTS_ROOT / script_name), *args],
        cwd=BACKEND_ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=env,
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


def _parameter_by_name(command: dict[str, Any], name: str) -> dict[str, Any]:
    return next(
        parameter
        for parameter in command["parameters"]
        if parameter["name"] == name
    )


def test_openapi_export_is_deterministic_and_preserves_full_schema(
    tmp_path: Path,
) -> None:
    from app.config import Settings
    from app.main import app

    output_path = tmp_path / "openapi.json"
    result = _run_exporter("export_openapi_contract.py", str(output_path))

    assert result.returncode == 0, result.stderr
    app_schema = app.openapi()
    expected_schema = deepcopy(app_schema)
    app_name = Settings.model_fields["app_name"].get_default()
    app_version = Settings.model_fields["app_version"].get_default()
    assert isinstance(app_name, str)
    assert isinstance(app_version, str)
    expected_schema["info"]["title"] = f"{app_name} API"
    expected_schema["info"]["version"] = app_version
    expected_text = json.dumps(
        expected_schema,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    assert output_path.read_text(encoding="utf-8") == expected_text

    exported_schema = json.loads(expected_text)
    assert exported_schema == expected_schema
    exported_operation_ids = {
        operation["operationId"]
        for path_item in exported_schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    app_operation_ids = {
        operation["operationId"]
        for path_item in app_schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert exported_operation_ids
    assert exported_operation_ids == app_operation_ids
    assert exported_schema["components"]["schemas"] == app_schema["components"][
        "schemas"
    ]


def test_openapi_export_ignores_app_identity_environment_overrides(
    tmp_path: Path,
) -> None:
    ordinary_path = tmp_path / "ordinary.json"
    overridden_path = tmp_path / "overridden.json"

    ordinary = _run_exporter("export_openapi_contract.py", str(ordinary_path))
    overridden = _run_exporter(
        "export_openapi_contract.py",
        str(overridden_path),
        env_overrides={
            "APP_NAME": "Environment-specific name",
            "APP_VERSION": "999.999.999",
        },
    )

    assert ordinary.returncode == 0, ordinary.stderr
    assert overridden.returncode == 0, overridden.stderr
    assert overridden_path.read_text(encoding="utf-8") == ordinary_path.read_text(
        encoding="utf-8"
    )


def test_cli_export_is_deterministic_and_captures_visible_command_tree(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "cli.json"

    first = _run_exporter("export_cli_contract.py", str(output_path))
    assert first.returncode == 0, first.stderr
    first_text = output_path.read_text(encoding="utf-8")

    second = _run_exporter("export_cli_contract.py", str(output_path))
    assert second.returncode == 0, second.stderr
    assert output_path.read_text(encoding="utf-8") == first_text

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
    assert contract["command"]["no_args_is_help"] is True
    assert contract["command"]["invoke_without_command"] is False
    assert contract["command"]["chain"] is False
    assert contract["command"]["help_option_names"] == ["-h", "--help"]

    pending_commands = [contract["command"]]
    while pending_commands:
        command = pending_commands.pop()
        assert {
            "chain",
            "help_option_names",
            "invoke_without_command",
            "no_args_is_help",
        } <= command.keys()
        for parameter in command["parameters"]:
            assert {
                "aliases",
                "count",
                "default",
                "envvar",
                "flag_value",
                "help",
                "is_eager",
                "is_flag",
                "kind",
                "metavar",
                "multiple",
                "name",
                "nargs",
                "required",
                "type",
            } <= parameter.keys()
            assert "python_name" not in parameter
        pending_commands.extend(command["commands"])

    root_project = _parameter_by_name(contract["command"], "--project")
    assert root_project["aliases"] == ["-p"]
    assert root_project["default"] is None
    assert root_project["help"] == "Project ID to use (overrides default from config)."
    assert root_project["kind"] == "option"
    assert root_project["required"] is False
    assert root_project["type"] == {"name": "text", "param_type": "String"}
    assert root_project["nargs"] == 1
    assert root_project["multiple"] is False
    assert root_project["metavar"] == "TEXT"
    assert "python_name" not in root_project

    run_submit = _command_by_path(contract, "bif run submit")
    assert run_submit["help"] == "Submit a new run."
    workflow_option = _parameter_by_name(run_submit, "--workflow")
    assert workflow_option["aliases"] == []
    assert workflow_option["default"] is None
    assert workflow_option["help"] == "Workflow ID"
    assert workflow_option["kind"] == "option"
    assert workflow_option["required"] is True

    config_set = _command_by_path(contract, "bif config set")
    key_argument = _parameter_by_name(config_set, "KEY")
    assert key_argument["aliases"] == []
    assert key_argument["default"] is None
    assert key_argument["help"] == "Config key to set"
    assert key_argument["kind"] == "argument"
    assert key_argument["required"] is True

    file_upload = _command_by_path(contract, "bif file upload")
    assert _parameter_by_name(file_upload, "--overwrite")["aliases"] == [
        "--no-overwrite"
    ]

    after_seq = _parameter_by_name(
        _command_by_path(contract, "bif agent events"),
        "--after-seq",
    )
    assert after_seq["type"] == {
        "clamp": False,
        "max": None,
        "max_open": False,
        "min": 0,
        "min_open": False,
        "name": "integer range",
        "param_type": "IntRange",
    }

    version = _parameter_by_name(contract["command"], "--version")
    assert version["is_eager"] is True
    assert version["is_flag"] is True
    assert version["flag_value"] is True
    assert version["count"] is False
    assert version["type"] == {"name": "boolean", "param_type": "Bool"}


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

    output_path.write_text("{}\n", encoding="utf-8")
    drift_result = _run_exporter(script_name, "--check", str(output_path))

    assert drift_result.returncode != 0
    assert "drift" in drift_result.stderr.lower()
    assert str(output_path) in drift_result.stderr

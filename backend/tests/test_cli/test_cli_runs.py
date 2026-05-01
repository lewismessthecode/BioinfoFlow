"""Tests for run commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from tests.test_cli.conftest import make_envelope

_R = "app.cli.commands.run"
_RO = "app.cli.commands.run_outputs"
_RB = "app.cli.commands.run_batch"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _run(run_id: str = "r-001", **kw) -> dict:
    return {
        "run_id": run_id,
        "project_id": kw.get("project_id", "p-1"),
        "workflow_id": kw.get("workflow_id", "wf-1"),
        "status": kw.get("status", "running"),
        "current_task": kw.get("current_task", "FASTQC"),
        "created_at": "2025-01-01T00:00:00Z",
    }


class TestRunList:
    def test_lists_runs(self, runner: CliRunner) -> None:
        resp = make_envelope([_run("r-1"), _run("r-2")])
        with patch(f"{_R}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["--mode", "remote", "run", "list"])
        assert result.exit_code == 0
        assert "r-1" in result.stdout

    def test_json_output(self, runner: CliRunner) -> None:
        resp = make_envelope([_run()])
        with patch(f"{_R}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--output", "json", "--mode", "remote", "run", "list"]
            )
        parsed = json.loads(result.stdout)
        assert parsed["success"] is True


class TestRunSubmit:
    def test_submit_with_flags(self, runner: CliRunner) -> None:
        resp = make_envelope(_run())
        with patch(f"{_R}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "remote",
                    "--project",
                    "p-1",
                    "run",
                    "submit",
                    "--workflow",
                    "wf-1",
                ],
            )
        assert result.exit_code == 0
        assert "r-001" in result.stdout

    def test_submit_requires_project(self, runner: CliRunner) -> None:
        result = runner.invoke(
            app, ["--mode", "remote", "run", "submit", "--workflow", "wf-1"]
        )
        assert result.exit_code != 0


class TestRunShow:
    def test_shows_run(self, runner: CliRunner) -> None:
        resp = make_envelope(_run("r-42"))
        with patch(f"{_R}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["--mode", "remote", "run", "show", "r-42"])
        assert result.exit_code == 0
        assert "r-42" in result.stdout


class TestRunLogs:
    def test_logs_output(self, runner: CliRunner) -> None:
        resp = make_envelope(["line 1", "line 2"])
        with patch(f"{_R}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["--mode", "remote", "run", "logs", "r-42"])
        assert result.exit_code == 0
        assert "line 1" in result.stdout


class TestRunCancel:
    def test_cancel_with_force(self, runner: CliRunner) -> None:
        resp = make_envelope(_run(status="cancelled"))
        with patch(f"{_R}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--mode", "remote", "run", "cancel", "r-42", "--force"]
            )
        assert result.exit_code == 0
        assert "cancelled" in result.stdout

    def test_cancel_prompts_without_force(self, runner: CliRunner) -> None:
        resp = make_envelope(_run(status="cancelled"))
        with patch(f"{_R}.api_post", new_callable=AsyncMock, return_value=resp):
            # Reject the prompt — command should abort, no API call.
            result = runner.invoke(
                app, ["--mode", "remote", "run", "cancel", "r-42"], input="n\n"
            )
        assert "Cancel run r-42?" in result.stdout

    def test_cancel_via_confirmation(self, runner: CliRunner) -> None:
        resp = make_envelope(_run(status="cancelled"))
        with patch(f"{_R}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--mode", "remote", "run", "cancel", "r-42"], input="y\n"
            )
        assert result.exit_code == 0
        assert "cancelled" in result.stdout


class TestRunRetry:
    def test_retry(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {
                "run_id": "r-42",
                "new_run_id": "r-43",
                "status": "pending",
                "message": "retried",
            }
        )
        with patch(f"{_R}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["--mode", "remote", "run", "retry", "r-42"])
        assert result.exit_code == 0
        assert "r-43" in result.stdout


class TestRunResume:
    def test_resume(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {
                "run_id": "r-42",
                "new_run_id": "r-44",
                "status": "pending",
                "message": "resumed",
            }
        )
        with patch(f"{_R}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["--mode", "remote", "run", "resume", "r-42"])
        assert result.exit_code == 0
        assert "r-44" in result.stdout


class TestRunCleanup:
    def test_cleanup_with_force(self, runner: CliRunner) -> None:
        resp = make_envelope({"cleaned": True})
        with patch(f"{_R}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--mode", "remote", "run", "cleanup", "r-42", "--force"]
            )
        assert result.exit_code == 0
        assert "cleaned" in result.stdout

    def test_cleanup_prompts_without_force(self, runner: CliRunner) -> None:
        resp = make_envelope({"cleaned": True})
        with patch(f"{_R}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--mode", "remote", "run", "cleanup", "r-42"], input="n\n"
            )
        assert "Clean up run r-42?" in result.stdout


class TestRunOutputsList:
    def test_list_outputs(self, runner: CliRunner) -> None:
        resp = make_envelope(
            [{"name": "result.vcf", "path": "/out/result.vcf", "size_bytes": 1024}]
        )
        with patch(f"{_RO}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--mode", "remote", "run", "outputs", "list", "r-42"]
            )
        assert result.exit_code == 0
        assert "result.vcf" in result.stdout


class TestBatchSubmit:
    def test_submit_from_spec(self, runner: CliRunner, tmp_path) -> None:
        spec = tmp_path / "batch.json"
        spec.write_text(
            json.dumps(
                {
                    "project_id": "p-1",
                    "runs": [
                        {"workflow_id": "wf-1", "values": {"reads": "asset://project/a.fastq.gz"}},
                        {"workflow_id": "wf-2"},
                    ],
                }
            )
        )
        resp = make_envelope({"batch_id": "b-1", "run_count": 3, "status": "submitted"})
        with patch(f"{_RB}.api_post", new_callable=AsyncMock, return_value=resp) as mock_post:
            result = runner.invoke(
                app, ["--mode", "remote", "run", "batch", "submit", "--spec", str(spec)]
            )
        assert result.exit_code == 0
        assert "b-1" in result.stdout
        endpoint = mock_post.call_args[0][1]
        payload = mock_post.call_args[0][2]
        assert endpoint == "/runs/batch"
        assert payload["runs"][0]["values"] == {"reads": "asset://project/a.fastq.gz"}
        assert payload["runs"][1]["values"] == {}

    def test_submit_rejects_legacy_run_payload_keys(self, runner: CliRunner, tmp_path) -> None:
        spec = tmp_path / "batch-legacy.json"
        spec.write_text(
            json.dumps(
                {
                    "project_id": "p-1",
                    "runs": [
                        {"workflow_id": "wf-1", "params": {"reads": "x.fastq.gz"}},
                        {"workflow_id": "wf-2", "values": {}},
                    ],
                }
            )
        )

        result = runner.invoke(
            app,
            ["--mode", "remote", "run", "batch", "submit", "--spec", str(spec)],
        )

        assert result.exit_code != 0
        assert "legacy run keys are not supported" in result.stdout


class TestBatchShow:
    def test_show(self, runner: CliRunner) -> None:
        resp = make_envelope(
            {"batch_id": "b-1", "status": "running", "runs": [], "description": ""}
        )
        with patch(f"{_RB}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--mode", "remote", "run", "batch", "show", "b-1"]
            )
        assert result.exit_code == 0
        assert "b-1" in result.stdout


class TestBatchCancel:
    def test_cancel_with_force(self, runner: CliRunner) -> None:
        resp = make_envelope({"batch_id": "b-1", "status": "cancelled"})
        with patch(f"{_RB}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                ["--mode", "remote", "run", "batch", "cancel", "b-1", "--force"],
            )
        assert result.exit_code == 0
        assert "cancelled" in result.stdout

    def test_cancel_prompts_without_force(self, runner: CliRunner) -> None:
        resp = make_envelope({"batch_id": "b-1", "status": "cancelled"})
        with patch(f"{_RB}.api_post", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app,
                ["--mode", "remote", "run", "batch", "cancel", "b-1"],
                input="n\n",
            )
        assert "Cancel all runs in batch b-1?" in result.stdout


class TestRunListFilters:
    def test_list_with_workflow_filter(self, runner: CliRunner) -> None:
        resp = make_envelope([_run()])
        with patch(
            f"{_R}.api_get", new_callable=AsyncMock, return_value=resp
        ) as mock_get:
            result = runner.invoke(
                app, ["--mode", "remote", "run", "list", "--workflow", "wf-9"]
            )
        assert result.exit_code == 0
        params = mock_get.call_args[0][2]
        assert params["workflow_id"] == "wf-9"

    def test_list_with_status_filter(self, runner: CliRunner) -> None:
        resp = make_envelope([_run()])
        with patch(
            f"{_R}.api_get", new_callable=AsyncMock, return_value=resp
        ) as mock_get:
            result = runner.invoke(
                app, ["--mode", "remote", "run", "list", "--status", "completed,failed"]
            )
        assert result.exit_code == 0
        params = mock_get.call_args[0][2]
        assert params["status"] == "completed,failed"

    def test_list_with_cursor(self, runner: CliRunner) -> None:
        resp = make_envelope([_run()])
        with patch(
            f"{_R}.api_get", new_callable=AsyncMock, return_value=resp
        ) as mock_get:
            result = runner.invoke(
                app, ["--mode", "remote", "run", "list", "--cursor", "c1"]
            )
        assert result.exit_code == 0
        params = mock_get.call_args[0][2]
        assert params["cursor"] == "c1"


class TestRunSubmitAdvanced:
    def test_submit_rejects_removed_workspace_option(self, runner: CliRunner) -> None:
        resp = make_envelope(_run())
        with patch(
            f"{_R}.api_post", new_callable=AsyncMock, return_value=resp
        ):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "remote",
                    "--project",
                    "p-1",
                    "run",
                    "submit",
                    "--workflow",
                    "wf-1",
                    "--workspace",
                    "/data/ws",
                ],
            )
        assert result.exit_code != 0

    def test_submit_rejects_removed_params_option(self, runner: CliRunner) -> None:
        resp = make_envelope(_run())
        with patch(
            f"{_R}.api_post", new_callable=AsyncMock, return_value=resp
        ):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "remote",
                    "--project",
                    "p-1",
                    "run",
                    "submit",
                    "--workflow",
                    "wf-1",
                    "--params",
                    '{"ref": "hg38"}',
                ],
            )
        assert result.exit_code != 0

    def test_submit_with_values(self, runner: CliRunner) -> None:
        resp = make_envelope(_run())
        with patch(
            f"{_R}.api_post", new_callable=AsyncMock, return_value=resp
        ) as mock_post:
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "remote",
                    "--project",
                    "p-1",
                    "run",
                    "submit",
                    "--workflow",
                    "wf-1",
                    "--values",
                    '{"ref": "hg38"}',
                ],
            )
        assert result.exit_code == 0
        endpoint = mock_post.call_args[0][1]
        payload = mock_post.call_args[0][2]
        assert endpoint == "/runs"
        assert payload["values"] == {"ref": "hg38"}
        assert "params" not in payload

    def test_wizard_rejects_legacy_spec_keys(self, runner: CliRunner, tmp_path) -> None:
        spec = tmp_path / "wizard-legacy.json"
        spec.write_text(
            json.dumps(
                {
                    "workflow_id": "wf-1",
                    "project_id": "p-1",
                    "params": {"reads": "asset://project/reads.fastq.gz"},
                }
            )
        )

        result = runner.invoke(
            app, ["--mode", "remote", "run", "wizard", "--spec", str(spec)]
        )

        assert result.exit_code != 0
        assert "legacy run keys are not supported" in result.stdout


class TestRunWizard:
    def test_wizard(self, runner: CliRunner, tmp_path) -> None:
        spec = tmp_path / "wizard.json"
        spec.write_text(
            json.dumps(
                {
                    "workflow_id": "wf-1",
                    "project_id": "p-1",
                    "values": {"reads": "asset://project/reads.fastq.gz"},
                }
            )
        )
        resp = make_envelope(_run())
        with patch(
            f"{_R}.api_post", new_callable=AsyncMock, return_value=resp
        ) as mock_post:
            result = runner.invoke(
                app, ["--mode", "remote", "run", "wizard", "--spec", str(spec)]
            )
        assert result.exit_code == 0
        assert "r-001" in result.stdout
        endpoint = mock_post.call_args[0][1]
        payload = mock_post.call_args[0][2]
        assert endpoint == "/runs"
        assert payload["values"] == {"reads": "asset://project/reads.fastq.gz"}


class TestRunLogsFormats:
    def test_logs_string_data(self, runner: CliRunner) -> None:
        resp = make_envelope("log output as string")
        with patch(f"{_R}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["--mode", "remote", "run", "logs", "r-42"])
        assert result.exit_code == 0
        assert "log output as string" in result.stdout

    def test_logs_dict_data(self, runner: CliRunner) -> None:
        resp = make_envelope({"lines": ["dict line 1", "dict line 2"]})
        with patch(f"{_R}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(app, ["--mode", "remote", "run", "logs", "r-42"])
        assert result.exit_code == 0
        assert "dict line 1" in result.stdout

    def test_logs_with_task_filter(self, runner: CliRunner) -> None:
        resp = make_envelope(["task log"])
        with patch(
            f"{_R}.api_get", new_callable=AsyncMock, return_value=resp
        ) as mock_get:
            result = runner.invoke(
                app, ["--mode", "remote", "run", "logs", "r-42", "--task", "FASTQC"]
            )
        assert result.exit_code == 0
        params = mock_get.call_args[0][2]
        assert params["task"] == "FASTQC"

    def test_logs_json_no_follow(self, runner: CliRunner) -> None:
        resp = make_envelope(["line 1"])
        with patch(f"{_R}.api_get", new_callable=AsyncMock, return_value=resp):
            result = runner.invoke(
                app, ["--output", "json", "--mode", "remote", "run", "logs", "r-42"]
            )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["success"] is True


class TestRunOutputsDownload:
    def test_download(self, runner: CliRunner, tmp_path) -> None:
        dest_file = tmp_path / "r-42_outputs.tar.gz"
        with patch(
            f"{_RO}.api_download", new_callable=AsyncMock, return_value=dest_file
        ):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "remote",
                    "run",
                    "outputs",
                    "download",
                    "r-42",
                    "--dest",
                    str(tmp_path),
                ],
            )
        assert result.exit_code == 0
        assert "Downloaded" in result.stdout

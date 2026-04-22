from __future__ import annotations

import asyncio
from argparse import Namespace

import httpx
import pytest

import scripts.agent_harness as agent_harness
from app.services.agent.harness import (
    get_scenario,
    provision_workspace,
    score_scenario_result,
)
from app.services.agent.harness_runner import (
    build_client_options,
    build_project_payload,
    render_aggregate_markdown,
    resolve_scenarios,
    summarize_results,
)


def test_resolve_scenarios_supports_single_and_all_modes():
    all_scenarios = resolve_scenarios(run_all=True, scenario_id=None)
    assert len(all_scenarios) == 10

    single = resolve_scenarios(run_all=False, scenario_id="omics_script_execution")
    assert [scenario["id"] for scenario in single] == ["omics_script_execution"]


def test_build_client_options_supports_cookie_and_extra_headers():
    options = build_client_options(
        session_cookie="session-token.mock-signature",
        header_assignments=["X-Test=1", "Authorization=Bearer local-token"],
    )

    assert options["cookies"] == {"better-auth.session_token": "session-token.mock-signature"}
    assert options["headers"]["X-Test"] == "1"
    assert options["headers"]["Authorization"] == "Bearer local-token"
    assert options["trust_env"] is False


def test_build_project_payload_creates_scenario_specific_workspace(tmp_path):
    scenario = get_scenario("clinical_survival_analysis")

    payload = build_project_payload(
        scenario=scenario,
        workspace_root=tmp_path,
        run_label="20260407t000000z",
    )

    assert scenario["id"] in payload["name"]
    assert str(tmp_path) in payload["external_root_path"]
    assert payload["external_root_path"].endswith(scenario["id"])


def test_provision_workspace_creates_expected_rna_seq_fixture_files(tmp_path):
    scenario = get_scenario("rna_seq_differential_expression")

    created = provision_workspace(tmp_path, scenario)

    assert "data/counts.csv" in created
    assert "data/meta.csv" in created
    assert (tmp_path / "data" / "counts.csv").read_text(encoding="utf-8").startswith(
        "gene_id"
    )
    assert (tmp_path / "data" / "meta.csv").read_text(encoding="utf-8").startswith(
        "sample_id"
    )


def test_score_scenario_result_passes_when_tools_links_and_outputs_are_present(tmp_path):
    scenario = get_scenario("omics_script_execution")
    provision_workspace(tmp_path, scenario)
    output_path = tmp_path / "outputs" / "agent-report" / "qc-summary.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake-png")

    result = {
        "status": {"is_running": False},
        "events": [
            {
                "event": "agent.tool_call_start",
                "data": {"metadata": {"name": "execute_code"}},
            },
            {"event": "agent.done", "data": {}},
        ],
        "history": {
            "messages": [
                {
                    "role": "agent",
                    "type": "text",
                    "content": "Executed the Python analysis and saved plots to outputs/agent-report/qc-summary.png",
                }
            ]
        },
    }

    score = score_scenario_result(scenario, result=result, workspace_root=tmp_path)

    assert score["passed"] is True
    assert score["passed_checks"] == score["total_checks"]
    assert all(check["passed"] for check in score["checks"])


def test_score_scenario_result_accepts_artifacts_saved_under_data_when_reply_mentions_them(
    tmp_path,
):
    scenario = get_scenario("rna_seq_differential_expression")
    provision_workspace(tmp_path, scenario)
    artifact_path = tmp_path / "data" / "de_results.csv"
    artifact_path.write_text("gene,log2fc\nTP53,1.2\n", encoding="utf-8")

    result = {
        "status": {"is_running": False},
        "events": [
            {
                "event": "agent.tool_call_start",
                "data": {"metadata": {"name": "execute_code"}},
            }
        ],
        "history": {
            "messages": [
                {
                    "role": "agent",
                    "type": "text",
                    "content": "Saved the differential expression results to data/de_results.csv.",
                }
            ]
        },
    }

    score = score_scenario_result(scenario, result=result, workspace_root=tmp_path)

    assert score["passed"] is True


def test_score_scenario_result_accepts_root_level_analysis_outputs(tmp_path):
    scenario = get_scenario("clinical_survival_analysis")
    provision_workspace(tmp_path, scenario)
    (tmp_path / "km_results.json").write_text('{"median_os": 14}', encoding="utf-8")
    (tmp_path / "km_survival_curves.csv").write_text(
        "arm,time,survival_probability\ncontrol,14,0.5\n",
        encoding="utf-8",
    )

    result = {
        "status": {"is_running": False},
        "events": [
            {
                "event": "agent.tool_call_start",
                "data": {"metadata": {"name": "shell"}},
            }
        ],
        "history": {
            "messages": [
                {
                    "role": "agent",
                    "type": "text",
                    "content": "Created km_results.json and km_survival_curves.csv in the workspace root.",
                }
            ]
        },
    }

    score = score_scenario_result(scenario, result=result, workspace_root=tmp_path)

    assert score["passed"] is True


def test_score_scenario_result_fails_when_pubmed_run_has_no_links_or_search(tmp_path):
    scenario = get_scenario("pubmed_crispr_base_editing")

    result = {
        "status": {"is_running": False},
        "events": [{"event": "agent.done", "data": {}}],
        "history": {
            "messages": [
                {
                    "role": "agent",
                    "type": "text",
                    "content": "Here is some general background on base editing without citations.",
                }
            ]
        },
    }

    score = score_scenario_result(scenario, result=result, workspace_root=tmp_path)

    assert score["passed"] is False
    assert score["failed_checks"] >= 1
    assert any(not check["passed"] for check in score["checks"])


def test_score_scenario_result_classifies_provider_errors_as_infra_fail(tmp_path):
    scenario = get_scenario("omics_script_execution")

    result = {
        "status": {"is_running": False},
        "events": [{"event": "agent.error", "data": {}}],
        "history": {
            "messages": [
                {
                    "role": "agent",
                    "type": "text",
                    "content": (
                        "litellm.MidStreamFallbackError: "
                        "Vertex_ai_betaException - 503 Service Unavailable"
                    ),
                }
            ]
        },
    }

    score = score_scenario_result(scenario, result=result, workspace_root=tmp_path)

    assert score["classification"] == "infra_fail"


def test_summarize_results_and_render_markdown_for_batch_run():
    results = [
        {
            "scenario": {"id": "omics_script_execution"},
            "score": {"passed": True, "passed_checks": 4, "total_checks": 4},
        },
        {
            "scenario": {"id": "pubmed_crispr_base_editing"},
            "score": {"passed": False, "passed_checks": 2, "total_checks": 4},
        },
    ]

    summary = summarize_results(results)
    markdown = render_aggregate_markdown(summary)

    assert summary["scenario_count"] == 2
    assert summary["passed_scenarios"] == 1
    assert summary["failed_scenarios"] == 1
    assert "omics_script_execution" in markdown
    assert "pubmed_crispr_base_editing" in markdown


@pytest.mark.asyncio
async def test_run_single_scenario_recovers_when_sse_stream_disconnects(
    tmp_path, monkeypatch
):
    scenario = get_scenario("omics_script_execution")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()

    async def fake_ensure_project(client, *, scenario, args, run_label):
        return ({"id": "project-123"}, workspace_path)

    async def fake_api_request(client, method, path, **kwargs):
        if method == "POST" and path == "/agent/conversations":
            return {"id": "conversation-123"}
        if method == "POST" and path == "/agent/message":
            return {"accepted": True}
        if method == "GET" and path.endswith("/status"):
            return {
                "conversation_id": "conversation-123",
                "is_running": False,
                "assistant_message_id": None,
                "last_event_at": None,
            }
        if method == "GET" and path.endswith("conversation-123"):
            return {
                "messages": [
                    {
                        "role": "agent",
                        "type": "text",
                        "content": "Completed analysis after the event stream disconnected.",
                    }
                ]
            }
        raise AssertionError(f"Unexpected request: {method} {path}")

    async def fake_collect_events(
        client,
        *,
        project_id,
        conversation_id,
        until_done,
        bucket,
        timeout_seconds,
    ):
        del until_done
        raise httpx.RemoteProtocolError("incomplete chunked read")

    monkeypatch.setattr(agent_harness, "_ensure_project", fake_ensure_project)
    monkeypatch.setattr(agent_harness, "_api_request", fake_api_request)
    monkeypatch.setattr(agent_harness, "_collect_events", fake_collect_events)
    monkeypatch.setattr(agent_harness, "provision_workspace", lambda *_args: [])

    args = Namespace(
        project_id=None,
        workspace_root=str(tmp_path / "workspaces"),
        timeout_seconds=0.1,
    )

    result = await agent_harness._run_single_scenario(
        client=object(),
        scenario=scenario,
        args=args,
        timestamp="20260408T010000Z",
        output_dir=output_dir,
    )

    assert result["status"]["is_running"] is False
    assert result["history"]["messages"][-1]["content"].startswith("Completed analysis")
    assert (output_dir / "20260408T010000Z-omics_script_execution.json").exists()


@pytest.mark.asyncio
async def test_run_single_scenario_ignores_collector_timeout_during_cancel(
    tmp_path, monkeypatch
):
    scenario = get_scenario("omics_script_execution")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()

    async def fake_ensure_project(client, *, scenario, args, run_label):
        return ({"id": "project-456"}, workspace_path)

    async def fake_api_request(client, method, path, **kwargs):
        if method == "POST" and path == "/agent/conversations":
            return {"id": "conversation-456"}
        if method == "POST" and path == "/agent/message":
            return {"accepted": True}
        if method == "GET" and path.endswith("/status"):
            return {
                "conversation_id": "conversation-456",
                "is_running": False,
                "assistant_message_id": None,
                "last_event_at": None,
            }
        if method == "GET" and path.endswith("conversation-456"):
            return {
                "messages": [
                    {
                        "role": "agent",
                        "type": "text",
                        "content": "Recovered after SSE collector timeout during shutdown.",
                    }
                ]
            }
        raise AssertionError(f"Unexpected request: {method} {path}")

    async def fake_collect_events(
        client,
        *,
        project_id,
        conversation_id,
        until_done,
        bucket,
        timeout_seconds,
    ):
        del until_done
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError as exc:
            raise TimeoutError("collector cancelled while reading SSE stream") from exc

    monkeypatch.setattr(agent_harness, "_ensure_project", fake_ensure_project)
    monkeypatch.setattr(agent_harness, "_api_request", fake_api_request)
    monkeypatch.setattr(agent_harness, "_collect_events", fake_collect_events)
    monkeypatch.setattr(agent_harness, "provision_workspace", lambda *_args: [])

    args = Namespace(
        project_id=None,
        workspace_root=str(tmp_path / "workspaces"),
        timeout_seconds=0.05,
    )

    result = await agent_harness._run_single_scenario(
        client=object(),
        scenario=scenario,
        args=args,
        timestamp="20260408T020000Z",
        output_dir=output_dir,
    )

    assert result["status"]["is_running"] is False
    assert result["history"]["messages"][-1]["content"].startswith("Recovered after SSE")

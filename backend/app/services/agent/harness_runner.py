from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.agent.harness import SCENARIOS, get_scenario


def resolve_scenarios(*, run_all: bool, scenario_id: str | None) -> list[dict[str, Any]]:
    if run_all:
        return list(SCENARIOS)
    if not scenario_id:
        raise ValueError("scenario_id is required unless run_all=True")
    return [get_scenario(scenario_id)]


def build_client_options(
    *,
    session_cookie: str | None = None,
    header_assignments: list[str] | None = None,
) -> dict[str, Any]:
    headers: dict[str, str] = {}
    for assignment in header_assignments or []:
        key, separator, value = assignment.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"Invalid header assignment: {assignment}")
        headers[key.strip()] = value.strip()

    cookies: dict[str, str] = {}
    if session_cookie:
        cookies["better-auth.session_token"] = session_cookie.strip()

    return {"headers": headers, "cookies": cookies, "trust_env": False}


def build_project_payload(
    *,
    scenario: dict[str, Any],
    workspace_root: Path,
    run_label: str | None = None,
) -> dict[str, Any]:
    label = run_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    workspace_path = workspace_root / label / scenario["id"]
    return {
        "name": f"harness-{scenario['id']}-{label}",
        "description": f"Auto-generated harness workspace for {scenario['id']}",
        "external_root_path": str(workspace_path),
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    scenario_count = len(results)
    passed = [item for item in results if item.get("score", {}).get("passed")]
    failed = [item for item in results if not item.get("score", {}).get("passed")]
    return {
        "scenario_count": scenario_count,
        "passed_scenarios": len(passed),
        "failed_scenarios": len(failed),
        "results": results,
    }


def render_aggregate_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Agent Harness Summary",
        "",
        f"- Scenario count: {summary['scenario_count']}",
        f"- Passed: {summary['passed_scenarios']}",
        f"- Failed: {summary['failed_scenarios']}",
        "",
        "## Results",
        "",
    ]
    for item in summary.get("results", []):
        scenario_id = item.get("scenario", {}).get("id", "unknown")
        score = item.get("score", {})
        status = "PASS" if score.get("passed") else "FAIL"
        lines.append(
            f"- {scenario_id}: {status} ({score.get('passed_checks', 0)}/{score.get('total_checks', 0)} checks)"
        )
    return "\n".join(lines)

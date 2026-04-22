from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from httpx_sse import aconnect_sse

from app.services.agent.harness import (
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


DEFAULT_BASE_URL = "http://localhost:8000/api/v1"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Bioinfoflow agent regression harness scenarios against the live API."
    )
    parser.add_argument("--project-id", help="Existing project ID to target for a single scenario")
    parser.add_argument("--scenario-id", help="Scenario ID from the harness catalog")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all harness scenarios sequentially. Auto-creates one project per scenario.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument(
        "--output-dir",
        default="output/agent-harness",
        help="Directory where per-scenario and aggregate reports will be written",
    )
    parser.add_argument(
        "--workspace-root",
        default="tmp/agent-harness-workspaces",
        help="Root directory for auto-created harness workspaces",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=180.0,
        help="Maximum time to wait for each agent turn to finish",
    )
    parser.add_argument(
        "--session-cookie",
        help="Better Auth session cookie value to send as better-auth.session_token",
    )
    parser.add_argument(
        "--session-cookie-file",
        help="Read the Better Auth session cookie value from a file",
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help="Extra header in KEY=VALUE format. Can be supplied multiple times.",
    )
    return parser.parse_args()


async def _api_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    **kwargs: Any,
) -> dict[str, Any]:
    response = await client.request(method, path, **kwargs)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success", False):
        raise RuntimeError(f"API request failed: {payload}")
    return payload["data"]


async def _collect_events(
    client: httpx.AsyncClient,
    *,
    project_id: str,
    conversation_id: str,
    until_done: asyncio.Event,
    bucket: list[dict[str, Any]],
    timeout_seconds: float,
) -> None:
    async with aconnect_sse(
        client,
        "GET",
        "/events/stream",
        params={"project_id": project_id, "conversation_id": conversation_id},
    ) as event_source:
        async with asyncio.timeout(timeout_seconds):
            async for sse in event_source.aiter_sse():
                if not sse.data:
                    continue
                payload = json.loads(sse.data)
                bucket.append(payload)
                if payload.get("event") in {"agent.done", "agent.cancelled", "agent.error"}:
                    until_done.set()
                    return


async def _wait_for_conversation_to_settle(
    client: httpx.AsyncClient,
    *,
    conversation_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    latest_status: dict[str, Any] = {
        "conversation_id": conversation_id,
        "is_running": True,
        "assistant_message_id": None,
        "last_event_at": None,
    }
    while True:
        latest_status = await _api_request(
            client,
            "GET",
            f"/agent/conversations/{conversation_id}/status",
        )
        if not latest_status.get("is_running", False):
            return latest_status

        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return latest_status
        await asyncio.sleep(min(1.0, remaining))


async def _drain_collector(task: asyncio.Task[None]) -> str | None:
    try:
        await task
    except asyncio.CancelledError:
        return None
    except (httpx.HTTPError, TimeoutError) as exc:
        return str(exc)
    return None


def _render_markdown_summary(result: dict[str, Any]) -> str:
    history = result.get("history", {}).get("messages", [])
    final_agent = next(
        (
            message
            for message in reversed(history)
            if message.get("role") == "agent" and message.get("type") == "text"
        ),
        None,
    )
    lines = [
        f"# Agent Harness Result: {result['scenario']['id']}",
        "",
        f"- Timestamp: {result['timestamp']}",
        f"- Project ID: {result['project']['id']}",
        f"- Project Home: {result['workspace_root']}",
        f"- Conversation ID: {result['conversation_id']}",
        f"- Final status: {result['status'].get('is_running') and 'running' or 'idle'}",
        f"- Event counts: {json.dumps(result['event_counts'], ensure_ascii=False)}",
        f"- Score: {result['score']['passed_checks']}/{result['score']['total_checks']} ({'PASS' if result['score']['passed'] else 'FAIL'})",
        "",
        "## Prompt",
        "",
        result["scenario"]["prompt"],
        "",
        "## Fixtures",
        "",
    ]
    if result["fixtures_created"]:
        lines.extend(f"- {item}" for item in result["fixtures_created"])
    else:
        lines.append("- No local fixtures were required.")
    lines.extend(["", "## Checks", ""])
    for check in result["score"]["checks"]:
        mark = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- [{mark}] {check['description']}")
    lines.extend(["", "## Final Assistant Reply", ""])
    lines.append(
        final_agent.get("content", "_No assistant reply captured._")
        if final_agent
        else "_No assistant reply captured._"
    )
    return "\n".join(lines)


def _load_session_cookie(args: argparse.Namespace) -> str | None:
    if args.session_cookie:
        return args.session_cookie.strip()
    if args.session_cookie_file:
        return Path(args.session_cookie_file).read_text(encoding="utf-8").strip()
    return None


async def _ensure_project(
    client: httpx.AsyncClient,
    *,
    scenario: dict[str, Any],
    args: argparse.Namespace,
    run_label: str,
) -> tuple[dict[str, Any], Path | None]:
    if args.project_id:
        project = await _api_request(client, "GET", f"/projects/{args.project_id}")
        return project, None

    payload = build_project_payload(
        scenario=scenario,
        workspace_root=Path(args.workspace_root),
        run_label=run_label,
    )
    project = await _api_request(client, "POST", "/projects", json=payload)
    return project, Path(payload["external_root_path"])


async def _run_single_scenario(
    client: httpx.AsyncClient,
    *,
    scenario: dict[str, Any],
    args: argparse.Namespace,
    timestamp: str,
    output_dir: Path,
) -> dict[str, Any]:
    run_label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    project, workspace_root = await _ensure_project(
        client, scenario=scenario, args=args, run_label=run_label
    )
    if workspace_root is None:
        raise RuntimeError(
            "Existing-project harness runs require an auto-created external_root_path."
        )
    fixtures_created = provision_workspace(workspace_root, scenario)

    conversation = await _api_request(
        client,
        "POST",
        "/agent/conversations",
        json={"project_id": project["id"], "title": scenario["id"]},
    )
    conversation_id = conversation["id"]

    done_event = asyncio.Event()
    events: list[dict[str, Any]] = []
    collector = asyncio.create_task(
        _collect_events(
            client,
            project_id=project["id"],
            conversation_id=conversation_id,
            until_done=done_event,
            bucket=events,
            timeout_seconds=args.timeout_seconds,
        )
    )

    await _api_request(
        client,
        "POST",
        "/agent/message",
        json={
            "project_id": project["id"],
            "conversation_id": conversation_id,
            "content": scenario["prompt"],
        },
    )

    done_waiter = asyncio.create_task(done_event.wait())
    stream_error: str | None = None
    status: dict[str, Any] | None = None
    collector_drained = False
    try:
        done, _pending = await asyncio.wait(
            {collector, done_waiter},
            timeout=args.timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if collector in done:
            stream_error = await _drain_collector(collector)
            collector_drained = True
            if not done_event.is_set():
                status = await _wait_for_conversation_to_settle(
                    client,
                    conversation_id=conversation_id,
                    timeout_seconds=args.timeout_seconds,
                )
        elif done_waiter not in done:
            status = await _wait_for_conversation_to_settle(
                client,
                conversation_id=conversation_id,
                timeout_seconds=args.timeout_seconds,
            )
    finally:
        if not done_waiter.done():
            done_waiter.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await done_waiter

        if not collector.done():
            collector.cancel()
        if not collector_drained:
            collector_error = await _drain_collector(collector)
            if collector_error and not stream_error:
                stream_error = collector_error

    history = await _api_request(client, "GET", f"/agent/conversations/{conversation_id}")
    status = status or await _api_request(
        client,
        "GET",
        f"/agent/conversations/{conversation_id}/status",
    )

    if stream_error:
        events.append(
            {
                "event": "agent.stream_error",
                "data": {"metadata": {"message": stream_error}},
            }
        )

    result = {
        "timestamp": timestamp,
        "project": project,
        "project_id": project["id"],
        "conversation_id": conversation_id,
        "scenario": scenario,
        "status": status,
        "workspace_root": str(workspace_root),
        "event_counts": dict(Counter(item["event"] for item in events)),
        "events": events,
        "history": history,
        "fixtures_created": fixtures_created,
    }
    result["score"] = score_scenario_result(
        scenario,
        result=result,
        workspace_root=workspace_root,
    )

    result_prefix = output_dir / f"{timestamp}-{scenario['id']}"
    json_path = result_prefix.with_suffix(".json")
    md_path = result_prefix.with_suffix(".md")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown_summary(result), encoding="utf-8")

    print(
        f"[{scenario['id']}] {'PASS' if result['score']['passed'] else 'FAIL'} "
        f"{result['score']['passed_checks']}/{result['score']['total_checks']} checks"
    )
    print(f"[{scenario['id']}] Wrote JSON result to {json_path}")
    print(f"[{scenario['id']}] Wrote markdown summary to {md_path}")
    return result


async def main() -> None:
    args = _parse_args()
    scenarios = resolve_scenarios(run_all=args.all, scenario_id=args.scenario_id)
    if args.all and args.project_id:
        raise SystemExit("--project-id cannot be combined with --all; auto-created projects are used for batch runs.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_cookie = _load_session_cookie(args)
    client_options = build_client_options(
        session_cookie=session_cookie,
        header_assignments=args.header,
    )

    async with httpx.AsyncClient(
        base_url=args.base_url,
        timeout=30.0,
        headers=client_options["headers"],
        cookies=client_options["cookies"],
        trust_env=client_options.get("trust_env", False),
    ) as client:
        results: list[dict[str, Any]] = []
        for scenario in scenarios:
            results.append(
                await _run_single_scenario(
                    client,
                    scenario=scenario,
                    args=args,
                    timestamp=timestamp,
                    output_dir=output_dir,
                )
            )

    summary = summarize_results(results)
    summary["timestamp"] = timestamp
    summary_prefix = output_dir / f"{timestamp}-summary"
    summary_json = summary_prefix.with_suffix(".json")
    summary_md = summary_prefix.with_suffix(".md")
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_md.write_text(render_aggregate_markdown(summary), encoding="utf-8")

    print(f"Wrote aggregate JSON summary to {summary_json}")
    print(f"Wrote aggregate markdown summary to {summary_md}")


if __name__ == "__main__":
    asyncio.run(main())

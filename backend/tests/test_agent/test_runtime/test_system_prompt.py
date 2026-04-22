from __future__ import annotations

from datetime import datetime, timezone

from app.services.agent.runtime.system_prompt import build_system_prompt


def test_runtime_system_prompt_does_not_reference_removed_demo_catalog():
    prompt = build_system_prompt()

    assert "/demos" not in prompt
    assert "/workflows/market" not in prompt
    assert "workflow_validate" not in prompt
    assert "ecoli-qc" not in prompt
    assert "parabricks-wgs" not in prompt
    assert "deaf-20" not in prompt
    assert "demo-sars-cov-2" not in prompt
    assert "demo/sars-cov-2" not in prompt


def test_runtime_system_prompt_includes_freshness_and_grounding_rules():
    prompt = build_system_prompt()
    current_year = str(datetime.now(timezone.utc).year)

    assert current_year in prompt
    assert "If the user asks about current Bioinfoflow behavior" in prompt
    assert "inspect the local workspace and repository first" in prompt
    assert "If the user asks for latest, recent, current, or today" in prompt
    assert "verify that the files exist" in prompt
    assert "pubmed_search" in prompt
    assert "web_fetch" in prompt
    assert "chembl_search" in prompt

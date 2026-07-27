from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_security_docs_describe_agent_browser_dns_rebinding_residual_risk() -> None:
    security = " ".join(
        (_REPO_ROOT / "docs/security.md").read_text(encoding="utf-8").split()
    )

    assert "best-effort public DNS preflight" in security
    assert "runtime domain containment" in security
    assert "does not provide IP pinning" in security
    assert "DNS-rebinding risk" in security
    assert "trusted public domains" in security
    assert "disable Bash network access and agent-browser" in security


def test_harness_plan_does_not_claim_complete_ssrf_boundary() -> None:
    plan = " ".join(
        (_REPO_ROOT / "docs/plans/2026-07-24-agent-harness-surface-simplification.md")
        .read_text(encoding="utf-8")
        .split()
    )

    assert "best-effort preflight plus runtime domain containment" in plan
    assert "not a complete SSRF security boundary" in plan

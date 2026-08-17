from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_security_docs_describe_harness_network_boundaries() -> None:
    security = " ".join(
        (_REPO_ROOT / "docs/security.md").read_text(encoding="utf-8").split()
    )

    assert "Network and process visibility are not sandbox properties" in security
    assert "scoped authenticated `bif` path remains a separate" in security
    assert "remote Bubblewrap" in security
    assert "Command classification is defense in depth" in security
    assert "agent-browser" not in security


def test_harness_plan_does_not_claim_complete_ssrf_boundary() -> None:
    plan = " ".join(
        (_REPO_ROOT / "docs/plans/2026-07-24-agent-harness-surface-simplification.md")
        .read_text(encoding="utf-8")
        .split()
    )

    assert "best-effort preflight plus runtime domain containment" in plan
    assert "not a complete SSRF security boundary" in plan

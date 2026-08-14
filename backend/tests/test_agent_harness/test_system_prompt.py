from __future__ import annotations

from app.services.agent_harness.system_prompt import default_system_prompt_snapshot


def test_default_system_prompt_describes_only_the_five_harness_tools() -> None:
    snapshot = default_system_prompt_snapshot()

    assert snapshot.id == "bioinfoflow-agent-v13"
    assert (
        "The harness exposes exactly five tools: `read`, `bash`, `edit`, `write`, "
        "and `ask_user`." in snapshot.content
    )
    assert (
        "Run Bioinfoflow platform operations through the trusted `bif` CLI inside "
        "`bash`." in snapshot.content
    )
    assert (
        "For public web access, use allowed command-line clients through `bash` only "
        "when the runtime network policy permits it." in snapshot.content
    )
    assert (
        "A remote session's connection and working environment are fixed by the "
        "Session." in snapshot.content
    )
    assert (
        "Keep the append-only Session history as the source of the user's current "
        "intent." in snapshot.content
    )
    assert (
        "Treat confirmation-requiring calls as ordering barriers." in snapshot.content
    )
    assert "Treat interaction-requiring calls as ordering barriers." in snapshot.content

    for retired_semantic in (
        "canonical conversation",
        "approval-requiring calls",
        "target-selection calls",
    ):
        assert retired_semantic not in snapshot.content

    for nonexistent_tool in (
        "web.search",
        "remote.connections.list",
        "remote-capable tools",
        "dedicated Bioinfoflow platform tool",
        "Bioinfoflow platform tools",
    ):
        assert nonexistent_tool not in snapshot.content

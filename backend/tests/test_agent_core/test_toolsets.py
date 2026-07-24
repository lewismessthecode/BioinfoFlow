from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.toolsets import ToolsetExposure


def test_attachment_tools_are_read_only_parallel_safe_and_remote_compatible() -> None:
    registry = build_default_tool_registry()
    search = registry.get("attachments.search").spec
    read = registry.get("attachments.read").spec

    assert search.risk_level == "read"
    assert read.risk_level == "read"
    assert search.parallel_safe is True
    assert read.parallel_safe is True
    exposed = ToolsetExposure(registry).exposed_names(
        policy={"name": "execution"},
        execution_target={"type": "remote_ssh", "connection_id": "conn-1"},
    )
    assert {"attachments.search", "attachments.read"} <= exposed

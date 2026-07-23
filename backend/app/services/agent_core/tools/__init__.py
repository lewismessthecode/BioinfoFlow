from app.path_layout import state_root
from app.services.agent_core.plugins import register_plugin_tools
from app.services.agent_core.tools.dispatcher import AgentToolDispatcher
from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.agent_core.tools.providers import (
    AgentToolProvider,
    default_tool_providers,
)
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.agent_core.tools.toolsets import ToolsetExposure


def build_default_tool_registry() -> AgentToolRegistry:
    """Register every tool in a deterministic, grouped order.

    Provider order is stable for cache-key stability. Exposure is decided
    separately by ``ToolsetExposure``: registration is not model exposure.
    """
    registry = AgentToolRegistry()

    for provider in default_tool_providers():
        registry.register_many(provider.tools())

    register_plugin_tools(registry, root=state_root() / "agent_core" / "plugins")
    return registry


__all__ = [
    "AgentToolContext",
    "AgentToolDispatcher",
    "AgentToolExecutor",
    "AgentToolProvider",
    "AgentToolRegistry",
    "AgentToolSpec",
    "ToolsetExposure",
    "build_default_tool_registry",
]

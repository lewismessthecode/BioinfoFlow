from typing import Any

from app.services.llm.profiles.base import ProviderProfile
from app.services.model_runtime.contracts import ReasoningRequest


class OpenRouterProfile(ProviderProfile):
    def invocation_options(
        self,
        model_name: str,
        reasoning: ReasoningRequest,
    ) -> dict[str, Any]:
        del model_name
        if not reasoning.enabled:
            return {}
        return {"reasoning": {"effort": reasoning.effort or "medium"}}

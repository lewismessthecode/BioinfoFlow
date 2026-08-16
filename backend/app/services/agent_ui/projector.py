"""Current Harness adapter for the stable Agent UI protocol.

The imports remain delegated during the expand phase so existing runtime code keeps
working while API consumers move to this product-owned boundary.
"""

from app.services.agent_harness.projection import (
    entry_contract,
    pending_interaction_entry_view,
    public_interaction_request,
    public_interaction_response,
    public_model_summary,
    public_run_error,
    run_view,
)
from app.services.agent_ui.contracts import StoredArtifactResourceView


def public_artifact_resource(value: object) -> dict | None:
    if not isinstance(value, dict) or value.get("kind") != "stored_file":
        return None
    try:
        return StoredArtifactResourceView.model_validate(value).model_dump(mode="json")
    except ValueError:
        return None

__all__ = [
    "entry_contract",
    "pending_interaction_entry_view",
    "public_artifact_resource",
    "public_interaction_request",
    "public_interaction_response",
    "public_model_summary",
    "public_run_error",
    "run_view",
]

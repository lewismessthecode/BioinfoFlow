from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


RiskLevel = Literal[
    "read", "act_low", "act_high", "destructive", "external", "critical"
]


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    reasons: list[str] = field(default_factory=list)
    affected_resources: list[dict] = field(default_factory=list)
    requires_explicit_approval: bool = False


class RiskEngine:
    def assess(
        self,
        *,
        kind: str,
        name: str,
        requested_level: RiskLevel | None = None,
        input: dict | None = None,
    ) -> RiskAssessment:
        if requested_level is not None:
            return RiskAssessment(
                level=requested_level,
                reasons=[f"tool declared {requested_level} risk"],
                affected_resources=_affected_resources(input or {}),
            )

        normalized = f"{kind}:{name}".lower()
        if normalized.startswith("tool:read") or normalized.startswith("platform:list"):
            level: RiskLevel = "read"
        elif any(term in normalized for term in ("delete", "remove", "purge", "wipe")):
            level = "destructive"
        elif any(
            term in normalized for term in ("submit", "cancel", "register", "update")
        ):
            level = "act_high"
        elif kind in {"shell", "code", "config"}:
            level = "act_high"
        else:
            level = "act_low"

        return RiskAssessment(
            level=level,
            reasons=[f"inferred from {kind}:{name}"],
            affected_resources=_affected_resources(input or {}),
        )


def _affected_resources(input: dict) -> list[dict]:
    resources: list[dict] = []
    for key in ("project_id", "run_id", "workflow_id", "image_id", "file_path"):
        value = input.get(key)
        if value:
            resources.append({"type": key.removesuffix("_id"), "id": str(value)})
    return resources

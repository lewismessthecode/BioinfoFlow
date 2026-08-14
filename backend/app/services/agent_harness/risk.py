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

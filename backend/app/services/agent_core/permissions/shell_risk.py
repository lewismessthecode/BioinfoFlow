"""Backward-compatible shell risk entry point.

Command semantics now live in :mod:`command_risk` so local and SSH execution
cannot drift into separate classifiers. Existing callers keep this function
while the richer tool path consumes ``CommandRiskAssessment`` directly.
"""

from __future__ import annotations

from app.services.agent_core.permissions.command_risk import classify_command_level
from app.services.agent_core.permissions.risk import RiskLevel


def classify_shell_command(command: str) -> RiskLevel:
    return classify_command_level(command)

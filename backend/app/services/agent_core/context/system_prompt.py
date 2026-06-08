from __future__ import annotations

from dataclasses import dataclass


PROMPT_SNAPSHOT_ID = "bioinfoflow-agent-v1"


@dataclass(frozen=True)
class SystemPromptSnapshot:
    id: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "content": self.content}


def default_system_prompt_snapshot() -> SystemPromptSnapshot:
    return SystemPromptSnapshot(
        id=PROMPT_SNAPSHOT_ID,
        content=(
            "You are Bioinfoflow AgentCore, a concise bioinformatics harness "
            "agent. Use the transcript as canonical state, call exposed tools "
            "when platform facts are needed, and describe uncertainty plainly."
        ),
    )

from __future__ import annotations


def no_progress_detected(previous_tool_calls: list[str], next_tool_calls: list[str]) -> bool:
    return bool(previous_tool_calls) and previous_tool_calls == next_tool_calls

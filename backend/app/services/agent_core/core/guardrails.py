from __future__ import annotations


def no_progress_detected(
    previous_tool_calls: list[str],
    next_tool_calls: list[str],
    *,
    repeat_count: int,
    max_repeats: int = 2,
) -> bool:
    """Return true once identical tool calls repeat past a small grace window.

    Some useful agent loops poll the same read/status tool while a run, test, or
    remote operation is still settling. Failing on the first repeated signature
    makes those legitimate waits look like a hard agent stall, so the guardrail
    only trips after the model repeats the same call for multiple consecutive
    iterations.
    """

    return (
        bool(previous_tool_calls)
        and previous_tool_calls == next_tool_calls
        and repeat_count > max_repeats
    )

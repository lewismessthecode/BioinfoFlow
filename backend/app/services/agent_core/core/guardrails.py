from __future__ import annotations


def no_progress_detected(
    previous_tool_calls: list[str],
    next_tool_calls: list[str],
    *,
    previous_tool_results: list[str] | None = None,
    next_tool_results: list[str] | None = None,
    repeat_count: int,
    max_repeats: int = 2,
) -> bool:
    """Return true once identical tool calls and results repeat past a grace window.

    Some useful agent loops poll the same read/status tool while a run, test, or
    remote operation is still settling. Failing on the first repeated signature
    makes those legitimate waits look like a hard agent stall. Result-aware
    comparison keeps polling alive while the observed state changes and only
    trips when both the request and the tool output are stuck.
    """

    return (
        bool(previous_tool_calls)
        and previous_tool_calls == next_tool_calls
        and previous_tool_results == next_tool_results
        and repeat_count > max_repeats
    )

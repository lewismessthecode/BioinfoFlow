/**
 * Demo replay engine.
 *
 * Reads NDJSON recordings and dispatches events with compressed timing.
 * Pure logic — no React dependency. Used by the demo context provider.
 */

import type { DemoEvent, DemoRunDag, DemoRunStatus, RecordedEvent } from "./types"

// ---------------------------------------------------------------------------
// Timing compression
// ---------------------------------------------------------------------------

/** Maximum gap between any two events (ms). */
const MAX_GAP_MS = 2000
/** Minimum gap for text deltas — realistic typing speed. */
const DELTA_GAP_MS = 30
/** Brief pause for DAG/status transitions. */
const TRANSITION_PAUSE_MS = 500

/**
 * Compress event timings so the entire recording replays in a reasonable
 * duration. Gaps are capped, text deltas play at typing speed, and DAG
 * status transitions get brief pauses for visual impact.
 */
function compressTimings(events: RecordedEvent[]): number[] {
  if (events.length === 0) return []

  const delays: number[] = [0]

  for (let i = 1; i < events.length; i++) {
    const rawGap = events[i].t - events[i - 1].t
    const eventType = events[i].event

    let delay: number
    if (eventType === "agent.text_delta" || eventType === "agent.thinking_delta") {
      delay = DELTA_GAP_MS
    } else if (eventType === "run.status" || eventType === "run.dag") {
      delay = Math.min(rawGap, TRANSITION_PAUSE_MS)
    } else {
      delay = Math.min(rawGap, MAX_GAP_MS)
    }

    delays.push(delay)
  }

  return delays
}

// ---------------------------------------------------------------------------
// Event parsing
// ---------------------------------------------------------------------------

/** Map a recorded event to a typed DemoEvent. */
function parseRecordedEvent(recorded: RecordedEvent): DemoEvent | null {
  const { event, data } = recorded
  const messageId = (data.id as string) || "demo-msg"

  switch (event) {
    case "agent.text_delta":
      return {
        kind: "agent",
        sseEvent: {
          type: "text_delta",
          messageId,
          content: (data.content as string) || "",
        },
      }

    case "agent.thinking_delta":
      return {
        kind: "agent",
        sseEvent: {
          type: "thinking_delta",
          messageId,
          content: (data.content as string) || "",
        },
      }

    case "agent.tool_call_start": {
      const meta = (data.metadata as Record<string, unknown>) || data
      return {
        kind: "agent",
        sseEvent: {
          type: "tool_call_start",
          messageId,
          metadata: {
            id: (meta.id as string) || "",
            name: (meta.name as string) || "",
            args: (meta.args as Record<string, unknown>) || {},
          },
        },
      }
    }

    case "agent.tool_call_end": {
      const meta = (data.metadata as Record<string, unknown>) || data
      return {
        kind: "agent",
        sseEvent: {
          type: "tool_call_end",
          messageId,
          metadata: {
            id: (meta.id as string) || "",
            name: (meta.name as string) || "",
            result: (meta.result as string) || "",
            is_error: (meta.is_error as boolean) || false,
            duration_ms: (meta.duration_ms as number) || 0,
          },
        },
      }
    }

    case "agent.message":
      return {
        kind: "agent",
        sseEvent: {
          type: "text",
          messageId,
          content: (data.content as string) || "",
        },
      }

    case "agent.done":
      return {
        kind: "agent",
        sseEvent: { type: "done", messageId },
      }

    case "agent.error":
      return {
        kind: "agent",
        sseEvent: {
          type: "error",
          messageId,
          content: (data.content as string) || "An error occurred",
        },
      }

    case "user.message":
      return {
        kind: "user_message",
        text: (data.content as string) || "",
      }

    case "run.status":
      return {
        kind: "run_status",
        data: {
          run_id: (data.run_id as string) || "demo-run",
          status: (data.status as string as DemoRunStatus["status"]) || "running",
          current_task: data.current_task as string | null | undefined,
          tasks_completed: data.tasks_completed as number | undefined,
          tasks_total: data.tasks_total as number | undefined,
          message: data.message as string | undefined,
        },
      }

    case "run.dag":
      return {
        kind: "run_dag",
        data: {
          run_id: (data.run_id as string) || "demo-run",
          dag: data.dag as DemoRunDag["dag"],
        },
      }

    case "run.log":
      return {
        kind: "run_log",
        data: {
          run_id: (data.run_id as string) || "demo-run",
          message: (data.message as string) || "",
          level: data.level as string | undefined,
          task: data.task as string | undefined,
          timestamp: data.timestamp as string | undefined,
        },
      }

    default:
      return null
  }
}

// ---------------------------------------------------------------------------
// NDJSON loader
// ---------------------------------------------------------------------------

/** Parse an NDJSON string into an array of RecordedEvent. */
export function parseNDJSON(text: string): RecordedEvent[] {
  return text
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => {
      try {
        return JSON.parse(line) as RecordedEvent
      } catch {
        return null
      }
    })
    .filter((event): event is RecordedEvent => event !== null)
}

// ---------------------------------------------------------------------------
// Replay scheduler
// ---------------------------------------------------------------------------

export type ReplayCallbacks = {
  onEvent: (event: DemoEvent, index: number, total: number) => void
  onFinish: () => void
}

/**
 * Schedule all events with compressed timing.
 * Returns a cancel function to stop playback.
 */
export function scheduleReplay(
  events: RecordedEvent[],
  callbacks: ReplayCallbacks,
): () => void {
  const delays = compressTimings(events)
  const timers: ReturnType<typeof setTimeout>[] = []

  let cumulativeDelay = 0

  for (let i = 0; i < events.length; i++) {
    cumulativeDelay += delays[i]

    const timer = setTimeout(() => {
      const parsed = parseRecordedEvent(events[i])
      if (parsed) {
        callbacks.onEvent(parsed, i, events.length)
      }

      // Fire onFinish after the last event
      if (i === events.length - 1) {
        callbacks.onFinish()
      }
    }, cumulativeDelay)

    timers.push(timer)
  }

  return () => {
    for (const timer of timers) {
      clearTimeout(timer)
    }
  }
}

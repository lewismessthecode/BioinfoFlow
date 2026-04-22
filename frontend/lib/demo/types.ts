/**
 * Demo replay types.
 *
 * Defines the NDJSON recording format and replay state.
 */

import type { SSEEvent } from "@/lib/chat-types"
import type { DagData, RunStatus } from "@/lib/types"

// ---------------------------------------------------------------------------
// Recording format — each line of the NDJSON file
// ---------------------------------------------------------------------------

/** A recorded event with a time offset from the start of the recording. */
export type RecordedEvent = {
  /** Milliseconds from start of recording. */
  t: number
  /** Event category. */
  event: RecordedEventType
  /** Event payload — shape depends on event type. */
  data: Record<string, unknown>
}

export type RecordedEventType =
  | "agent.text_delta"
  | "agent.thinking_delta"
  | "agent.tool_call_start"
  | "agent.tool_call_end"
  | "agent.message"
  | "agent.done"
  | "agent.error"
  | "run.status"
  | "run.dag"
  | "run.log"
  | "user.message"

// ---------------------------------------------------------------------------
// Replay state
// ---------------------------------------------------------------------------

export type ReplayStatus = "idle" | "playing" | "paused" | "finished"

// ---------------------------------------------------------------------------
// Mapped SSE event (after converting from recording format)
// ---------------------------------------------------------------------------

export type DemoRunStatus = {
  run_id: string
  status: RunStatus
  current_task?: string | null
  tasks_completed?: number
  tasks_total?: number
  message?: string
}

export type DemoRunDag = {
  run_id: string
  dag: DagData
}

export type DemoRunLog = {
  run_id: string
  message: string
  level?: string
  task?: string
  timestamp?: string
}

/** Parsed event dispatched by the replay engine. */
export type DemoEvent =
  | { kind: "agent"; sseEvent: SSEEvent }
  | { kind: "user_message"; text: string }
  | { kind: "run_status"; data: DemoRunStatus }
  | { kind: "run_dag"; data: DemoRunDag }
  | { kind: "run_log"; data: DemoRunLog }

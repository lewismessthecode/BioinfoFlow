import type { AgentEvent } from "@/lib/agent/contracts"
import type { DagData, RunStatus } from "@/lib/types"

export type ReplayStatus = "idle" | "playing" | "paused" | "finished"

export type DemoTimelineItem =
  | {
      t: number
      kind: "agent"
      event: AgentEvent
    }
  | {
      t: number
      kind: "pipeline"
      status: RunStatus
      currentTask: string | null
      dag: DagData | null
    }

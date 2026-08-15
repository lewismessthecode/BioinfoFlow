import type { AgentEvent } from "@/lib/agent/contracts"
import type { DemoTimelineItem } from "./types"

const MAX_GAP_MS = 2000
const DELTA_GAP_MS = 30
const TRANSITION_PAUSE_MS = 500

const AGENT_EVENT_TYPES = new Set<AgentEvent["type"]>([
  "snapshot",
  "run.updated",
  "assistant.delta",
  "tool.updated",
  "interaction.requested",
  "entry.committed",
])

function compressTimings(events: DemoTimelineItem[]) {
  if (events.length === 0) return []
  const delays = [0]

  for (let index = 1; index < events.length; index += 1) {
    const rawGap = events[index].t - events[index - 1].t
    const event = events[index]
    if (event.kind === "agent" && event.event.type === "assistant.delta") {
      delays.push(DELTA_GAP_MS)
    } else if (
      event.kind === "pipeline" ||
      (event.kind === "agent" && event.event.type === "run.updated")
    ) {
      delays.push(Math.min(rawGap, TRANSITION_PAUSE_MS))
    } else {
      delays.push(Math.min(rawGap, MAX_GAP_MS))
    }
  }

  return delays
}

export function parseNDJSON(text: string): DemoTimelineItem[] {
  return text
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => {
      try {
        return JSON.parse(line) as unknown
      } catch {
        return null
      }
    })
    .filter(isDemoTimelineItem)
}

function isDemoTimelineItem(value: unknown): value is DemoTimelineItem {
  if (!value || typeof value !== "object") return false
  const item = value as Record<string, unknown>
  if (typeof item.t !== "number") return false
  if (item.kind === "pipeline") {
    return typeof item.status === "string" && "dag" in item
  }
  if (item.kind !== "agent" || !item.event || typeof item.event !== "object") {
    return false
  }
  const event = item.event as Record<string, unknown>
  return (
    typeof event.type === "string" &&
    AGENT_EVENT_TYPES.has(event.type as AgentEvent["type"])
  )
}

export type ReplayCallbacks = {
  onEvent: (event: DemoTimelineItem, index: number, total: number) => void
  onFinish: () => void
}

export function scheduleReplay(
  events: DemoTimelineItem[],
  callbacks: ReplayCallbacks,
) {
  const delays = compressTimings(events)
  const timers: ReturnType<typeof setTimeout>[] = []
  let cumulativeDelay = 0

  for (let index = 0; index < events.length; index += 1) {
    cumulativeDelay += delays[index]
    timers.push(
      setTimeout(() => {
        callbacks.onEvent(events[index], index, events.length)
        if (index === events.length - 1) callbacks.onFinish()
      }, cumulativeDelay),
    )
  }

  return () => timers.forEach(clearTimeout)
}

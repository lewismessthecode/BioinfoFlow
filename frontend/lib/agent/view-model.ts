import type {
  HistoryEntry,
  InteractionResponse,
  PlanEntry,
  ToolProgressView,
  ToolResultPart,
} from "@/lib/agent/contracts"

export function buildTranscriptView(entries: HistoryEntry[]) {
  const toolResultsByCallId = new Map<string, ToolResultPart>()
  const consumedToolCallIds = new Set<string>()
  const interactionResponses = new Map<string, InteractionResponse>()
  const latestPlans = new Map<string, PlanEntry>()
  const lastEntryIdsByRun = new Map<string, string>()
  const toolCallEntryIdsByCallId = new Map<string, string>()
  const sortedEntries = [...entries].sort((left, right) =>
    left.sequence === right.sequence
      ? left.created_at.localeCompare(right.created_at)
      : left.sequence - right.sequence,
  )

  for (const entry of sortedEntries) {
    if (entry.run_id) lastEntryIdsByRun.set(entry.run_id, entry.id)
    if (entry.type === "message") {
      for (const part of entry.payload.parts) {
        if (part.type === "tool_result") {
          toolResultsByCallId.set(part.call_id, part)
        }
        if (part.type === "tool_call") {
          consumedToolCallIds.add(part.call_id)
          toolCallEntryIdsByCallId.set(part.call_id, entry.id)
        }
      }
    }

    if (entry.type === "interaction_response") {
      interactionResponses.set(
        entry.payload.interaction_id,
        entry.payload.response,
      )
    }

    if (entry.type === "plan") {
      const latest = latestPlans.get(entry.payload.plan_id)
      if (
        !latest ||
        entry.payload.revision > latest.payload.revision ||
        (entry.payload.revision === latest.payload.revision &&
          entry.sequence > latest.sequence)
      ) {
        latestPlans.set(entry.payload.plan_id, entry)
      }
    }
  }

  return {
    entries: sortedEntries,
    toolResultsByCallId,
    toolCallEntryIdsByCallId,
    visibleMessagePartsByEntryId: new Map(
      sortedEntries.flatMap((entry) => {
        if (entry.type !== "message") return []
        const parts =
          entry.payload.role === "tool"
            ? entry.payload.parts.filter(
                (part) =>
                  part.type !== "tool_result" ||
                  !consumedToolCallIds.has(part.call_id),
              )
            : entry.payload.parts
        return [[entry.id, parts] as const]
      }),
    ),
    interactionResponses,
    lastEntryIdsByRun,
    latestPlanEntryIds: new Map(
      [...latestPlans].map(([planId, entry]) => [planId, entry.id]),
    ),
  }
}

export function scopeLiveToolsByEntry(
  liveToolsByCallId: ReadonlyMap<string, ToolProgressView>,
  toolCallEntryIdsByCallId: ReadonlyMap<string, string>,
) {
  const result = new Map<string, Map<string, ToolProgressView>>()
  for (const [callId, tool] of liveToolsByCallId) {
    const entryId = toolCallEntryIdsByCallId.get(callId)
    if (!entryId) continue
    const entryTools = result.get(entryId)
    if (entryTools) {
      entryTools.set(callId, tool)
    } else {
      result.set(entryId, new Map([[callId, tool]]))
    }
  }
  return result
}

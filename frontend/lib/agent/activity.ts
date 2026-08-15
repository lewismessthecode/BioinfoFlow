import type {
  AssistantDraftPartView,
  HistoryEntry,
  ToolProgressView,
} from "@/lib/agent/contracts"

export type ActiveActivityItem =
  | {
      kind: "thinking"
      key: string
      part: AssistantDraftPartView
    }
  | {
      kind: "response"
      key: string
      part: AssistantDraftPartView
    }
  | {
      kind: "tool_group"
      key: string
      tools: ToolProgressView[]
    }

const EMPTY_DURABLE_TOOL_CALL_IDS = new Set<string>()

export function buildActiveActivity(
  draftParts: AssistantDraftPartView[],
  tools: ToolProgressView[],
  durableToolCallIds: ReadonlySet<string> = EMPTY_DURABLE_TOOL_CALL_IDS,
): ActiveActivityItem[] {
  const activity: ActiveActivityItem[] = draftParts.map((part) => ({
    kind: part.type === "reasoning_summary" ? "thinking" : "response",
    key: `draft:${part.id}`,
    part,
  }))

  for (const tool of tools) {
    if (durableToolCallIds.has(tool.call_id)) continue

    const previous = activity.at(-1)
    if (
      previous?.kind === "tool_group" &&
      previous.tools.at(-1)?.group_id === tool.group_id
    ) {
      previous.tools.push(tool)
      continue
    }

    activity.push({
      kind: "tool_group",
      key: `tool:${tool.group_id}:${tool.call_id}`,
      tools: [tool],
    })
  }

  return activity
}

export function collectDurableToolCallIds(entries: HistoryEntry[]) {
  const callIds = new Set<string>()

  for (const entry of entries) {
    if (entry.type !== "message") continue
    for (const part of entry.payload.parts) {
      if (part.type === "tool_call") callIds.add(part.call_id)
    }
  }

  return callIds
}

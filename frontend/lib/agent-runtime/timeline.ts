import { buildTurnSegments } from "./segments"
import type {
  AgentRuntimeDecisionSegment,
  AgentRuntimeEvent,
  AgentRuntimeInlinePlanStatus,
  AgentRuntimeTextBlock,
  AgentRuntimeTimelineEntry,
  AgentRuntimeToolCallState,
  AgentRuntimeTranscriptSegment,
  AgentRuntimeTurn,
} from "./types"

export function buildAgentRuntimeTimeline(
  turns: AgentRuntimeTurn[],
  events: AgentRuntimeEvent[],
): AgentRuntimeTimelineEntry[] {
  const sortedEvents = [...events].sort(
    (a, b) =>
      a.seq - b.seq ||
      a.created_at.localeCompare(b.created_at) ||
      a.id.localeCompare(b.id),
  )

  return turns.map((turn) => {
    const turnEvents = sortedEvents.filter((event) => event.turn_id === turn.id)
    const segments = buildTurnSegments(turn, turnEvents)
    const textBlocks = textBlocksFromSegments(segments)
    const thinkingBlocks = thinkingBlocksFromSegments(segments)
    const activityGroups = segments
      .filter((segment) => segment.kind === "activity_group")
      .map((segment) => segment.activityGroup)
    const activities = activityGroups.flatMap((group) => group.activities)
    const inlinePlans = segments
      .filter((segment): segment is AgentRuntimeDecisionSegment => segment.kind === "decision")
      .filter((segment) => segment.decision.interaction?.kind === "plan_approval")
      .map((segment) => ({
        actionId: segment.decision.actionId,
        plan:
          segment.decision.interaction?.kind === "plan_approval"
            ? segment.decision.interaction.plan
            : "",
        status: inlinePlanStatus(segment.decision.state),
      }))

    return {
      turn,
      assistant: {
        messageId: latestMessageId(turnEvents),
        text: textBlocks.map((block) => block.text).join("\n\n"),
        textBlocks,
        status: assistantStatus(turn, textBlocks),
        errorMessage: latestErrorMessage(turn, turnEvents),
        thinking: thinkingBlocks.length
          ? {
              content: thinkingBlocks.map((block) => block.content).join("\n\n"),
              isComplete: thinkingBlocks.every((block) => block.isComplete),
            }
          : null,
        thinkingBlocks,
        toolCalls: buildToolCalls(turnEvents),
      },
      activities,
      activityGroups,
      inlinePlans,
      segments,
    } satisfies AgentRuntimeTimelineEntry
  })
}

function textBlocksFromSegments(segments: AgentRuntimeTranscriptSegment[]) {
  return segments
    .filter((segment) => segment.kind === "assistant_text")
    .map((segment) => segment.textBlock)
}

function thinkingBlocksFromSegments(segments: AgentRuntimeTranscriptSegment[]) {
  return segments
    .filter((segment) => segment.kind === "assistant_thinking")
    .map((segment) => segment.thinkingBlock)
}

function assistantStatus(
  turn: AgentRuntimeTurn,
  textBlocks: AgentRuntimeTextBlock[],
): AgentRuntimeTimelineEntry["assistant"]["status"] {
  if (turn.status === "failed") return "failed"
  if (turn.status === "cancelled") return "cancelled"
  if (turn.status === "completed") return "completed"
  if (textBlocks.some((block) => block.status === "streaming")) return "streaming"
  if (textBlocks.some((block) => block.status === "completed")) return "completed"
  return initialAssistantStatus(turn)
}

function initialAssistantStatus(
  turn: AgentRuntimeTurn,
): AgentRuntimeTimelineEntry["assistant"]["status"] {
  switch (turn.status) {
    case "completed":
      return "completed"
    case "failed":
      return "failed"
    case "cancelled":
      return "cancelled"
    case "queued":
    case "running":
    case "waiting_approval":
    case "waiting_user":
      return "pending"
  }
}

function buildToolCalls(events: AgentRuntimeEvent[]) {
  const toolCalls: AgentRuntimeToolCallState[] = []
  for (const event of events) {
    if (
      event.type !== "assistant.tool_call.started" &&
      event.type !== "assistant.tool_call.delta" &&
      event.type !== "assistant.tool_call.completed"
    ) {
      continue
    }
    upsertToolCall(toolCalls, event)
  }
  return toolCalls
}

function upsertToolCall(toolCalls: AgentRuntimeToolCallState[], event: AgentRuntimeEvent) {
  const callId = String(event.payload.call_id || "")
  const index = Number(event.payload.index || 0)
  const existing = toolCalls.find((item) => item.callId === callId) ?? null
  const next: AgentRuntimeToolCallState = {
    callId,
    name: String(event.payload.name || existing?.name || ""),
    status: String(event.payload.status || existing?.status || "building"),
    index,
    arguments: isRecord(event.payload.arguments) ? event.payload.arguments : existing?.arguments,
    argumentsDelta: stringOrNull(event.payload.arguments_delta) ?? existing?.argumentsDelta ?? null,
  }
  if (!existing) {
    toolCalls.push(next)
    toolCalls.sort((a, b) => a.index - b.index)
    return
  }
  Object.assign(existing, next)
}

function latestMessageId(events: AgentRuntimeEvent[]) {
  let messageId: string | null = null
  for (const event of events) {
    messageId = stringOrNull(event.payload.message_id) ?? messageId
  }
  return messageId
}

function latestErrorMessage(turn: AgentRuntimeTurn, events: AgentRuntimeEvent[]) {
  let errorMessage = turn.error_message ?? null
  for (const event of events) {
    if (event.type !== "turn.failed") continue
    errorMessage = stringOrNull(event.payload.error_message) ?? errorMessage
  }
  return errorMessage
}

function inlinePlanStatus(state: AgentRuntimeDecisionSegment["decision"]["state"]): AgentRuntimeInlinePlanStatus {
  switch (state) {
    case "approved":
    case "completed":
      return "approved"
    case "answered":
      return "answered"
    case "rejected":
    case "failed":
    case "cancelled":
      return "rejected"
    case "pending":
      return "pending"
  }
}

function stringOrNull(value: unknown) {
  return typeof value === "string" ? value : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

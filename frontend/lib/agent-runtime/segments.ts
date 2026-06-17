import { classifyActivity } from "./activity-groups"
import { buildAgentRuntimeToolActivities } from "./tool-activity"
import type {
  AgentActionDecision,
  AgentAskUserQuestion,
  AgentRuntimeActivityGroup,
  AgentRuntimeDecisionState,
  AgentRuntimeDecisionView,
  AgentRuntimeEvent,
  AgentRuntimeTextBlock,
  AgentRuntimeTextBlockStatus,
  AgentRuntimeThinkingBlock,
  AgentRuntimeToolActivity,
  AgentRuntimeToolActivityStatus,
  AgentRuntimeTranscriptSegment,
  AgentRuntimeTurn,
  AgentWaitingDecision,
} from "./types"

export function buildTurnSegments(
  turn: AgentRuntimeTurn,
  events: AgentRuntimeEvent[],
  decisionResolverEvents: AgentRuntimeEvent[] = events,
): AgentRuntimeTranscriptSegment[] {
  const sortedEvents = sortEvents(events)
  const sortedDecisionResolverEvents =
    decisionResolverEvents === events ? sortedEvents : sortEvents(decisionResolverEvents)
  const textBlocks = buildTextBlocks(turn, sortedEvents)
  const thinkingBlocks = buildThinkingBlocks(turn, sortedEvents)
  const activities = buildAgentRuntimeToolActivities(sortedEvents)
  const activitySegments = activities.map((activity, index) =>
    activityGroupSegment(turn.id, activity, index),
  )
  const decisionSegments = buildDecisionSegments(
    turn.id,
    sortedEvents,
    sortedDecisionResolverEvents,
  )
  const errorSegment = buildTurnErrorSegment(turn, sortedEvents)

  return mergeAdjacentActivitySegments(
    [
      ...thinkingBlocks.map((thinkingBlock): AgentRuntimeTranscriptSegment => ({
        id: thinkingBlock.id,
        turnId: turn.id,
        kind: "assistant_thinking",
        seqStart: thinkingBlock.seqStart,
        seqEnd: thinkingBlock.seqEnd,
        status: thinkingBlock.isComplete ? "completed" : "streaming",
        thinkingBlock,
      })),
      ...textBlocks.map((textBlock): AgentRuntimeTranscriptSegment => ({
        id: textBlock.id,
        turnId: turn.id,
        kind: "assistant_text",
        seqStart: textBlock.seqStart,
        seqEnd: textBlock.seqEnd,
        status: textBlock.status,
        textBlock,
      })),
      ...activitySegments,
      ...decisionSegments,
      ...(errorSegment ? [errorSegment] : []),
    ].sort(compareSegments),
  )
}

function buildTextBlocks(
  turn: AgentRuntimeTurn,
  events: AgentRuntimeEvent[],
): AgentRuntimeTextBlock[] {
  type TextDraft = AgentRuntimeTextBlock & { sawCumulative: boolean }
  const blocks: TextDraft[] = []
  const byKey = new Map<string, TextDraft>()
  const activeKeyByMessage = new Map<string, string>()
  const interruptedMessages = new Set<string>()
  let syntheticKey: string | null = null
  let previousWasText = false

  for (const event of events) {
    if (!isTextEvent(event)) {
      const messageId = stringValue(event.payload.message_id)
      if (messageId) interruptedMessages.add(messageId)
      previousWasText = false
      continue
    }

    const messageId = stringValue(event.payload.message_id)
    let key: string
    if (messageId) {
      const shouldStartNewBlock = interruptedMessages.has(messageId)
      key = shouldStartNewBlock
        ? `message:${messageId}:seq:${event.seq}:${event.id}`
        : activeKeyByMessage.get(messageId) ?? `message:${messageId}`
      activeKeyByMessage.set(messageId, key)
      interruptedMessages.delete(messageId)
      syntheticKey = null
    } else {
      if (!previousWasText || !syntheticKey) {
        syntheticKey = `synthetic:${event.seq}:${event.id}`
      }
      key = syntheticKey
    }
    previousWasText = true
    const existing = byKey.get(key)
    const block = existing ?? {
      id: `text:${turn.id}:${key}`,
      turnId: turn.id,
      messageId,
      seqStart: event.seq,
      seqEnd: event.seq,
      text: "",
      status: "streaming" as AgentRuntimeTextBlockStatus,
      source: "events" as const,
      sawCumulative: false,
    }
    const cumulative = firstStringPayload(event.payload, ["content", "text"])
    const delta = firstStringPayload(event.payload, ["delta", "text_delta"])
    if (cumulative !== null) {
      block.text = cumulative
      block.sawCumulative = true
    } else if (delta !== null) {
      block.text = `${block.text}${delta}`
    }
    block.seqStart = Math.min(block.seqStart, event.seq)
    block.seqEnd = Math.max(block.seqEnd, event.seq)
    block.status = event.type === "assistant.text.completed" ? "completed" : "streaming"
    if (!existing) {
      byKey.set(key, block)
      blocks.push(block)
    }
  }

  const visibleBlocks = trimCumulativeTextOverlaps(
    blocks.filter((block) => block.text.length > 0),
  )
  const snapshotText = turn.final_text ?? ""
  if (!snapshotText) return finalizeTextBlocks(turn, visibleBlocks)

  if (!visibleBlocks.length) {
    return [snapshotTextBlock(turn, events, snapshotText)]
  }

  const hasAuthoritativeEventText = visibleBlocks.some((block) => block.sawCumulative)
  const eventTextReconstructsSnapshot = textBlocksContainSnapshot(visibleBlocks, snapshotText)
  const duplicatesSnapshot = visibleBlocks.some(
    (block) => block.text.trim() === snapshotText.trim(),
  )
  if (!hasAuthoritativeEventText && !duplicatesSnapshot && !eventTextReconstructsSnapshot) {
    return finalizeTextBlocks(turn, [snapshotTextBlock(turn, events, snapshotText), ...visibleBlocks])
  }
  return finalizeTextBlocks(turn, visibleBlocks)
}

function finalizeTextBlocks(
  turn: AgentRuntimeTurn,
  blocks: Array<AgentRuntimeTextBlock & { sawCumulative?: boolean }>,
): AgentRuntimeTextBlock[] {
  return blocks
    .map((block) => {
      const textBlock: AgentRuntimeTextBlock = {
        id: block.id,
        turnId: block.turnId,
        messageId: block.messageId,
        seqStart: block.seqStart,
        seqEnd: block.seqEnd,
        text: block.text,
        status: block.status,
        source: block.source,
      }
      if (turn.status === "failed") return { ...textBlock, status: "failed" as const }
      if (turn.status === "cancelled") return { ...textBlock, status: "cancelled" as const }
      return textBlock
    })
    .sort((a, b) => a.seqStart - b.seqStart || a.id.localeCompare(b.id))
}

function trimCumulativeTextOverlaps(
  blocks: TextDraftForDedupe[],
): TextDraftForDedupe[] {
  const visible: TextDraftForDedupe[] = []
  for (const block of blocks) {
    const previous = visible.at(-1)
    if (previous && block.sawCumulative) {
      const nextText = stripRepeatedPrefix(block.text, previous.text)
      if (!nextText) continue
      visible.push({ ...block, text: nextText })
      continue
    }
    visible.push(block)
  }
  return visible
}

type TextDraftForDedupe = AgentRuntimeTextBlock & { sawCumulative?: boolean }

function stripRepeatedPrefix(text: string, prefix: string) {
  if (text.trim() === prefix.trim()) return ""
  if (!text.startsWith(prefix)) return text
  return text.slice(prefix.length).replace(/^\s+/, "")
}

function textBlocksContainSnapshot(
  blocks: TextDraftForDedupe[],
  snapshotText: string,
) {
  const snapshot = snapshotText.trim()
  if (!snapshot) return false
  const concatenated = blocks.map((block) => block.text).join("").trim()
  const paragraphJoined = blocks.map((block) => block.text).join("\n\n").trim()
  return concatenated === snapshot || paragraphJoined === snapshot
}

function snapshotTextBlock(
  turn: AgentRuntimeTurn,
  events: AgentRuntimeEvent[],
  text: string,
): AgentRuntimeTextBlock {
  const firstEventSeq = events[0]?.seq ?? 1
  const seq = firstEventSeq - 0.5
  return {
    id: `text:${turn.id}:snapshot`,
    turnId: turn.id,
    messageId: null,
    seqStart: seq,
    seqEnd: seq,
    text,
    status: textStatusFromTurn(turn),
    source: "snapshot",
  }
}

function buildThinkingBlocks(
  turn: AgentRuntimeTurn,
  events: AgentRuntimeEvent[],
): AgentRuntimeThinkingBlock[] {
  const blocks: AgentRuntimeThinkingBlock[] = []
  const byKey = new Map<string, AgentRuntimeThinkingBlock>()
  let syntheticKey: string | null = null
  let previousWasThinking = false

  for (const event of events) {
    if (!isThinkingEvent(event)) {
      previousWasThinking = false
      continue
    }
    const messageId = stringValue(event.payload.message_id)
    const sourceId = stringValue(event.payload.source_id)
    if (messageId || sourceId) {
      syntheticKey = null
    } else if (!previousWasThinking || !syntheticKey) {
      syntheticKey = `synthetic:${event.seq}:${event.id}`
    }
    previousWasThinking = true
    const key = messageId
      ? `message:${messageId}`
      : sourceId
        ? `source:${sourceId}`
        : syntheticKey!
    const existing = byKey.get(key)
    const block = existing ?? {
      id: `thinking:${turn.id}:${key}`,
      turnId: turn.id,
      messageId,
      seqStart: event.seq,
      seqEnd: event.seq,
      content: "",
      isComplete: false,
    }
    const cumulative = firstStringPayload(event.payload, ["content", "text", "summary"])
    const delta = firstStringPayload(event.payload, ["delta", "text_delta"])
    if (cumulative !== null) {
      block.content = cumulative
    } else if (delta !== null) {
      block.content = `${block.content}${delta}`
    }
    block.seqStart = Math.min(block.seqStart, event.seq)
    block.seqEnd = Math.max(block.seqEnd, event.seq)
    block.isComplete = event.type !== "assistant.thinking.delta"
    if (!existing) {
      byKey.set(key, block)
      blocks.push(block)
    }
  }

  return blocks
    .filter((block) => block.content.length > 0)
    .sort((a, b) => a.seqStart - b.seqStart || a.id.localeCompare(b.id))
}

function buildDecisionSegments(
  turnId: string,
  events: AgentRuntimeEvent[],
  resolverEvents: AgentRuntimeEvent[],
): AgentRuntimeTranscriptSegment[] {
  const byActionId = new Map<string, AgentRuntimeDecisionView>()

  for (const event of events) {
    if (event.type !== "action.waiting_decision") continue
    const actionId = stringValue(event.payload.action_id)
    if (!actionId) continue
    const decision = parseWaitingDecision(event)
    if (!decision.actionId) continue
    byActionId.set(actionId, {
      ...decision,
      state: "pending",
      turnId,
      seqStart: event.seq,
      seqEnd: event.seq,
      scrollTargetId: decisionScrollTargetId(actionId),
    })
  }

  for (const event of resolverEvents) {
    const actionId = stringValue(event.payload.action_id)
    if (!actionId) continue
    const existing = byActionId.get(actionId)
    if (!existing || event.seq < existing.seqStart) continue

    if (event.type === "action.decision_recorded") {
      existing.state = decisionState(event)
      existing.seqEnd = Math.max(existing.seqEnd, event.seq)
      continue
    }

    if (event.type === "action.failed") {
      existing.state = "failed"
      existing.seqEnd = Math.max(existing.seqEnd, event.seq)
      continue
    }

    if (event.type === "action.cancelled") {
      existing.state = "cancelled"
      existing.seqEnd = Math.max(existing.seqEnd, event.seq)
      continue
    }

    if (event.type === "action.completed") {
      if (existing.state !== "rejected" && existing.state !== "failed" && existing.state !== "cancelled") {
        existing.state = "completed"
      }
      existing.seqEnd = Math.max(existing.seqEnd, event.seq)
    }
  }

  return [...byActionId.values()].map((decision): AgentRuntimeTranscriptSegment => ({
    id: decision.scrollTargetId,
    turnId,
    kind: "decision",
    seqStart: decision.seqStart,
    seqEnd: decision.seqEnd,
    status: decision.state,
    decision,
  }))
}

function buildTurnErrorSegment(
  turn: AgentRuntimeTurn,
  events: AgentRuntimeEvent[],
): AgentRuntimeTranscriptSegment | null {
  const terminalEvent = [...events]
    .reverse()
    .find((event) => ["turn.failed", "turn.cancelled", "turn.interrupted"].includes(event.type))

  if (terminalEvent) {
    const status = terminalEvent.type === "turn.failed" ? "failed" : "cancelled"
    return {
      id: `turn-error:${turn.id}:${terminalEvent.id}`,
      turnId: turn.id,
      kind: "turn_error",
      seqStart: terminalEvent.seq,
      seqEnd: terminalEvent.seq,
      status,
      message: stringValue(terminalEvent.payload.error_message) ?? turn.error_message ?? null,
    }
  }

  if (turn.status !== "failed" && turn.status !== "cancelled") return null
  const lastSeq = events.at(-1)?.seq ?? 1
  return {
    id: `turn-error:${turn.id}:snapshot`,
    turnId: turn.id,
    kind: "turn_error",
    seqStart: lastSeq + 0.5,
    seqEnd: lastSeq + 0.5,
    status: turn.status,
    message: turn.error_message ?? null,
  }
}

function activityGroupSegment(
  turnId: string,
  activity: AgentRuntimeToolActivity,
  index: number,
): AgentRuntimeTranscriptSegment {
  const kind = classifyActivity(activity)
  const activityGroup: AgentRuntimeActivityGroup = {
    id: `${kind}-${activity.seqStart}-${index}`,
    kind,
    status: activity.status,
    activities: [activity],
    seqStart: activity.seqStart,
    seqEnd: activity.seqEnd,
  }
  return {
    id: `activity:${activityGroup.id}`,
    turnId,
    kind: "activity_group",
    seqStart: activityGroup.seqStart,
    seqEnd: activityGroup.seqEnd,
    status: activityGroup.status,
    activityGroup,
  }
}

function mergeAdjacentActivitySegments(
  segments: AgentRuntimeTranscriptSegment[],
): AgentRuntimeTranscriptSegment[] {
  const merged: AgentRuntimeTranscriptSegment[] = []
  for (const segment of segments) {
    const previous = merged.at(-1)
    if (
      previous?.kind === "activity_group" &&
      segment.kind === "activity_group" &&
      previous.activityGroup.kind === segment.activityGroup.kind
    ) {
      const activities = [
        ...previous.activityGroup.activities,
        ...segment.activityGroup.activities,
      ]
      previous.activityGroup = {
        ...previous.activityGroup,
        activities,
        status: aggregateStatus(activities),
        seqEnd: Math.max(previous.seqEnd, segment.seqEnd),
      }
      previous.seqEnd = previous.activityGroup.seqEnd
      previous.status = previous.activityGroup.status
      continue
    }
    merged.push(segment)
  }
  return merged
}

function compareSegments(
  a: AgentRuntimeTranscriptSegment,
  b: AgentRuntimeTranscriptSegment,
) {
  return (
    a.seqStart - b.seqStart ||
    segmentPriority(a.kind) - segmentPriority(b.kind) ||
    a.seqEnd - b.seqEnd ||
    a.id.localeCompare(b.id)
  )
}

function segmentPriority(kind: AgentRuntimeTranscriptSegment["kind"]) {
  switch (kind) {
    case "assistant_thinking":
      return 0
    case "assistant_text":
      return 1
    case "activity_group":
      return 2
    case "decision":
      return 3
    case "turn_error":
      return 4
  }
}

function aggregateStatus(
  activities: AgentRuntimeToolActivity[],
): AgentRuntimeToolActivityStatus {
  if (activities.some((activity) => activity.status === "failed")) return "failed"
  if (activities.some((activity) => activity.status === "cancelled")) return "cancelled"
  if (activities.some((activity) => activity.status === "rejected")) return "rejected"
  if (activities.some((activity) => activity.status === "waiting")) return "waiting"
  if (activities.some((activity) => activity.status === "running")) return "running"
  if (activities.some((activity) => activity.status === "requested")) return "requested"
  if (activities.some((activity) => activity.status === "building")) return "building"
  return "completed"
}

function sortEvents(events: AgentRuntimeEvent[]) {
  return [...events].sort(
    (a, b) =>
      a.seq - b.seq ||
      a.created_at.localeCompare(b.created_at) ||
      a.id.localeCompare(b.id),
  )
}

function textStatusFromTurn(turn: AgentRuntimeTurn): AgentRuntimeTextBlockStatus {
  if (turn.status === "failed") return "failed"
  if (turn.status === "cancelled") return "cancelled"
  if (turn.status === "completed") return "completed"
  return "streaming"
}

export function parseRuntimeWaitingDecision(event: AgentRuntimeEvent): AgentWaitingDecision {
  return parseWaitingDecision(event)
}

export function decisionScrollTargetId(actionId: string) {
  return `agent-decision-${actionId}`
}

function parseWaitingDecision(event: AgentRuntimeEvent): AgentWaitingDecision {
  const payload = event.payload ?? {}
  const raw = payload.interaction as
    | { kind?: string; questions?: unknown; plan?: unknown }
    | undefined
  let interaction: AgentWaitingDecision["interaction"] = null
  if (raw?.kind === "user_input") {
    interaction = {
      kind: "user_input",
      questions: Array.isArray(raw.questions)
        ? (raw.questions as AgentAskUserQuestion[])
        : [],
    }
  } else if (raw?.kind === "plan_approval") {
    interaction = { kind: "plan_approval", plan: String(raw.plan ?? "") }
  }
  return {
    actionId: String(payload.action_id || ""),
    name: typeof payload.name === "string" ? payload.name : undefined,
    kind: typeof payload.kind === "string" ? payload.kind : undefined,
    riskLevel: typeof payload.risk_level === "string" ? payload.risk_level : undefined,
    toolCallId:
      typeof payload.tool_call_id === "string" ? payload.tool_call_id : null,
    inputPreview:
      typeof payload.input_preview === "string" ? payload.input_preview : null,
    interaction,
  }
}

function decisionState(event: AgentRuntimeEvent): AgentRuntimeDecisionState {
  const decision = String(event.payload.decision || "") as AgentActionDecision
  if (decision === "reject") return "rejected"
  if (decision === "answer") return "answered"
  return "approved"
}

function isTextEvent(event: AgentRuntimeEvent) {
  return event.type === "assistant.text.delta" || event.type === "assistant.text.completed"
}

function isThinkingEvent(event: AgentRuntimeEvent) {
  return [
    "assistant.thinking.delta",
    "assistant.thinking.summary",
    "assistant.thinking.completed",
  ].includes(event.type)
}

function firstStringPayload(payload: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = payload[key]
    if (typeof value === "string") return value
  }
  return null
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value : null
}

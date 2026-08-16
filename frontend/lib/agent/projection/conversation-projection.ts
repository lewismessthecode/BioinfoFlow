import type { AgentStoreState } from "../store"
import { applyAgentEvent, initialAgentStoreState } from "../store"
import type {
  ActivityGroupTranscriptBlock,
  ActivityItem,
  ConversationViewModel,
  MessageReference,
  TranscriptBlock,
} from "../conversation-model/types"
import type {
  HistoryEntry,
  MessagePart,
  ToolCallPart,
  ToolResultPart,
} from "../contracts"
import {
  parsePresentationSnapshot,
  parsePresentationEvent,
  type PresentationDiagnostic,
} from "../transport/presentation-contract"

export type ConversationProjectionState = {
  transportState: AgentStoreState
  diagnostics: PresentationDiagnostic[]
}

export type ConversationProjectionResult =
  | {
      ok: true
      state: ConversationProjectionState
      view: ConversationViewModel
    }
  | { ok: false; diagnostic: PresentationDiagnostic }

export type ConversationProjectionEventResult = {
  outcome: "applied" | "ignored" | "needs_snapshot" | "diagnostic"
  state: ConversationProjectionState
  view: ConversationViewModel
}

type HistoryProjectionContext = {
  groups: Map<string, ActivityGroupTranscriptBlock>
  calls: Map<string, { groupKey: string; activity: ActivityItem }>
}

const COMPOSER_CAPABILITIES = {
  modelSelection: true,
  permissionSelection: true,
  environmentSelection: { auto: true, manualMultiSelect: true },
  planMode: false,
} as const

export function createConversationProjection(
  input: unknown,
): ConversationProjectionResult {
  const parsed = parsePresentationSnapshot(input)
  if (!parsed.ok) return parsed
  const snapshot = parsed.value.snapshot
  const state: ConversationProjectionState = {
    transportState: {
      ...initialAgentStoreState,
      session: snapshot.session,
      runs: snapshot.runs,
      entries: snapshot.entries,
      activeRun: snapshot.active_run,
    },
    diagnostics: [],
  }
  return {
    ok: true,
    state,
    view: projectConversationView(state, parsed.value.protocolVersion),
  }
}

export function applyConversationProjectionEvent(
  current: ConversationProjectionState,
  input: unknown,
): ConversationProjectionEventResult {
  const parsed = parsePresentationEvent(input)
  if (!parsed.ok) {
    return applyConversationProjectionDiagnostic(current, parsed.diagnostic)
  }
  const application = applyAgentEvent(current.transportState, parsed.value.event)
  if (application.outcome === "needs_snapshot") {
    const diagnostic: PresentationDiagnostic = {
      code: "event_gap",
      message: `Agent presentation event requires a fresh snapshot: ${parsed.value.event.type}`,
      originalType: parsed.value.event.type,
    }
    const state = appendDiagnostic(current, diagnostic)
    return {
      outcome: "needs_snapshot",
      state,
      view: projectConversationView(state),
    }
  }
  const state = { ...current, transportState: application.state }
  return {
    outcome: application.outcome,
    state,
    view: projectConversationView(state),
  }
}

export function applyConversationProjectionDiagnostic(
  current: ConversationProjectionState,
  diagnostic: PresentationDiagnostic,
): ConversationProjectionEventResult {
  const state = appendDiagnostic(current, diagnostic)
  return {
    outcome: "diagnostic",
    state,
    view: projectConversationView(state),
  }
}

function projectConversationView(
  state: ConversationProjectionState,
  protocolVersion = 1,
): ConversationViewModel {
  const session = state.transportState.session
  if (!session) {
    throw new Error("A Conversation projection requires an authoritative session")
  }
  return {
      protocolVersion,
      conversation: {
        id: session.id,
        title: session.title,
        status: session.status,
        workspaceId: session.workspace_id,
        projectId: session.project_id,
      },
      composer: {
        placement:
          state.transportState.runs.length || state.transportState.entries.length
            ? "docked"
            : "centered",
        canSend: session.status === "active",
        settings: {
          model: {
            provider: session.model.provider,
            model: session.model.model,
            displayName: session.model.display_name,
          },
          permissionMode: session.permission_mode,
          workspaceAccess: session.workspace_access,
          revision: session.settings_revision ?? 0,
          environmentScope: normalizeEnvironmentScope(
            session.environment_scope,
          ),
        },
        capabilities: COMPOSER_CAPABILITIES,
      },
      transcript: projectTranscript(state.transportState, state.diagnostics),
      activeWork: state.transportState.activeRun
        ? {
            runId: state.transportState.activeRun.run.id,
            status: state.transportState.activeRun.run.status as "queued" | "running" | "waiting_user",
            phase: state.transportState.activeRun.run.phase,
            startedAt: state.transportState.activeRun.run.started_at,
          }
        : null,
  }
}

function normalizeEnvironmentScope(value: unknown): {
  mode: "auto" | "manual"
  environmentIds: string[]
} {
  if (!value || typeof value !== "object") {
    return { mode: "auto", environmentIds: [] }
  }
  const scope = value as {
    mode?: unknown
    selected_environment_ids?: unknown
    environment_ids?: unknown
  }
  if (scope.mode !== "manual") return { mode: "auto", environmentIds: [] }
  const ids = Array.isArray(scope.selected_environment_ids)
    ? scope.selected_environment_ids
    : Array.isArray(scope.environment_ids)
      ? scope.environment_ids
      : []
  return {
    mode: "manual",
    environmentIds: ids.filter((item): item is string => typeof item === "string"),
  }
}

function appendDiagnostic(
  state: ConversationProjectionState,
  diagnostic: PresentationDiagnostic,
): ConversationProjectionState {
  return { ...state, diagnostics: [...state.diagnostics, diagnostic] }
}

function projectTranscript(
  state: AgentStoreState,
  diagnostics: readonly PresentationDiagnostic[],
): TranscriptBlock[] {
  const transcript: TranscriptBlock[] = []
  const seenEntryIds = new Set<string>()
  const context: HistoryProjectionContext = {
    groups: new Map(),
    calls: new Map(),
  }
  const entries = [...state.entries].sort((left, right) => left.sequence - right.sequence)
  for (const entry of entries) {
    if (seenEntryIds.has(entry.id)) continue
    seenEntryIds.add(entry.id)
    transcript.push(...projectEntry(entry, state, context))
  }
  coalesceInteractions(transcript)

  for (const run of state.runs) {
    if (
      run.status !== "completed" &&
      run.status !== "failed" &&
      run.status !== "cancelled"
    ) {
      continue
    }
    transcript.push({
      type: "outcome",
      id: `run:${run.id}:outcome`,
      runId: run.id,
      createdAt: run.completed_at ?? run.updated_at,
      status: run.status,
      reason: run.termination_reason,
      error: run.error,
    })
  }
  appendActiveRun(transcript, state)
  diagnostics.forEach((diagnostic, index) => {
    transcript.push({
      type: "unknown",
      id: `diagnostic:${index}:${diagnostic.originalType}`,
      runId: null,
      createdAt: null,
      originalType: diagnostic.originalType,
      message: diagnostic.message,
      diagnosticCode: diagnostic.code,
    })
  })
  return transcript
}

function coalesceInteractions(transcript: TranscriptBlock[]) {
  const pendingIndexes = new Map<string, number>()
  for (let index = 0; index < transcript.length; index += 1) {
    const block = transcript[index]
    if (block.type !== "interaction") continue
    if (block.status === "pending") {
      pendingIndexes.set(block.interactionId, index)
      continue
    }
    const pendingIndex = pendingIndexes.get(block.interactionId)
    if (pendingIndex === undefined) continue
    const pending = transcript[pendingIndex]
    if (pending.type !== "interaction") continue
    transcript[pendingIndex] = {
      ...pending,
      status: "resolved",
      response: block.response,
    }
    transcript.splice(index, 1)
    index -= 1
  }
}

function appendActiveRun(
  transcript: TranscriptBlock[],
  state: AgentStoreState,
) {
  const activeRun = state.activeRun
  if (!activeRun) return
  const draft = activeRun.assistant_draft
  if (draft) {
    for (const part of draft.parts) {
      const partType = String(part.type)
      if (partType === "reasoning_summary" || partType === "reasoning_trace") {
        transcript.push({
          type: "reasoning",
          id: `draft:${draft.id}:${part.id}`,
          runId: activeRun.run.id,
          createdAt: activeRun.run.updated_at,
          text: part.text,
          streaming: true,
          provider: state.session?.model.provider ?? null,
          model: state.session?.model.model ?? null,
          sourceField: partType,
          truncated: false,
        })
      } else {
        transcript.push({
          type: "message",
          id: `draft:${draft.id}:${part.id}`,
          runId: activeRun.run.id,
          createdAt: activeRun.run.updated_at,
          role: "assistant",
          text: part.text,
          references: [],
          streaming: true,
        })
      }
    }
  }

  const groups = new Map<string, ActivityGroupTranscriptBlock>()
  for (const tool of activeRun.tool_progress) {
    let group = groups.get(tool.group_id)
    if (!group) {
      group = {
        type: "activity_group",
        id: `active:${activeRun.run.id}:activity:${tool.group_id}`,
        runId: activeRun.run.id,
        createdAt: tool.started_at ?? activeRun.run.updated_at,
        executionMode: tool.execution_mode,
        activities: [],
      }
      groups.set(tool.group_id, group)
      transcript.push(group)
    }
    group.activities.push({
      id: `active:${activeRun.run.id}:tool:${tool.call_id}`,
      callId: tool.call_id,
      name: tool.name,
      displayName: tool.display_name,
      category: tool.category,
      summary: tool.summary,
      status: tool.status,
      input: tool.arguments,
      output: tool.output_summary,
      error: tool.error,
      startedAt: tool.started_at,
      completedAt: tool.completed_at,
    })
  }
  const interaction = activeRun.pending_interaction
  if (interaction) {
    transcript.push({
      type: "interaction",
      id: `active:${activeRun.run.id}:interaction:${interaction.interaction_id}`,
      runId: activeRun.run.id,
      createdAt: activeRun.run.updated_at,
      interactionId: interaction.interaction_id,
      status: "pending",
      request: interaction.request,
      response: null,
    })
  }
}

function projectEntry(
  entry: HistoryEntry,
  state: AgentStoreState,
  context: HistoryProjectionContext,
): TranscriptBlock[] {
  if (entry.schema_version !== 1 && entry.schema_version !== 2) {
    return [unknownEntry(entry, "unsupported_entry_version")]
  }
  switch (entry.type) {
    case "message":
      return projectMessageEntry(entry, state, context)
    case "notice":
      return [
        {
          type: "notice",
          id: entry.id,
          runId: entry.run_id,
          createdAt: entry.created_at,
          code: entry.payload.code,
          message: entry.payload.message,
          details: entry.payload.details,
        },
      ]
    case "interaction_request":
      return [
        {
          type: "interaction",
          id: entry.id,
          runId: entry.run_id,
          createdAt: entry.created_at,
          interactionId: entry.payload.interaction_id,
          status: "pending",
          request: entry.payload.request,
          response: null,
        },
      ]
    case "interaction_response":
      return [
        {
          type: "interaction",
          id: entry.id,
          runId: entry.run_id,
          createdAt: entry.created_at,
          interactionId: entry.payload.interaction_id,
          status: "resolved",
          request: null,
          response: entry.payload.response,
        },
      ]
    case "plan":
      return [
        {
          type: "plan",
          id: entry.id,
          runId: entry.run_id,
          createdAt: entry.created_at,
          planId: entry.payload.plan_id,
          revision: entry.payload.revision,
          title: entry.payload.title ?? null,
          items: entry.payload.items,
          updatedAt: entry.payload.updated_at,
        },
      ]
    default:
      return [unknownEntry(entry, "unknown_history_entry")]
  }
}

function projectMessageEntry(
  entry: Extract<HistoryEntry, { type: "message" }>,
  state: AgentStoreState,
  context: HistoryProjectionContext,
): TranscriptBlock[] {
  const blocks: TranscriptBlock[] = []
  for (const part of entry.payload.parts) {
    const currentPart = part as unknown as {
      id: string
      type: string
      text?: unknown
      provider?: unknown
      model?: unknown
      source?: unknown
      truncated?: unknown
    }
    if (currentPart.type === "reasoning_trace") {
      blocks.push({
        type: "reasoning",
        id: `${entry.id}:${currentPart.id}`,
        runId: entry.run_id,
        createdAt: entry.created_at,
        text: typeof currentPart.text === "string" ? currentPart.text : "",
        streaming: false,
        provider:
          typeof currentPart.provider === "string" ? currentPart.provider : null,
        model: typeof currentPart.model === "string" ? currentPart.model : null,
        sourceField:
          typeof currentPart.source === "string"
            ? currentPart.source
            : "reasoning_trace",
        truncated: currentPart.truncated === true,
      })
      continue
    }
    switch (part.type) {
      case "text":
        blocks.push({
          type: "message",
          id: `${entry.id}:${part.id}`,
          runId: entry.run_id,
          createdAt: entry.created_at,
          role: entry.payload.role,
          text: part.text,
          references: [],
          streaming: false,
        })
        break
      case "reasoning_summary":
        blocks.push({
          type: "reasoning",
          id: `${entry.id}:${part.id}`,
          runId: entry.run_id,
          createdAt: entry.created_at,
          text: part.text,
          streaming: false,
          provider: state.session?.model.provider ?? null,
          model: state.session?.model.model ?? null,
          sourceField: "reasoning_summary",
          truncated: false,
        })
        break
      case "tool_call":
        projectToolCall(entry, part, blocks, context)
        break
      case "tool_result":
        projectToolResult(entry, part, blocks, context)
        break
      case "artifact_ref":
        blocks.push({
          type: "artifact",
          id: `${entry.id}:${part.id}`,
          runId: entry.run_id,
          createdAt: entry.created_at,
          artifactId: part.artifact_id,
          title: part.title,
          mediaType: part.media_type,
        })
        break
      case "attachment_ref":
      case "file_ref":
      case "directory_ref":
      case "workflow_ref":
      case "run_ref":
        appendReference(blocks, entry, part)
        break
      case "unknown":
        blocks.push({
          type: "unknown",
          id: `${entry.id}:${part.id}`,
          runId: entry.run_id,
          createdAt: entry.created_at,
          originalType: part.original_type,
          message: part.display_text,
          diagnosticCode: "unknown_message_part",
        })
        break
      default: {
        const unknownPart = part as unknown as {
          id?: unknown
          type?: unknown
        }
        const originalType =
          typeof unknownPart.type === "string" ? unknownPart.type : "unknown"
        const partId =
          typeof unknownPart.id === "string" ? unknownPart.id : originalType
        blocks.push({
          type: "unknown",
          id: `${entry.id}:${partId}`,
          runId: entry.run_id,
          createdAt: entry.created_at,
          originalType,
          message: `This message contains unsupported content (${originalType}).`,
          diagnosticCode: "unknown_message_part",
        })
      }
    }
  }
  return blocks
}

function projectToolCall(
  entry: Extract<HistoryEntry, { type: "message" }>,
  part: ToolCallPart,
  blocks: TranscriptBlock[],
  context: HistoryProjectionContext,
) {
  const runKey = entry.run_id ?? "session"
  const groupKey = `${runKey}:${part.group_id}`
  let group = context.groups.get(groupKey)
  if (!group) {
    group = {
      type: "activity_group",
      id: `${entry.id}:activity:${part.group_id}`,
      runId: entry.run_id,
      createdAt: entry.created_at,
      executionMode: part.execution_mode,
      activities: [],
    }
    context.groups.set(groupKey, group)
    blocks.push(group)
  }
  const activity: ActivityItem = {
    id: `${entry.id}:${part.id}`,
    callId: part.call_id,
    name: part.name,
    displayName: part.display_name,
    category: part.category,
    summary: part.summary,
    status: "pending",
    input: part.arguments,
    output: null,
    error: null,
    startedAt: null,
    completedAt: null,
  }
  group.activities.push(activity)
  context.calls.set(`${runKey}:${part.call_id}`, { groupKey, activity })
}

function projectToolResult(
  entry: Extract<HistoryEntry, { type: "message" }>,
  part: ToolResultPart,
  blocks: TranscriptBlock[],
  context: HistoryProjectionContext,
) {
  const runKey = entry.run_id ?? "session"
  const callKey = `${runKey}:${part.call_id}`
  const call = context.calls.get(callKey)
  if (!call) {
    blocks.push({
      type: "unknown",
      id: `${entry.id}:${part.id}`,
      runId: entry.run_id,
      createdAt: entry.created_at,
      originalType: "orphan_tool_result",
      message: part.summary ?? "Tool result could not be matched to a tool call.",
      diagnosticCode: "orphan_tool_result",
    })
    return
  }
  const group = context.groups.get(call.groupKey)
  const activityIndex = group?.activities.indexOf(call.activity) ?? -1
  if (!group || activityIndex < 0) return
  const activity = {
    ...call.activity,
    status: part.status,
    summary: part.summary ?? call.activity.summary,
    output: part.output,
    error: part.error,
    startedAt: part.started_at,
    completedAt: part.completed_at,
  }
  group.activities[activityIndex] = activity
  context.calls.set(callKey, { groupKey: call.groupKey, activity })
}

function appendReference(
  blocks: TranscriptBlock[],
  entry: Extract<HistoryEntry, { type: "message" }>,
  part: Exclude<
    MessagePart,
    | { type: "text" }
    | { type: "reasoning_summary" }
    | { type: "tool_call" }
    | { type: "tool_result" }
    | { type: "artifact_ref" }
    | { type: "unknown" }
  >,
) {
  const reference = toMessageReference(part)
  const previous = blocks.at(-1)
  if (previous?.type === "message" && previous.role === entry.payload.role) {
    previous.references.push(reference)
    return
  }
  blocks.push({
    type: "message",
    id: `${entry.id}:${part.id}`,
    runId: entry.run_id,
    createdAt: entry.created_at,
    role: entry.payload.role,
    text: "",
    references: [reference],
    streaming: false,
  })
}

function toMessageReference(
  part: Exclude<
    MessagePart,
    | { type: "text" }
    | { type: "reasoning_summary" }
    | { type: "tool_call" }
    | { type: "tool_result" }
    | { type: "artifact_ref" }
    | { type: "unknown" }
  >,
): MessageReference {
  switch (part.type) {
    case "attachment_ref":
      return {
        kind: "attachment",
        id: part.attachment_id,
        label: part.filename,
        path: null,
      }
    case "file_ref":
      return { kind: "file", id: part.id, label: part.label, path: part.path ?? null }
    case "directory_ref":
      return {
        kind: "directory",
        id: part.id,
        label: part.label,
        path: part.path ?? null,
      }
    case "workflow_ref":
      return {
        kind: "workflow",
        id: part.workflow_id,
        label: part.label,
        path: null,
      }
    case "run_ref":
      return { kind: "run", id: part.run_id, label: part.label, path: null }
  }
}

function unknownEntry(
  entry: HistoryEntry,
  diagnosticCode: string,
): TranscriptBlock {
  return {
    type: "unknown",
    id: entry.id,
    runId: entry.run_id,
    createdAt: entry.created_at,
    originalType: String(entry.type),
    message: `This conversation contains unsupported content (${String(entry.type)}).`,
    diagnosticCode,
  }
}

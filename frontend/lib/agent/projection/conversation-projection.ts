import type { AgentStoreState } from "../store"
import { applyAgentEvent, initialAgentStoreState } from "../store"
import type {
  ActivityGroupTranscriptBlock,
  ActivityItem,
  ConversationInteractionRequest,
  ConversationInteractionResponse,
  ConversationExecutionConfig,
  ConversationPlan,
  InteractionTranscriptBlock,
  ConversationViewModel,
  MessageReference,
  ReasoningTranscriptBlock,
  TranscriptBlock,
} from "../conversation-model/types"
import type {
  HistoryEntry,
  MessagePart,
  RunView,
  SessionView,
  ToolCallPart,
  ToolPublicDetail,
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
  interactions: Map<string, InteractionTranscriptBlock>
  hiddenCalls: Set<string>
}

type ReasoningProjectionInput = {
  id: string
  runId: string | null
  createdAt: string | null
  text: string
  streaming: boolean
  provider?: string | null
  model?: string | null
  sourceField?: string | null
  truncated?: boolean
  startedAt?: string | null
  completedAt?: string | null
  fallbackProvider?: string | null
  fallbackModel?: string | null
  fallbackSourceField: string
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
    diagnostics: parsed.value.diagnostics,
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
      params: { originalType: parsed.value.event.type },
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

export function applyConversationSessionTitle(
  current: ConversationProjectionState,
  incoming: SessionView,
): ConversationProjectionEventResult {
  const session = current.transportState.session
  const incomingTitle = incoming.title?.trim()
  if (
    !session ||
    session.id !== incoming.id ||
    session.title !== null ||
    !incomingTitle ||
    isOlderTimestamp(incoming.updated_at, session.updated_at)
  ) {
    return {
      outcome: "ignored",
      state: current,
      view: projectConversationView(current),
    }
  }
  const state = {
    ...current,
    transportState: {
      ...current.transportState,
      session: {
        ...session,
        title: incomingTitle,
        updated_at: incoming.updated_at,
      },
    },
  }
  return {
    outcome: "applied",
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

function isOlderTimestamp(incoming: string, current: string) {
  const incomingTimestamp = Date.parse(incoming)
  const currentTimestamp = Date.parse(current)
  return (
    Number.isFinite(incomingTimestamp) &&
    Number.isFinite(currentTimestamp) &&
    incomingTimestamp < currentTimestamp
  )
}

function projectConversationView(
  state: ConversationProjectionState,
  protocolVersion = 1,
): ConversationViewModel {
  const session = state.transportState.session
  if (!session) {
    throw new Error("A Conversation projection requires an authoritative session")
  }
  const runs = canonicalRuns(state.transportState.runs)
  const transportState =
    runs === state.transportState.runs
      ? state.transportState
      : { ...state.transportState, runs }
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
      transcript: projectTranscript(transportState, state.diagnostics),
      currentPlan: projectCurrentPlan(transportState),
      runs: runs.map((run) => ({
        id: run.id,
        status: run.status,
        startedAt: run.started_at,
        completedAt: run.completed_at,
        executionConfig: projectExecutionConfig(run.execution_config),
      })),
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

function canonicalRuns(
  runs: RunView[],
): RunView[] {
  const latestById = new Map<string, RunView>()
  const orderedIds: string[] = []
  for (const run of runs) {
    const current = latestById.get(run.id)
    if (!current) {
      latestById.set(run.id, run)
      orderedIds.push(run.id)
      continue
    }
    if (
      run.revision > current.revision ||
      (run.revision === current.revision && run.updated_at > current.updated_at)
    ) {
      latestById.set(run.id, run)
    }
  }
  if (orderedIds.length === runs.length) return runs
  return orderedIds.map((id) => latestById.get(id)!)
}

function projectExecutionConfig(
  config: import("../contracts").RunExecutionConfigView | null | undefined,
): ConversationExecutionConfig | null {
  if (!config) return null
  return {
    settingsRevision: config.settings_revision,
    model: {
      provider: config.model.provider,
      model: config.model.model,
      displayName: config.model.display_name,
    },
    permissionMode: config.permission_mode,
    workspaceAccess: config.workspace_access,
    environmentScope: {
      mode: config.environment_scope.mode,
      environmentIds: [...config.environment_scope.environment_ids],
    },
    environmentTargets: config.environment_targets.map((target) => ({
      environmentId: target.environment_id,
      displayName: target.display_name,
      kind: target.kind,
      host: target.host,
    })),
  }
}

function runModel(
  state: AgentStoreState,
  runId: string | null,
): { provider: string; model: string } | null {
  if (!runId) return null
  const run =
    (state.activeRun?.run.id === runId ? state.activeRun.run : null) ??
    state.runs.find((candidate) => candidate.id === runId)
  const model = run?.execution_config?.model
  return model ? { provider: model.provider, model: model.model } : null
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

function projectInteractionRequest(
  request: import("../contracts").InteractionRequest,
): ConversationInteractionRequest {
  if (request.type === "approval") {
    const rawTarget = (request as typeof request & {
      target?: {
        environment_id?: string
        display_name?: string
        kind?: string
        host?: string | null
      } | null
      environment?: {
        id?: string
        label?: string
        kind?: string
        host?: string | null
      } | null
      environment_id?: string | null
      environment_label?: string | null
      environment_kind?: string | null
      environment_host?: string | null
    })
    const nestedTarget = rawTarget.target ?? rawTarget.environment
    const targetRecord = nestedTarget as Record<string, unknown> | null
    const environmentId =
      stringField(targetRecord, "environment_id") ??
      stringField(targetRecord, "id") ??
      rawTarget.environment_id
    return {
      type: "approval",
      callId: request.call_id,
      toolName: request.tool_name,
      summary: request.summary,
      inputPreview: request.input_preview,
      allowedResponses: request.allowed_responses,
      risk: {
        level: request.risk.level,
        effects: request.risk.effects,
        reasons: request.risk.reasons,
        reasonCodes: request.risk.reason_codes ?? [],
        justification: request.risk.justification ?? null,
        affectedResources: request.risk.affected_resources,
      },
      target: environmentId
        ? {
            environmentId,
            displayName: nestedTarget
              ? stringField(targetRecord, "display_name") ??
                stringField(targetRecord, "label") ??
                environmentId
              : rawTarget.environment_label ?? environmentId,
            kind:
              (nestedTarget?.kind ?? rawTarget.environment_kind) === "ssh"
                ? "ssh"
                : "local",
            host: nestedTarget?.host ?? rawTarget.environment_host ?? null,
          }
        : null,
    }
  }
  if (request.type === "ask_user") {
    return {
      type: "ask_user",
      callId: request.call_id,
      questions: request.questions.map((question) => ({
        id: question.id,
        header: question.header,
        question: question.question,
        multiSelect: question.multi_select,
        options: question.options,
      })),
    }
  }
  return {
    type: "recovery",
    callId: request.call_id,
    toolName: request.tool_name,
    messageCode: request.message_code ?? null,
    messageParams: localizationParams(request.message_params),
    messageFallback: request.message,
    options: request.options,
  }
}

function localizationParams(value: unknown): Record<string, string | number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {}
  return Object.fromEntries(
    Object.entries(value).filter(
      (entry): entry is [string, string | number] =>
        typeof entry[1] === "string" || typeof entry[1] === "number",
    ),
  )
}

function projectInteractionResponse(
  response: import("../contracts").InteractionResponse,
): ConversationInteractionResponse {
  return response
}

function stringField(value: Record<string, unknown> | null, key: string) {
  const field = value?.[key]
  return typeof field === "string" ? field : null
}

function durationMs(startedAt: string | null, completedAt: string | null) {
  if (!startedAt || !completedAt) return null
  const milliseconds =
    new Date(completedAt).getTime() - new Date(startedAt).getTime()
  return Number.isFinite(milliseconds) && milliseconds >= 0
    ? milliseconds
    : null
}

function projectReasoningBlock(
  input: ReasoningProjectionInput,
): ReasoningTranscriptBlock {
  const startedAt = input.startedAt ?? null
  const completedAt = input.completedAt ?? null
  return {
    type: "reasoning",
    id: input.id,
    runId: input.runId,
    createdAt: input.createdAt,
    text: input.text,
    streaming: input.streaming,
    provider: input.provider ?? input.fallbackProvider ?? null,
    model: input.model ?? input.fallbackModel ?? null,
    sourceField: input.sourceField ?? input.fallbackSourceField,
    truncated: input.truncated ?? false,
    startedAt,
    completedAt,
    durationMs: durationMs(startedAt, completedAt),
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
    interactions: new Map(),
    hiddenCalls: new Set(),
  }
  const entries = [...state.entries].sort((left, right) => left.sequence - right.sequence)
  for (const entry of entries) {
    if (seenEntryIds.has(entry.id)) continue
    seenEntryIds.add(entry.id)
    transcript.push(...projectEntry(entry, state, context))
  }
  coalesceInteractions(transcript, context)
  insertExceptionalOutcomes(transcript, state.runs)
  appendActiveRun(transcript, state, context)
  diagnostics.forEach((diagnostic, index) => {
    transcript.push({
      type: "unknown",
      id: `diagnostic:${index}:${diagnostic.originalType}`,
      runId: null,
      createdAt: null,
      originalType: diagnostic.originalType,
      diagnosticCode: diagnostic.code,
      diagnosticParams: diagnostic.params,
    })
  })
  return transcript
}

function coalesceInteractions(
  transcript: TranscriptBlock[],
  context: HistoryProjectionContext,
) {
  const pendingIndexes = new Map<string, number>()
  for (let index = 0; index < transcript.length; index += 1) {
    const block = transcript[index]
    if (block.type !== "interaction") continue
    const key = interactionKey(block.runId, block.interactionId)
    if (block.status === "pending") {
      pendingIndexes.set(key, index)
      continue
    }
    const pendingIndex = pendingIndexes.get(key)
    if (pendingIndex === undefined) continue
    const pending = transcript[pendingIndex]
    if (pending.type !== "interaction") continue
    const resolved: InteractionTranscriptBlock = {
      ...pending,
      status: "resolved",
      response: block.response,
    }
    transcript[pendingIndex] = resolved
    context.interactions.set(key, resolved)
    transcript.splice(index, 1)
    index -= 1
  }
}

function insertExceptionalOutcomes(
  transcript: TranscriptBlock[],
  runs: RunView[],
) {
  for (const run of runs) {
    if (run.status !== "failed" && run.status !== "cancelled") continue
    const outcome: TranscriptBlock = {
      type: "outcome",
      id: `run:${run.id}:outcome`,
      runId: run.id,
      createdAt: run.completed_at ?? run.updated_at,
      status: run.status,
      reason: run.termination_reason,
      error: run.error,
    }
    const finalRunBlockIndex = findFinalRunBlockIndex(transcript, run.id)
    if (finalRunBlockIndex === -1) {
      transcript.push(outcome)
    } else {
      transcript.splice(finalRunBlockIndex + 1, 0, outcome)
    }
  }
}

function findFinalRunBlockIndex(
  transcript: readonly TranscriptBlock[],
  runId: string,
) {
  for (let index = transcript.length - 1; index >= 0; index -= 1) {
    if (transcript[index].runId === runId) return index
  }
  return -1
}

function appendActiveRun(
  transcript: TranscriptBlock[],
  state: AgentStoreState,
  context: HistoryProjectionContext,
) {
  const activeRun = state.activeRun
  if (!activeRun) return
  const effectiveModel = runModel(state, activeRun.run.id)
  const draft = activeRun.assistant_draft
  if (draft) {
    for (const part of draft.parts) {
      if (part.type === "reasoning_summary" || part.type === "reasoning_trace") {
        transcript.push(projectReasoningBlock({
          id: `draft:${draft.id}:${part.id}`,
          runId: activeRun.run.id,
          createdAt: activeRun.run.updated_at,
          text: part.text,
          streaming: true,
          provider: part.provider,
          model: part.model,
          sourceField: part.source,
          truncated: part.truncated,
          startedAt: part.started_at,
          completedAt: part.completed_at,
          fallbackProvider:
            effectiveModel?.provider ?? state.session?.model.provider ?? null,
          fallbackModel:
            effectiveModel?.model ?? state.session?.model.model ?? null,
          fallbackSourceField: part.type,
        }))
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

  for (const tool of activeRun.tool_progress) {
    if (tool.category === "plan") {
      continue
    }
    const runKey = activeRun.run.id
    const callKey = `${runKey}:${tool.call_id}`
    const existingCall = context.calls.get(callKey)
    if (existingCall) {
      const existingGroup = context.groups.get(existingCall.groupKey)
      const activityIndex =
        existingGroup?.activities.indexOf(existingCall.activity) ?? -1
      if (existingGroup && activityIndex >= 0) {
        const activity: ActivityItem = {
          ...existingCall.activity,
          status: tool.status,
          output: tool.output_summary ?? existingCall.activity.output,
          error: tool.error,
          startedAt: tool.started_at ?? existingCall.activity.startedAt,
          completedAt: tool.completed_at,
          details: mergeActivityDetails(
            existingCall.activity.details,
            projectActivityDetails(tool.public_details),
          ),
        }
        existingGroup.activities[activityIndex] = activity
        context.calls.set(callKey, {
          groupKey: existingCall.groupKey,
          activity,
        })
        continue
      }
    }

    const groupKey = `${runKey}:${tool.group_id}`
    let group = context.groups.get(groupKey)
    if (!group) {
      group = {
        type: "activity_group",
        id: `active:${activeRun.run.id}:activity:${tool.group_id}`,
        runId: activeRun.run.id,
        createdAt: tool.started_at ?? activeRun.run.updated_at,
        executionMode: tool.execution_mode,
        activities: [],
      }
      context.groups.set(groupKey, group)
      transcript.push(group)
    }
    const activity: ActivityItem = {
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
      details: projectActivityDetails(tool.public_details),
    }
    group.activities.push(activity)
    context.calls.set(callKey, { groupKey, activity })
  }
  const interaction = activeRun.pending_interaction
  const interactionIdentity = interaction
    ? interactionKey(activeRun.run.id, interaction.interaction_id)
    : null
  if (interaction && interactionIdentity && !context.interactions.has(interactionIdentity)) {
    const block: InteractionTranscriptBlock = {
      type: "interaction",
      id: `active:${activeRun.run.id}:interaction:${interaction.interaction_id}`,
      runId: activeRun.run.id,
      createdAt: activeRun.run.updated_at,
      interactionId: interaction.interaction_id,
      status: "pending",
      request: projectInteractionRequest(interaction.request),
      response: null,
    }
    context.interactions.set(interactionIdentity, block)
    transcript.push(block)
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
          params: localizationParams(entry.payload.params),
          fallback: entry.payload.message,
        },
      ]
    case "interaction_request":
      return projectInteractionRequestEntry(entry, context)
    case "interaction_response":
      return projectInteractionResponseEntry(entry)
    case "plan":
      return []
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
  const effectiveModel = runModel(state, entry.run_id)
  for (const part of entry.payload.parts) {
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
      case "reasoning_trace":
        blocks.push(projectReasoningBlock({
          id: `${entry.id}:${part.id}`,
          runId: entry.run_id,
          createdAt: entry.created_at,
          text: part.text,
          streaming: false,
          provider: part.provider,
          model: part.model,
          sourceField: part.source,
          truncated: part.truncated,
          startedAt: part.started_at,
          completedAt: part.completed_at,
          fallbackSourceField: "reasoning_trace",
        }))
        break
      case "reasoning_summary":
        blocks.push(projectReasoningBlock({
          id: `${entry.id}:${part.id}`,
          runId: entry.run_id,
          createdAt: entry.created_at,
          text: part.text,
          streaming: false,
          fallbackProvider:
            effectiveModel?.provider ?? state.session?.model.provider ?? null,
          fallbackModel:
            effectiveModel?.model ?? state.session?.model.model ?? null,
          fallbackSourceField: "reasoning_summary",
        }))
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
          diagnosticCode: "unknown_message_part",
          diagnosticParams: { originalType: part.original_type },
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
          diagnosticCode: "unknown_message_part",
          diagnosticParams: { originalType },
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
  if (part.category === "plan") {
    context.hiddenCalls.add(`${runKey}:${part.call_id}`)
    return
  }
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
    details: projectActivityDetails(part.public_details),
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
  if (context.hiddenCalls.has(callKey)) return
  const call = context.calls.get(callKey)
  if (!call) {
    blocks.push({
      type: "unknown",
      id: `${entry.id}:${part.id}`,
      runId: entry.run_id,
      createdAt: entry.created_at,
      originalType: "orphan_tool_result",
      diagnosticCode: "orphan_tool_result",
      diagnosticParams: { callId: part.call_id },
    })
    return
  }
  const group = context.groups.get(call.groupKey)
  const activityIndex = group?.activities.indexOf(call.activity) ?? -1
  if (!group || activityIndex < 0) return
  const activity = {
    ...call.activity,
    status: part.status,
    output: part.output,
    error: part.error,
    startedAt: part.started_at,
    completedAt: part.completed_at,
    details: mergeActivityDetails(
      call.activity.details,
      projectActivityDetails(part.public_details),
    ),
  }
  group.activities[activityIndex] = activity
  context.calls.set(callKey, { groupKey: call.groupKey, activity })
}

function projectCurrentPlan(state: AgentStoreState): ConversationPlan | null {
  const latest = [...state.entries]
    .filter((entry): entry is Extract<HistoryEntry, { type: "plan" }> =>
      entry.type === "plan"
    )
    .sort((left, right) => left.sequence - right.sequence)
    .at(-1)
  if (!latest) return null
  const run = state.runs.find((candidate) => candidate.id === latest.run_id)
  const active = Boolean(
    run && ["queued", "running", "waiting_user"].includes(run.status),
  )
  const completed = run?.status === "completed"
  return {
    id: latest.id,
    runId: latest.run_id,
    planId: latest.payload.plan_id,
    revision: latest.payload.revision,
    title: latest.payload.title ?? null,
    active,
    items: latest.payload.items.map((item) => ({
      ...item,
      status: completed ? "completed" : item.status,
    })),
    updatedAt: latest.payload.updated_at,
  }
}

function projectInteractionRequestEntry(
  entry: Extract<HistoryEntry, { type: "interaction_request" }>,
  context: HistoryProjectionContext,
): InteractionTranscriptBlock[] {
  const block: InteractionTranscriptBlock = {
    type: "interaction",
    id: entry.id,
    runId: entry.run_id,
    createdAt: entry.created_at,
    interactionId: entry.payload.interaction_id,
    status: "pending",
    request: projectInteractionRequest(entry.payload.request),
    response: null,
  }
  context.interactions.set(
    interactionKey(entry.run_id, entry.payload.interaction_id),
    block,
  )
  return [block]
}

function projectInteractionResponseEntry(
  entry: Extract<HistoryEntry, { type: "interaction_response" }>,
): InteractionTranscriptBlock[] {
  return [
    {
      type: "interaction",
      id: entry.id,
      runId: entry.run_id,
      createdAt: entry.created_at,
      interactionId: entry.payload.interaction_id,
      status: "resolved",
      request: null,
      response: projectInteractionResponse(entry.payload.response),
    },
  ]
}

function interactionKey(runId: string | null, interactionId: string) {
  return `${runId ?? "session"}:${interactionId}`
}

function projectActivityDetails(
  details: readonly ToolPublicDetail[] | undefined,
): ActivityItem["details"] {
  if (!details?.length) return undefined
  return details.map((detail) => ({
    id: detail.id,
    kind: detail.kind,
    label: detail.label,
    value: detail.value,
    format: detail.format,
    copyable: detail.copyable,
    truncated: detail.truncated,
    redacted: detail.redacted,
  }))
}

function mergeActivityDetails(
  current: ActivityItem["details"],
  incoming: ActivityItem["details"],
) {
  if (!incoming?.length) return current
  if (!current?.length) return incoming
  const merged = new Map(current.map((detail) => [detail.id, detail]))
  for (const detail of incoming) merged.set(detail.id, detail)
  return [...merged.values()]
}

function appendReference(
  blocks: TranscriptBlock[],
  entry: Extract<HistoryEntry, { type: "message" }>,
  part: Exclude<
    MessagePart,
    | { type: "text" }
    | { type: "reasoning_summary" }
    | { type: "reasoning_trace" }
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
    | { type: "reasoning_trace" }
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
  const originalType =
    entry.type === "unknown" ? entry.payload.original_type : String(entry.type)

  return {
    type: "unknown",
    id: entry.id,
    runId: entry.run_id,
    createdAt: entry.created_at,
    originalType,
    diagnosticCode,
    diagnosticParams:
      diagnosticCode === "unsupported_entry_version"
        ? {
            originalType,
            version: String(entry.schema_version),
          }
        : { originalType },
  }
}

import type { RunCreateV2 } from "@/lib/form-spec"
import { applySSEEvent, mapDbMessage } from "@/lib/chat-utils"
import type { ChatMessage, MessagePart, SSEEvent } from "@/lib/chat-types"
import type {
  AgentConversationHistory,
  AgentConversationRead,
  AgentEventData,
  AgentMessageRead,
  AgentMessageResponse,
  AuditLogEntry,
  DagData,
  DockerImage,
  EventEnvelope,
  ImageStatusMeta,
  Project,
  ProjectWorkflowGroup,
  Run,
  RunDagEvent,
  RunLogEntry,
  RunLogs,
  RunOutputs,
  RunStatusEvent,
  ValidateWorkflowResponse,
  Workflow,
} from "@/lib/types"
import type {
  AppRuntime,
  RequestParams,
  RuntimeEventSubscription,
  RuntimeRequestOptions,
  RuntimeRequestResult,
} from "./types"
import { ApiError } from "./request-core"
import { DEMO_RUNTIME_SCENARIO } from "@/lib/demo/scenario-data"
import type { DemoScenario, DemoFileNode } from "@/lib/demo/scenario"

type DemoUserLlmSettings = {
  provider_credentials: Record<string, Record<string, string>>
  selected_provider: string
  selected_model: string
  configured_providers: string[]
}

type DemoProviderModels = {
  provider: string
  label: string
  models: Array<{
    id: string
    name: string
    context_window: number | null
  }>
}

type DemoRuntimeState = {
  scenario: DemoScenario
  runs: Map<string, Run>
  runLogs: Map<string, RunLogs>
  runOutputs: Map<string, RunOutputs>
  runDag: Map<string, DagData>
  runAudit: Map<string, AuditLogEntry[]>
  conversationsByProject: Map<string, AgentConversationRead[]>
  conversationHistory: Map<string, AgentConversationHistory>
  conversationStatus: Map<
    string,
    {
      conversation_id: string
      is_running: boolean
      response_id: string | null
      assistant_message_id: string | null
      last_event_at: string | null
    }
  >
  workflowGroupsByProject: Map<string, ProjectWorkflowGroup[]>
  workspaceFiles: Map<string, DemoFileNode[]>
  images: DockerImage[]
  imageStatus: ImageStatusMeta
  llmSettings: DemoUserLlmSettings
  providerModels: DemoProviderModels[]
  runSequence: number
  projectSequence: number
  workflowSequence: number
  conversationSequence: number
  imageSequence: number
  subscribers: Map<number, RuntimeEventSubscription>
  subscriptionSequence: number
}

function clone<T>(value: T): T {
  return structuredClone(value)
}

function createInitialState(): DemoRuntimeState {
  return {
    scenario: clone(DEMO_RUNTIME_SCENARIO),
    runs: new Map(
      DEMO_RUNTIME_SCENARIO.runs.map((run) => [run.run_id, clone(run)]),
    ),
    runLogs: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.runLogs).map(([runId, logs]) => [
        runId,
        clone(logs),
      ]),
    ),
    runOutputs: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.runOutputs).map(([runId, outputs]) => [
        runId,
        clone(outputs),
      ]),
    ),
    runDag: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.runDag).map(([runId, dag]) => [
        runId,
        clone(dag),
      ]),
    ),
    runAudit: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.runAudit).map(([runId, audit]) => [
        runId,
        clone(audit),
      ]),
    ),
    conversationsByProject: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.conversations).map(
        ([projectId, conversations]) => [projectId, clone(conversations)],
      ),
    ),
    conversationHistory: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.conversationHistory).map(
        ([conversationId, history]) => [conversationId, clone(history)],
      ),
    ),
    conversationStatus: new Map(
      Object.keys(DEMO_RUNTIME_SCENARIO.conversationHistory).map(
        (conversationId) => [
          conversationId,
          {
            conversation_id: conversationId,
            is_running: false,
            response_id: null,
            assistant_message_id: null,
            last_event_at: null,
          },
        ],
      ),
    ),
    workflowGroupsByProject: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.projectWorkflowGroups).map(
        ([projectId, groups]) => [projectId, clone(groups)],
      ),
    ),
    workspaceFiles: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.workspaceFiles).map(
        ([projectId, files]) => [projectId, clone(files)],
      ),
    ),
    images: clone(DEMO_RUNTIME_SCENARIO.images),
    imageStatus: clone(DEMO_RUNTIME_SCENARIO.imageStatus),
    llmSettings: {
      provider_credentials: {
        openai: {
          api_key: "demo-key",
        },
      },
      selected_provider: "openai",
      selected_model: "gpt-5.4-mini",
      configured_providers: ["openai"],
    },
    providerModels: [
      {
        provider: "openai",
        label: "OpenAI",
        models: [
          {
            id: "gpt-5.4-mini",
            name: "GPT-5.4 Mini",
            context_window: 128000,
          },
          {
            id: "gpt-5.4",
            name: "GPT-5.4",
            context_window: 256000,
          },
        ],
      },
    ],
    runSequence: 1,
    projectSequence: DEMO_RUNTIME_SCENARIO.projects.length + 1,
    workflowSequence: DEMO_RUNTIME_SCENARIO.workflows.length + 1,
    conversationSequence:
      Object.values(DEMO_RUNTIME_SCENARIO.conversations).flat().length + 1,
    imageSequence: DEMO_RUNTIME_SCENARIO.images.length + 1,
    subscribers: new Map(),
    subscriptionSequence: 0,
  }
}

type DemoRunReplayStep =
  | { delayMs: number; type: "status"; data: RunStatusEvent }
  | { delayMs: number; type: "dag"; data: RunDagEvent }
  | { delayMs: number; type: "log"; data: { run_id: string; entry: RunLogEntry } }

type DemoAgentReplayStep = {
  delayMs: number
  event: string
  data: AgentEventData
}

function encodeDataUrl(label: string, content: string) {
  return `data:text/plain;charset=utf-8,${encodeURIComponent(
    `${label}\n\n${content}`,
  )}`
}

function matchPath(pattern: RegExp, path: string) {
  const match = pattern.exec(path)
  return match ? match.slice(1) : null
}

function nowStamp() {
  return new Date().toISOString()
}

function appendConversationMessage(
  state: DemoRuntimeState,
  conversationId: string,
  message: AgentMessageRead,
) {
  const history = state.conversationHistory.get(conversationId)
  if (!history) return
  history.messages = [...history.messages, message]
  history.title = history.title || "Demo analysis"
}

function serializeMessagePart(part: MessagePart): Record<string, unknown> {
  if (part.type === "text") {
    return { type: "text", text: part.text }
  }
  if (part.type === "thinking") {
    return {
      type: "thinking",
      text: part.text,
      isStreaming: part.isStreaming,
    }
  }
  if (part.type === "tool-call") {
    return {
      type: "tool-call",
      id: part.id,
      toolName: part.toolName,
      args: part.args,
      status: part.status,
      result: part.result,
      resultData: part.resultData,
      durationMs: part.durationMs,
      progressText: part.progressText,
      progressStatus: part.progressStatus,
    }
  }
  return {
    type: "approval",
    approvalId: part.approvalId,
    toolName: part.toolName,
    toolInput: part.toolInput,
    approvalType: part.approvalType,
    status: part.status,
    createdAt: part.createdAt.toISOString(),
    risk: part.risk,
  }
}

function messagePartsToText(parts: MessagePart[]) {
  return parts
    .filter((part): part is Extract<MessagePart, { type: "text" }> => part.type === "text")
    .map((part) => part.text)
    .join("")
}

function listProjectConversations(state: DemoRuntimeState, projectId: string) {
  return state.conversationsByProject.get(projectId) ?? []
}

function findConversationRead(
  state: DemoRuntimeState,
  conversationId: string,
) {
  for (const conversations of state.conversationsByProject.values()) {
    const match = conversations.find((item) => item.id === conversationId)
    if (match) return match
  }
  return null
}

function replaceConversationRead(
  state: DemoRuntimeState,
  conversation: AgentConversationRead,
) {
  const current = listProjectConversations(state, conversation.project_id)
  const index = current.findIndex((item) => item.id === conversation.id)
  if (index === -1) {
    state.conversationsByProject.set(conversation.project_id, [
      conversation,
      ...current,
    ])
    return
  }
  const next = [...current]
  next[index] = conversation
  state.conversationsByProject.set(conversation.project_id, next)
}

function removeConversationRead(
  state: DemoRuntimeState,
  conversationId: string,
  projectId: string,
) {
  const current = listProjectConversations(state, projectId)
  state.conversationsByProject.set(
    projectId,
    current.filter((item) => item.id !== conversationId),
  )
}

function ensureConversationStatus(
  state: DemoRuntimeState,
  conversationId: string,
) {
  const existing = state.conversationStatus.get(conversationId)
  if (existing) return existing
  const status = {
    conversation_id: conversationId,
    is_running: false,
    response_id: null,
    assistant_message_id: null,
    last_event_at: null,
  }
  state.conversationStatus.set(conversationId, status)
  return status
}

function createConversation(
  state: DemoRuntimeState,
  projectId: string,
  options?: {
    id?: string
    title?: string
    executionPolicy?: AgentConversationRead["execution_policy"]
  },
) {
  const conversationId =
    options?.id ??
    `conv-demo-${String(state.conversationSequence).padStart(3, "0")}`

  if (!options?.id) {
    state.conversationSequence += 1
  }

  const conversation: AgentConversationRead = {
    id: conversationId,
    project_id: projectId,
    title: options?.title ?? "New demo analysis",
    execution_policy: options?.executionPolicy ?? "auto",
    created_at: nowStamp(),
    updated_at: nowStamp(),
  }

  const current = state.conversationsByProject.get(projectId) ?? []
  state.conversationsByProject.set(projectId, [conversation, ...current])
  state.conversationHistory.set(conversationId, {
    conversation_id: conversationId,
    project_id: projectId,
    title: conversation.title,
    execution_policy: conversation.execution_policy,
    messages: [],
  })
  ensureConversationStatus(state, conversationId)

  return conversation
}

function ensureConversationForProject(
  state: DemoRuntimeState,
  projectId: string,
  options?: {
    preferredConversationId?: string
    executionPolicy?: AgentConversationRead["execution_policy"]
  },
) {
  const preferredConversationId = options?.preferredConversationId

  if (preferredConversationId) {
    if (state.conversationHistory.has(preferredConversationId)) {
      return preferredConversationId
    }
    return createConversation(state, projectId, {
      id: preferredConversationId,
      executionPolicy: options?.executionPolicy ?? "auto",
    }).id
  }

  const existing = listProjectConversations(state, projectId)[0]
  if (existing) {
    if (options?.executionPolicy && existing.execution_policy !== options.executionPolicy) {
      const history = state.conversationHistory.get(existing.id)
      if (history) {
        history.execution_policy = options.executionPolicy
      }
      replaceConversationRead(state, {
        ...existing,
        execution_policy: options.executionPolicy,
        updated_at: nowStamp(),
      })
    }
    return existing.id
  }

  return createConversation(state, projectId, {
    title: "Demo analysis",
    executionPolicy: options?.executionPolicy ?? "auto",
  }).id
}

function emitEnvelope<T>(
  state: DemoRuntimeState,
  eventName: string,
  projectId: string,
  data: T,
  options?: {
    conversationId?: string
    runId?: string
    imageId?: string
  },
) {
  const envelope: EventEnvelope<T> = {
    id: `evt-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    event: eventName,
    project_id: projectId,
    timestamp: nowStamp(),
    data,
    conversation_id: options?.conversationId,
    run_id: options?.runId,
    image_id: options?.imageId,
  }

  for (const [, subscriber] of state.subscribers) {
    if (subscriber.projectId && subscriber.projectId !== projectId) continue
    if (
      subscriber.conversationId &&
      subscriber.conversationId !== envelope.conversation_id
    ) {
      continue
    }
    if (subscriber.runId && subscriber.runId !== envelope.run_id) continue
    if (subscriber.imageId && subscriber.imageId !== envelope.image_id) continue

    if (eventName === "run.status") {
      subscriber.onRunStatus?.(envelope as EventEnvelope<RunStatusEvent>)
    } else if (eventName === "run.log") {
      subscriber.onRunLog?.(envelope as EventEnvelope<{ run_id: string; entry: RunLogEntry }>)
    } else if (eventName === "run.dag") {
      subscriber.onRunDag?.(envelope as EventEnvelope<RunDagEvent>)
    } else if (eventName === "image.progress") {
      subscriber.onImageProgress?.(
        envelope as EventEnvelope<{
          image_id: string
          progress?: number | null
          status: DockerImage["status"]
        }>,
      )
    } else if (eventName.startsWith("agent.")) {
      subscriber.onAgentEvent?.(envelope as EventEnvelope<AgentEventData>)
    }
  }
}

function applyRunReplayStep(
  state: DemoRuntimeState,
  projectId: string,
  runId: string,
  step: DemoRunReplayStep,
) {
  if (step.type === "status") {
    const current = state.runs.get(runId)
    if (!current) return
    const completed = step.data.status === "completed"
    const updated: Run = {
      ...current,
      status: step.data.status,
      current_task: step.data.current_task ?? null,
      tasks_completed: step.data.tasks_completed ?? current.tasks_completed,
      tasks_total: step.data.tasks_total ?? current.tasks_total,
      completed_at: completed ? nowStamp() : current.completed_at,
      duration_seconds: completed ? 96 : current.duration_seconds,
      updated_at: nowStamp(),
    }
    state.runs.set(runId, updated)
    emitEnvelope(state, "run.status", projectId, step.data, {
      runId,
    })
    return
  }

  if (step.type === "dag") {
    state.runDag.set(runId, clone(step.data.dag))
    emitEnvelope(state, "run.dag", projectId, step.data, {
      runId,
    })
    return
  }

  const logs = state.runLogs.get(runId) ?? { logs: [] }
  logs.logs = [...logs.logs, step.data.entry]
  state.runLogs.set(runId, logs)
  emitEnvelope(
    state,
    "run.log",
    projectId,
    {
      run_id: runId,
      message: step.data.entry.message,
      level: step.data.entry.level,
      task: step.data.entry.task,
      timestamp: step.data.entry.timestamp,
    },
    { runId },
  )
}

function scheduleRunReplay(
  state: DemoRuntimeState,
  projectId: string,
  runId: string,
  replay: DemoRunReplayStep[],
  initialDelayMs = 0,
) {
  let elapsed = initialDelayMs
  replay.forEach((step) => {
    elapsed += step.delayMs
    setTimeout(() => {
      applyRunReplayStep(state, projectId, runId, step)
    }, elapsed)
  })
  return elapsed
}

function createRunningDag(): DagData {
  return {
    nodes: [
      {
        id: "reads_stats",
        type: "pipeline",
        position: { x: 250, y: 50 },
        data: {
          label: "READS_STATS",
          status: "running",
          displayLabel: "Read Quality Stats",
        },
      },
      {
        id: "reference_stats",
        type: "pipeline",
        position: { x: 250, y: 200 },
        data: {
          label: "REFERENCE_STATS",
          status: "pending",
          displayLabel: "Reference Alignment",
        },
      },
      {
        id: "summary_report",
        type: "pipeline",
        position: { x: 250, y: 350 },
        data: {
          label: "SUMMARY_REPORT",
          status: "pending",
          displayLabel: "Summary Report",
        },
      },
    ],
    edges: [
      { id: "e1", source: "reads_stats", target: "reference_stats", animated: true },
      { id: "e2", source: "reference_stats", target: "summary_report", animated: false },
    ],
  }
}

function createCompletedDag(): DagData {
  return {
    nodes: [
      {
        id: "reads_stats",
        type: "pipeline",
        position: { x: 250, y: 50 },
        data: {
          label: "READS_STATS",
          status: "success",
          displayLabel: "Read Quality Stats",
          duration: 124,
        },
      },
      {
        id: "reference_stats",
        type: "pipeline",
        position: { x: 250, y: 200 },
        data: {
          label: "REFERENCE_STATS",
          status: "success",
          displayLabel: "Reference Alignment",
          duration: 188,
        },
      },
      {
        id: "summary_report",
        type: "pipeline",
        position: { x: 250, y: 350 },
        data: {
          label: "SUMMARY_REPORT",
          status: "success",
          displayLabel: "Summary Report",
          duration: 96,
        },
      },
    ],
    edges: [
      { id: "e1", source: "reads_stats", target: "reference_stats", animated: false },
      { id: "e2", source: "reference_stats", target: "summary_report", animated: false },
    ],
  }
}

function buildRunReplay(runId: string): DemoRunReplayStep[] {
  return [
    {
      delayMs: 80,
      type: "status",
      data: {
        run_id: runId,
        status: "queued",
        current_task: "Queueing",
        tasks_completed: 0,
        tasks_total: 3,
      },
    },
    {
      delayMs: 200,
      type: "status",
      data: {
        run_id: runId,
        status: "running",
        current_task: "READS_STATS",
        tasks_completed: 0,
        tasks_total: 3,
      },
    },
    {
      delayMs: 220,
      type: "dag",
      data: { run_id: runId, dag: createRunningDag() },
    },
    {
      delayMs: 240,
      type: "log",
      data: {
        run_id: runId,
        entry: {
          message: "Initializing reads quality checks",
          task: "READS_STATS",
          level: "info",
          timestamp: nowStamp(),
        },
      },
    },
    {
      delayMs: 520,
      type: "log",
      data: {
        run_id: runId,
        entry: {
          message: "Reference alignment metrics look healthy",
          task: "REFERENCE_STATS",
          level: "info",
          timestamp: nowStamp(),
        },
      },
    },
    {
      delayMs: 800,
      type: "status",
      data: {
        run_id: runId,
        status: "completed",
        current_task: null,
        tasks_completed: 3,
        tasks_total: 3,
      },
    },
    {
      delayMs: 820,
      type: "dag",
      data: {
        run_id: runId,
        dag: createCompletedDag(),
      },
    },
    {
      delayMs: 860,
      type: "log",
      data: {
        run_id: runId,
        entry: {
          message: "Demo summary report written to reports/summary.md",
          task: "SUMMARY_REPORT",
          level: "info",
          timestamp: nowStamp(),
        },
      },
    },
  ]
}

function buildAgentReplay(
  runId: string,
  assistantMessageId: string,
  responseId: string,
): DemoAgentReplayStep[] {
  return [
    {
      delayMs: 40,
      event: "agent.thinking_delta",
      data: {
        id: assistantMessageId,
        type: "thinking_delta",
        content: "I can run the lightweight demo workflow and mirror the progress live.",
        metadata: {
          response_id: responseId,
        },
      },
    },
    {
      delayMs: 120,
      event: "agent.text_delta",
      data: {
        id: assistantMessageId,
        type: "text_delta",
        content: "I",
        metadata: {
          response_id: responseId,
        },
      },
    },
    {
      delayMs: 150,
      event: "agent.text_delta",
      data: {
        id: assistantMessageId,
        type: "text_delta",
        content: "'ll launch the RNA-seq mini pipeline now.",
        metadata: {
          response_id: responseId,
        },
      },
    },
    {
      delayMs: 220,
      event: "agent.tool_call_start",
      data: {
        id: assistantMessageId,
        type: "tool_call_start",
        metadata: {
          response_id: responseId,
          id: `demo-tool-${runId}`,
          name: "submit_run",
          args: {
            workflow: "rnaseq-quant-mini",
            run_id: runId,
          },
        },
      },
    },
    {
      delayMs: 340,
      event: "agent.tool_call_end",
      data: {
        id: assistantMessageId,
        type: "tool_call_end",
        metadata: {
          response_id: responseId,
          id: `demo-tool-${runId}`,
          name: "submit_run",
          result: `Run submitted: ${runId}`,
          is_error: false,
          duration_ms: 1100,
        },
      },
    },
    {
      delayMs: 420,
      event: "agent.text_delta",
      data: {
        id: assistantMessageId,
        type: "text_delta",
        content: "\n\nThe live deck and runs view will update as the demo replay advances.",
        metadata: {
          response_id: responseId,
        },
      },
    },
    {
      delayMs: 900,
      event: "agent.done",
      data: {
        id: assistantMessageId,
        type: "completion",
        metadata: {
          response_id: responseId,
          input_tokens: 512,
          output_tokens: 178,
          context_tokens: 1024,
        },
      },
    },
  ]
}

function toDemoAgentSSEEvent(
  eventName: string,
  data: AgentEventData,
): SSEEvent | null {
  const metadata = (data.metadata ?? {}) as Record<string, unknown>

  if (eventName === "agent.text_delta") {
    return {
      type: "text_delta",
      messageId: data.id,
      content: data.content || "",
    }
  }

  if (eventName === "agent.thinking_delta") {
    return {
      type: "thinking_delta",
      messageId: data.id,
      content: data.content || "",
    }
  }

  if (eventName === "agent.tool_call_start") {
    return {
      type: "tool_call_start",
      messageId: data.id,
      metadata: {
        id: (metadata.id as string) || "",
        name: (metadata.name as string) || "",
        args: (metadata.args as Record<string, unknown>) || {},
      },
    }
  }

  if (eventName === "agent.tool_call_progress") {
    return {
      type: "tool_call_progress",
      messageId: data.id,
      metadata: {
        id: (metadata.id as string) || "",
        name: (metadata.name as string) || "",
        status: (metadata.status as string) || "",
        preview: (metadata.preview as string) || data.content || "",
      },
    }
  }

  if (eventName === "agent.tool_call_end") {
    return {
      type: "tool_call_end",
      messageId: data.id,
      metadata: {
        id: (metadata.id as string) || "",
        name: (metadata.name as string) || "",
        result: (metadata.result as string) || "",
        result_json: metadata.result_json,
        is_error: Boolean(metadata.is_error),
        duration_ms: (metadata.duration_ms as number) || 0,
      },
    }
  }

  if (eventName === "agent.message") {
    return {
      type: "text",
      messageId: data.id,
      content: data.content || "",
    }
  }

  if (eventName === "agent.done") {
    return {
      type: "done",
      messageId: data.id,
    }
  }

  if (eventName === "agent.error") {
    return {
      type: "error",
      messageId: data.id,
      content: data.content || "An error occurred",
    }
  }

  return null
}

function persistAgentReplayStep(
  state: DemoRuntimeState,
  conversationId: string,
  eventName: string,
  data: AgentEventData,
) {
  const history = state.conversationHistory.get(conversationId)
  if (!history) return

  const sseEvent = toDemoAgentSSEEvent(eventName, data)
  const status = ensureConversationStatus(state, conversationId)
  status.last_event_at = nowStamp()

  if (!sseEvent) {
    if (eventName === "agent.done" || eventName === "agent.error") {
      status.is_running = false
      status.response_id = null
    }
    return
  }

  const existingRecord = history.messages.find((message) => message.id === data.id)
  const record =
    existingRecord ??
    {
      id: data.id,
      role: "agent" as const,
      type: "text" as const,
      content: "",
      metadata: { parts: [] },
      created_at: nowStamp(),
    }

  if (!existingRecord) {
    history.messages = [...history.messages, record]
  }

  const mapped =
    mapDbMessage({
      id: record.id,
      role: record.role,
      type: record.type,
      content: record.content,
      metadata: record.metadata,
      created_at: record.created_at ?? nowStamp(),
    }) ??
    ({
      id: record.id,
      role: "assistant",
      parts: [],
      createdAt: new Date(record.created_at ?? nowStamp()),
      streaming: false,
    } satisfies ChatMessage)

  const updated = applySSEEvent([mapped], sseEvent).find(
    (message) => message.id === record.id,
  )
  if (!updated) return

  record.metadata = {
    ...(record.metadata ?? {}),
    parts: updated.parts.map(serializeMessagePart),
  }
  record.content = messagePartsToText(updated.parts)

  if (eventName === "agent.done" || eventName === "agent.error") {
    status.is_running = false
    status.response_id = null
  }
}

function syncImageStats(state: DemoRuntimeState) {
  const local = state.images.filter((image) => image.status === "local").length
  const remote = state.images.filter((image) => image.status === "remote").length
  const pulling = state.images.filter((image) => image.status === "pulling").length

  state.scenario.dashboard.stats.images = {
    total: state.images.length,
    local,
    remote,
    pulling,
  }
  state.imageStatus.last_synced_at = nowStamp()
}

function inferRegistry(name: string) {
  const firstSegment = name.split("/")[0] ?? ""
  if (firstSegment.includes(".") || firstSegment.includes(":") || firstSegment === "localhost") {
    return firstSegment
  }
  return "docker.io"
}

function upsertImage(state: DemoRuntimeState, image: DockerImage) {
  const existingIndex = state.images.findIndex(
    (candidate) => candidate.full_name === image.full_name,
  )
  if (existingIndex === -1) {
    state.images = [image, ...state.images]
  } else {
    const next = [...state.images]
    next[existingIndex] = image
    state.images = next
  }
  syncImageStats(state)
}

function createDemoImage(
  state: DemoRuntimeState,
  name: string,
  tag: string,
  status: DockerImage["status"],
  description: string,
) {
  const imageId = `img-demo-${String(state.imageSequence).padStart(3, "0")}`
  state.imageSequence += 1
  const registry = inferRegistry(name)

  return {
    id: imageId,
    name,
    tag,
    full_name: `${name}:${tag}`,
    description,
    size_bytes: 186_646_528,
    status,
    registry,
    pull_progress: status === "pulling" ? 58 : null,
    error_message: null,
    labels: {
      maintainer: "Bioinfoflow",
      demo: "true",
    },
    env: ["BIOINFOFLOW_DEMO=1", "PATH=/usr/local/bin:/usr/bin"],
    entrypoint: ["/bin/bash"],
    created_at: nowStamp(),
    updated_at: nowStamp(),
  } satisfies DockerImage
}

function getProjectRuns(state: DemoRuntimeState, projectId?: string | null) {
  const runs = Array.from(state.runs.values())
    .sort((left, right) => right.run_id.localeCompare(left.run_id))
  if (!projectId) return runs
  return runs.filter((run) => run.project_id === projectId)
}

function findFileNode(nodes: DemoFileNode[], path: string): DemoFileNode | null {
  for (const node of nodes) {
    if (node.path === path) return node
    if (node.type === "directory") {
      const nested = findFileNode(node.children, path)
      if (nested) return nested
    }
  }
  return null
}

function listChildren(nodes: DemoFileNode[], path: string) {
  if (!path || path === ".") {
    return nodes.map((node) => {
      if (node.type === "directory") {
        return {
          name: node.name,
          type: node.type,
          path: node.path,
          size_bytes: null,
        }
      }
      return {
        name: node.name,
        type: node.type,
        path: node.path,
        size_bytes: node.size_bytes ?? null,
      }
    })
  }

  const node = findFileNode(nodes, path)
  if (!node || node.type !== "directory") return []
  return node.children.map((child) => {
    if (child.type === "directory") {
      return {
        name: child.name,
        type: child.type,
        path: child.path,
        size_bytes: null,
      }
    }
    return {
      name: child.name,
      type: child.type,
      path: child.path,
      size_bytes: child.size_bytes ?? null,
    }
  })
}

function createRunRecord(
  state: DemoRuntimeState,
  payload: RunCreateV2,
  runId: string,
): Run {
  return {
    id: `run-model-${runId}`,
    run_id: runId,
    project_id: payload.project_id,
    workflow_id: payload.workflow_id,
    status: "pending",
    config: payload.values,
    started_at: nowStamp(),
    completed_at: null,
    duration_seconds: null,
    samples_count: 2,
    tasks_total: 3,
    tasks_completed: 0,
    current_task: "Queued",
    created_at: nowStamp(),
    updated_at: nowStamp(),
  }
}

function createRunArtifacts(runId: string) {
  return {
    logs: {
      logs: [] as RunLogEntry[],
    },
    outputs: {
      files: [
        {
          name: "summary.md",
          path: "reports/summary.md",
          size_bytes: 812,
          type: "file" as const,
        },
        {
          name: "counts.tsv",
          path: "counts/counts.tsv",
          size_bytes: 428,
          type: "file" as const,
        },
        {
          name: "metrics.json",
          path: "reports/metrics.json",
          size_bytes: 264,
          type: "file" as const,
        },
      ],
    },
    dag: createRunningDag(),
    audit: [
      {
        id: `audit-${runId}-submitted`,
        run_id: runId,
        action: "run.submitted",
        actor: "Demo Runtime",
        details: { origin: "demo", run_id: runId },
        created_at: nowStamp(),
      },
    ] as AuditLogEntry[],
  }
}

function createWorkflowRecord(
  state: DemoRuntimeState,
  payload: Record<string, unknown>,
  options?: {
    name?: string
    sourceRef?: string | null
    entrypointRelpath?: string | null
  },
): Workflow {
  const workflowId = `wf-demo-${String(state.workflowSequence).padStart(3, "0")}`
  state.workflowSequence += 1
  const source = (payload.source as Workflow["source"]) || "local"
  const engine = (payload.engine as Workflow["engine"]) || "nextflow"
  const name =
    options?.name ??
    String(
      payload.name ??
        payload.file_name ??
        payload.source_ref ??
        `demo-workflow-${state.workflowSequence - 1}`,
    )
      .replace(/^nf-core\//, "")
      .replace(/\.(wdl|nf)$/i, "")

  const workflow: Workflow = {
    id: workflowId,
    name,
    description:
      typeof payload.description === "string" && payload.description.trim()
        ? payload.description.trim()
        : "Registered in the demo runtime.",
    source,
    engine,
    source_ref:
      options?.sourceRef ??
      (typeof payload.source_ref === "string" ? payload.source_ref : null),
    entrypoint_relpath: options?.entrypointRelpath ?? null,
    version:
      typeof payload.version === "string" && payload.version.trim()
        ? payload.version.trim()
        : "1.0.0",
    created_at: nowStamp(),
    updated_at: nowStamp(),
  }

  state.scenario.workflows = [workflow, ...state.scenario.workflows]
  state.scenario.workflowDag[workflowId] = clone(createRunningDag())
  state.scenario.workflowSource[workflowId] =
    typeof payload.content === "string" && payload.content.trim()
      ? payload.content
      : `// Demo workflow source for ${name}\nworkflow { main: true }`
  state.scenario.formSpecs[workflowId] = clone(
    state.scenario.formSpecs["wf-rnaseq-quant-mini"],
  )

  return workflow
}

async function readUploadedFile(body: FormData | null, fallbackName: string) {
  const file = body?.get("file")
  if (!file || typeof File === "undefined" || !(file instanceof File)) {
    return {
      name: fallbackName,
      content: "Demo uploaded file",
      size: null as number | null,
    }
  }

  return {
    name: file.name || fallbackName,
    content: await file.text(),
    size: file.size || null,
  }
}

function upsertWorkspaceFile(
  state: DemoRuntimeState,
  projectId: string,
  path: string,
  content: string,
  sizeBytes: number | null,
) {
  const rootNodes = clone(state.workspaceFiles.get(projectId) ?? [])
  const [topLevel, ...rest] = path.split("/")
  if (!topLevel || rest.length === 0) return

  let directory = rootNodes.find(
    (node): node is Extract<DemoFileNode, { type: "directory" }> =>
      node.type === "directory" && node.path === topLevel,
  )

  if (!directory) {
    directory = {
      name: topLevel,
      type: "directory",
      path: topLevel,
      children: [],
    }
    rootNodes.unshift(directory)
  }

  directory.children = directory.children.filter((child) => child.path !== path)
  directory.children.unshift({
    name: rest.at(-1) ?? path,
    type: "file",
    path,
    content,
    size_bytes: sizeBytes,
  })

  state.workspaceFiles.set(projectId, rootNodes)
}

function createDemoRuntimeInternal(): AppRuntime {
  const state = createInitialState()

  const request = async <T>(
    path: string,
    options: RuntimeRequestOptions = {},
  ): Promise<RuntimeRequestResult<T>> => {
    const method = (options.method || "GET").toUpperCase()
    const params = options.params ?? {}
    const bodyText =
      typeof options.body === "string" ? options.body : null
    const bodyJson = bodyText ? JSON.parse(bodyText) : null
    const bodyFormData =
      typeof FormData !== "undefined" && options.body instanceof FormData
        ? options.body
        : null

    if (path === "/projects" && method === "GET") {
      return { data: clone(state.scenario.projects) as T }
    }

    if (path === "/projects" && method === "POST") {
      const projectId = `project-demo-${String(state.projectSequence).padStart(3, "0")}`
      state.projectSequence += 1
      const project: Project = {
        id: projectId,
        name:
          typeof bodyJson?.name === "string" && bodyJson.name.trim()
            ? bodyJson.name.trim()
            : `Demo Project ${state.projectSequence - 1}`,
        description:
          typeof bodyJson?.description === "string"
            ? bodyJson.description.trim() || null
            : null,
        created_at: nowStamp(),
        updated_at: nowStamp(),
      }
      state.scenario.projects = [project, ...state.scenario.projects]
      state.workflowGroupsByProject.set(projectId, [])
      state.workspaceFiles.set(projectId, [])
      state.conversationsByProject.set(projectId, [])
      return { data: clone(project) as T }
    }

    if (path === "/projects/default" && method === "GET") {
      throw new ApiError("Default project unavailable", { status: 404 })
    }

    const projectMatch = matchPath(/^\/projects\/([^/]+)$/, path)
    if (projectMatch && method === "PATCH") {
      const [projectId] = projectMatch
      const project = state.scenario.projects.find((item) => item.id === projectId)
      if (!project) throw new ApiError("Project not found", { status: 404 })
      if (typeof bodyJson?.name === "string" && bodyJson.name.trim()) {
        project.name = bodyJson.name.trim()
      }
      if (typeof bodyJson?.description === "string") {
        project.description = bodyJson.description.trim() || null
      }
      project.updated_at = nowStamp()
      return { data: clone(project) as T }
    }

    if (projectMatch && method === "DELETE") {
      const [projectId] = projectMatch
      state.scenario.projects = state.scenario.projects.filter(
        (item) => item.id !== projectId,
      )
      state.workflowGroupsByProject.delete(projectId)
      state.workspaceFiles.delete(projectId)
      state.conversationsByProject.delete(projectId)
      for (const [conversationId, history] of state.conversationHistory.entries()) {
        if (history.project_id === projectId) {
          state.conversationHistory.delete(conversationId)
          state.conversationStatus.delete(conversationId)
        }
      }
      return { data: null as T }
    }

    const projectRunsMatch = matchPath(/^\/projects\/([^/]+)\/workflows$/, path)
    if (projectRunsMatch && method === "GET") {
      const [projectId] = projectRunsMatch
      return {
        data: clone(state.workflowGroupsByProject.get(projectId) ?? []) as T,
      }
    }

    const bindWorkflowMatch = matchPath(
      /^\/projects\/([^/]+)\/workflows\/([^/]+):bind$/,
      path,
    )
    if (bindWorkflowMatch && method === "POST") {
      const [projectId, workflowId] = bindWorkflowMatch
      const workflow = state.scenario.workflows.find((item) => item.id === workflowId)
      if (!workflow) throw new ApiError("Workflow not found", { status: 404 })
      const current = state.workflowGroupsByProject.get(projectId) ?? []
      if (!current.some((group) => group.pinned_workflow.id === workflowId)) {
        current.unshift({
          source: workflow.source,
          name: workflow.name,
          pinned_workflow: workflow,
          versions: [workflow],
        })
      }
      state.workflowGroupsByProject.set(projectId, current)
      return { data: null as T }
    }

    const unbindWorkflowMatch = matchPath(
      /^\/projects\/([^/]+)\/workflows\/([^/]+):unbind$/,
      path,
    )
    if (unbindWorkflowMatch && method === "DELETE") {
      const [projectId, workflowId] = unbindWorkflowMatch
      const current = state.workflowGroupsByProject.get(projectId) ?? []
      state.workflowGroupsByProject.set(
        projectId,
        current.filter((group) => group.pinned_workflow.id !== workflowId),
      )
      return { data: null as T }
    }

    const pinsMatch = matchPath(/^\/projects\/([^/]+)\/workflow-pins$/, path)
    if (pinsMatch && method === "POST") {
      return { data: null as T }
    }

    if (path === "/workflows" && method === "GET") {
      return { data: clone(state.scenario.workflows) as T }
    }

    if (path === "/workflows" && method === "POST") {
      const workflow = createWorkflowRecord(state, bodyJson ?? {})
      return { data: clone(workflow) as T }
    }

    const workflowMatch = matchPath(/^\/workflows\/([^/]+)$/, path)
    if (workflowMatch && method === "GET") {
      const [workflowId] = workflowMatch
      const workflow = state.scenario.workflows.find((item) => item.id === workflowId)
      if (!workflow) throw new ApiError("Workflow not found", { status: 404 })
      return { data: clone(workflow) as T }
    }
    if (workflowMatch && method === "DELETE") {
      return { data: null as T }
    }

    const workflowDagMatch = matchPath(/^\/workflows\/([^/]+)\/dag$/, path)
    if (workflowDagMatch && method === "GET") {
      const [workflowId] = workflowDagMatch
      return {
        data: clone(state.scenario.workflowDag[workflowId]) as T,
      }
    }

    const workflowSourceMatch = matchPath(/^\/workflows\/([^/]+)\/source$/, path)
    if (workflowSourceMatch && method === "GET") {
      const [workflowId] = workflowSourceMatch
      return {
        data: { content: state.scenario.workflowSource[workflowId] ?? "" } as T,
      }
    }

    const formSpecMatch = matchPath(/^\/workflows\/([^/]+)\/form-spec$/, path)
    if (formSpecMatch && method === "GET") {
      const [workflowId] = formSpecMatch
      const spec = state.scenario.formSpecs[workflowId]
      if (!spec) throw new ApiError("Workflow form spec not found", { status: 404 })
      return { data: clone(spec) as T }
    }

    if (path === "/workflows/validate" && method === "POST") {
      const response: ValidateWorkflowResponse = {
        valid: true,
        errors: [],
        warnings: [],
        schema: state.scenario.workflows[0]?.schema_json ?? null,
        dag: clone(createRunningDag()),
      }
      return { data: response as T }
    }

    if (path === "/workflows/local-bundle" && method === "POST") {
      const workflow = createWorkflowRecord(
        state,
        {
          source: "local",
          engine: bodyFormData?.get("engine") ?? "nextflow",
          name: bodyFormData?.get("name") ?? null,
          version: bodyFormData?.get("version") ?? null,
          description: bodyFormData?.get("description") ?? null,
        },
        {
          name:
            typeof bodyFormData?.get("name") === "string"
              ? String(bodyFormData?.get("name"))
              : "demo-bundle",
          entrypointRelpath:
            typeof bodyFormData?.get("entrypoint_relpath") === "string"
              ? String(bodyFormData?.get("entrypoint_relpath"))
              : null,
        },
      )
      return { data: clone(workflow) as T }
    }

    if (path === "/runs" && method === "GET") {
      const runs = getProjectRuns(
        state,
        typeof params.project_id === "string" ? params.project_id : null,
      )
      return {
        data: clone(runs) as T,
        meta: {
          pagination: {
            limit:
              typeof params.limit === "number"
                ? params.limit
                : Number(params.limit) || runs.length,
            total_count: runs.length,
            has_more: false,
            next_cursor: null,
          },
        },
      }
    }

    if (path === "/runs" && method === "POST") {
      const payload = bodyJson as RunCreateV2
      const runId = `run_demo_${String(state.runSequence).padStart(3, "0")}`
      state.runSequence += 1
      const run = createRunRecord(state, payload, runId)
      const artifacts = createRunArtifacts(runId)
      state.runs.set(runId, run)
      state.runLogs.set(runId, artifacts.logs)
      state.runOutputs.set(runId, artifacts.outputs)
      state.runDag.set(runId, artifacts.dag)
      state.runAudit.set(runId, artifacts.audit)

      scheduleRunReplay(state, payload.project_id, runId, buildRunReplay(runId))

      return { data: { run_id: runId } as T }
    }

    const runMatch = matchPath(/^\/runs\/([^/]+)$/, path)
    if (runMatch && method === "GET") {
      const [runId] = runMatch
      const run = state.runs.get(runId)
      if (!run) throw new ApiError("Run not found", { status: 404 })
      return { data: clone(run) as T }
    }
    if (runMatch && method === "DELETE") {
      return { data: null as T }
    }

    const runStatusActionMatch = matchPath(/^\/runs\/([^/]+)\/(retry|resume|cancel|cleanup)$/, path)
    if (runStatusActionMatch && method === "POST") {
      const [runId, action] = runStatusActionMatch
      const run = state.runs.get(runId)
      if (!run) throw new ApiError("Run not found", { status: 404 })
      if (action === "cancel") {
        const updated = {
          ...run,
          status: "cancelled" as const,
          updated_at: nowStamp(),
        }
        state.runs.set(runId, updated)
        return { data: clone(updated) as T }
      }
      return { data: clone(run) as T }
    }

    const runLogsMatch = matchPath(/^\/runs\/([^/]+)\/logs$/, path)
    if (runLogsMatch && method === "GET") {
      const [runId] = runLogsMatch
      return {
        data: clone(state.runLogs.get(runId) ?? { logs: [] }) as T,
      }
    }

    const runOutputsMatch = matchPath(/^\/runs\/([^/]+)\/outputs$/, path)
    if (runOutputsMatch && method === "GET") {
      const [runId] = runOutputsMatch
      return {
        data: clone(state.runOutputs.get(runId) ?? { files: [] }) as T,
      }
    }

    const runDagMatch = matchPath(/^\/runs\/([^/]+)\/dag$/, path)
    if (runDagMatch && method === "GET") {
      const [runId] = runDagMatch
      return {
        data: clone(state.runDag.get(runId) ?? createRunningDag()) as T,
      }
    }

    const runAuditMatch = matchPath(/^\/runs\/([^/]+)\/audit$/, path)
    if (runAuditMatch && method === "GET") {
      const [runId] = runAuditMatch
      return {
        data: clone(state.runAudit.get(runId) ?? []) as T,
      }
    }

    if (path === "/stats" && method === "GET") {
      const runs = Array.from(state.runs.values())
      const completed = runs.filter((run) => run.status === "completed").length
      const running = runs.filter((run) => run.status === "running").length
      const queued = runs.filter((run) => run.status === "queued").length
      const pending = runs.filter((run) => run.status === "pending").length
      const failed = runs.filter((run) => run.status === "failed").length
      const cancelled = runs.filter((run) => run.status === "cancelled").length
      return {
        data: {
          ...clone(state.scenario.dashboard.stats),
          runs: {
            total: runs.length,
            completed,
            running,
            queued,
            pending,
            failed,
            cancelled,
          },
          recent_runs: runs.slice(0, 5).map((run) => ({
            run_id: run.run_id,
            workflow_id: run.workflow_id ?? null,
            status: run.status,
            started_at: run.started_at ?? null,
            duration_seconds: run.duration_seconds ?? null,
            current_task: run.current_task ?? null,
          })),
        } as T,
      }
    }

    if (path === "/system/health" && method === "GET") {
      return { data: clone(state.scenario.dashboard.health) as T }
    }

    if (path === "/system/gpu" && method === "GET") {
      return { data: clone(state.scenario.dashboard.gpu) as T }
    }

    if (path === "/scheduler/status" && method === "GET") {
      return { data: clone(state.scenario.dashboard.scheduler) as T }
    }

    if (path === "/agent/conversations" && method === "GET") {
      const projectId =
        typeof params.project_id === "string"
          ? params.project_id
          : state.scenario.contextDefaults.selectedProjectId
      return {
        data: clone(state.conversationsByProject.get(projectId) ?? []) as T,
      }
    }

    if (path === "/agent/conversations" && method === "POST") {
      const projectId =
        bodyJson?.project_id ??
        state.scenario.contextDefaults.selectedProjectId
      const conversation = createConversation(state, projectId, {
        title: "New demo analysis",
        executionPolicy: "auto",
      })
      return { data: clone(conversation) as T }
    }

    const conversationMatch = matchPath(/^\/agent\/conversations\/([^/]+)$/, path)
    if (conversationMatch && method === "GET") {
      const [conversationId] = conversationMatch
      const history = state.conversationHistory.get(conversationId)
      if (!history) throw new ApiError("Conversation not found", { status: 404 })
      return { data: clone(history) as T }
    }

    if (conversationMatch && method === "PATCH") {
      const [conversationId] = conversationMatch
      const history = state.conversationHistory.get(conversationId)
      if (!history) throw new ApiError("Conversation not found", { status: 404 })
      const existing = findConversationRead(state, conversationId)
      if (!existing) throw new ApiError("Conversation not found", { status: 404 })
      if (bodyJson?.execution_policy) {
        history.execution_policy = bodyJson.execution_policy
      }
      if (typeof bodyJson?.title === "string") {
        history.title = bodyJson.title.trim() || history.title
      }
      if (typeof bodyJson?.pinned === "boolean") {
        history.pinned = bodyJson.pinned
      }
      const updated: AgentConversationRead = {
        ...existing,
        title: history.title,
        pinned: history.pinned,
        execution_policy: history.execution_policy,
        updated_at: nowStamp(),
      }
      removeConversationRead(state, conversationId, existing.project_id)
      replaceConversationRead(state, updated)
      return { data: clone(updated) as T }
    }

    if (conversationMatch && method === "DELETE") {
      const [conversationId] = conversationMatch
      const existing = findConversationRead(state, conversationId)
      if (existing) {
        removeConversationRead(state, conversationId, existing.project_id)
      }
      state.conversationHistory.delete(conversationId)
      state.conversationStatus.delete(conversationId)
      return { data: null as T }
    }

    const moveConversationMatch = matchPath(
      /^\/agent\/conversations\/([^/]+)\/move$/,
      path,
    )
    if (moveConversationMatch && method === "PATCH") {
      const [conversationId] = moveConversationMatch
      const targetProjectId = bodyJson?.target_project_id as string | undefined
      const history = state.conversationHistory.get(conversationId)
      const existing = findConversationRead(state, conversationId)
      if (!history || !existing || !targetProjectId) {
        throw new ApiError("Conversation move target not found", { status: 404 })
      }
      removeConversationRead(state, conversationId, existing.project_id)
      history.project_id = targetProjectId
      const moved: AgentConversationRead = {
        ...existing,
        project_id: targetProjectId,
        updated_at: nowStamp(),
      }
      replaceConversationRead(state, moved)
      return { data: clone(moved) as T }
    }

    const conversationStatusMatch = matchPath(
      /^\/agent\/conversations\/([^/]+)\/status$/,
      path,
    )
    if (conversationStatusMatch && method === "GET") {
      const [conversationId] = conversationStatusMatch
      return { data: clone(ensureConversationStatus(state, conversationId)) as T }
    }

    const cancelConversationMatch = matchPath(
      /^\/agent\/conversations\/([^/]+)\/cancel$/,
      path,
    )
    if (cancelConversationMatch && method === "POST") {
      const [conversationId] = cancelConversationMatch
      const status = ensureConversationStatus(state, conversationId)
      status.is_running = false
      status.response_id = null
      status.last_event_at = nowStamp()
      return { data: { ok: true } as T }
    }

    if (path === "/agent/message" && method === "POST") {
      const projectId = bodyJson.project_id as string
      const ensuredConversationId = ensureConversationForProject(state, projectId, {
        preferredConversationId: bodyJson.conversation_id as string | undefined,
        executionPolicy: bodyJson.execution_policy as
          | AgentConversationRead["execution_policy"]
          | undefined,
      })
      const userText = bodyJson.content as string
      appendConversationMessage(state, ensuredConversationId, {
        id: `db-user-${Date.now()}`,
        role: "user",
        type: "text",
        content: userText,
        created_at: nowStamp(),
      })

      const runId = `run_demo_${String(state.runSequence).padStart(3, "0")}`
      state.runSequence += 1
      const assistantMessageId = `demo-agent-${runId}`
      const responseId = `demo-response-${runId}`
      appendConversationMessage(state, ensuredConversationId, {
        id: assistantMessageId,
        role: "agent",
        type: "text",
        content: "",
        metadata: {
          parts: [],
        },
        created_at: nowStamp(),
      })
      const conversationStatus = ensureConversationStatus(state, ensuredConversationId)
      conversationStatus.is_running = true
      conversationStatus.response_id = responseId
      conversationStatus.assistant_message_id = assistantMessageId
      conversationStatus.last_event_at = nowStamp()
      const run = createRunRecord(
        state,
        {
          project_id: projectId,
          workflow_id: "wf-rnaseq-quant-mini",
          values: {
            reads_r1: "deliveries/ecoli_R1.fastq.gz",
            reads_r2: "deliveries/ecoli_R2.fastq.gz",
            reference: "reference/ecoli_k12.fa",
          },
        },
        runId,
      )
      const artifacts = createRunArtifacts(runId)
      state.runs.set(runId, run)
      state.runLogs.set(runId, artifacts.logs)
      state.runOutputs.set(runId, artifacts.outputs)
      state.runDag.set(runId, artifacts.dag)
      state.runAudit.set(runId, artifacts.audit)

      let elapsed = 0
      buildAgentReplay(runId, assistantMessageId, responseId).forEach((step) => {
        elapsed += step.delayMs
        setTimeout(() => {
          persistAgentReplayStep(
            state,
            ensuredConversationId,
            step.event,
            step.data,
          )
          emitEnvelope(state, step.event, projectId, step.data, {
            conversationId: ensuredConversationId,
            runId,
          })
        }, elapsed)
      })
      scheduleRunReplay(state, projectId, runId, buildRunReplay(runId), elapsed)

      return {
        data: {
          conversation_id: ensuredConversationId,
          response_id: responseId,
          message_id: assistantMessageId,
          status: "accepted",
        } as AgentMessageResponse as T,
      }
    }

    if (path === "/images" && method === "GET") {
      return {
        data: clone(state.images) as T,
        meta: {
          status: clone(state.imageStatus),
        },
      }
    }

    if (path === "/images/pull" && method === "POST") {
      const name =
        typeof bodyJson?.name === "string" && bodyJson.name.trim()
          ? bodyJson.name.trim()
          : null
      const tag =
        typeof bodyJson?.tag === "string" && bodyJson.tag.trim()
          ? bodyJson.tag.trim()
          : "latest"
      if (!name) {
        throw new ApiError("Image name is required", { status: 400 })
      }

      const fullName = `${name}:${tag}`
      const existing = state.images.find((image) => image.full_name === fullName)
      const image =
        existing
          ? {
              ...existing,
              status: "local" as const,
              pull_progress: null,
              error_message: null,
              updated_at: nowStamp(),
            }
          : createDemoImage(
              state,
              name,
              tag,
              "local",
              "Imported through the demo runtime.",
            )
      upsertImage(state, image)
      return { data: clone(image) as T }
    }

    if (path === "/images/load" && method === "POST") {
      const uploaded = await readUploadedFile(bodyFormData, "demo-image.tar")
      const normalizedName = uploaded.name
        .replace(/\.(tar|tar\.gz|tgz)$/i, "")
        .replace(/[^a-z0-9._/-]+/gi, "-")
        .replace(/^-+|-+$/g, "")
        .toLowerCase() || `demo-image-${state.imageSequence}`
      const image = createDemoImage(
        state,
        `ghcr.io/demo/${normalizedName}`,
        "1.0.0",
        "local",
        "Loaded from a demo tarball import.",
      )
      upsertImage(state, image)
      return { data: clone(state.images) as T }
    }

    const imageMatch = matchPath(/^\/images\/([^/]+)$/, path)
    if (imageMatch && method === "DELETE") {
      const [imageId] = imageMatch
      const image = state.images.find((candidate) => candidate.id === imageId)
      if (!image) throw new ApiError("Image not found", { status: 404 })
      if (image.status === "pulling") {
        throw new ApiError("Image is still pulling", {
          code: "IMAGE_PULLING",
          status: 409,
        })
      }
      state.images = state.images.filter((candidate) => candidate.id !== imageId)
      syncImageStats(state)
      return { data: null as T }
    }

    const approvalMatch = matchPath(/^\/agent\/approvals\/([^/]+)\/resolve$/, path)
    if (approvalMatch && method === "POST") {
      return {
        data: {
          success: true,
        } as T,
      }
    }

    if (path === "/user-settings" && method === "GET") {
      return { data: clone(state.llmSettings) as T }
    }

    if (path === "/user-settings/models" && method === "GET") {
      return { data: clone(state.providerModels) as T }
    }

    if (path === "/user-settings" && method === "PATCH") {
      state.llmSettings = {
        ...state.llmSettings,
        ...(bodyJson ?? {}),
      }
      return { data: clone(state.llmSettings) as T }
    }

    const userSettingsTestMatch = matchPath(/^\/user-settings\/test\/([^/]+)$/, path)
    if (userSettingsTestMatch && method === "POST") {
      const [provider] = userSettingsTestMatch
      return {
        data: {
          provider,
          success: true,
          error: null,
          model: state.llmSettings.selected_model,
        } as T,
      }
    }

    if (path === "/files" && method === "GET") {
      const projectId = params.project_id as string
      const pathParam = (params.path as string | undefined) ?? "."
      const nodes = state.workspaceFiles.get(projectId) ?? []
      return {
        data: {
          path: pathParam,
          files: listChildren(nodes, pathParam),
        } as T,
      }
    }

    if (path === "/files" && method === "DELETE") {
      return { data: null as T }
    }

    if (path === "/files/upload" && method === "POST") {
      const projectId =
        (bodyFormData?.get("project_id") as string | null) ??
        state.scenario.contextDefaults.selectedProjectId
      const uploaded = await readUploadedFile(bodyFormData, "demo-upload.txt")
      upsertWorkspaceFile(
        state,
        projectId,
        `deliveries/${uploaded.name}`,
        uploaded.content,
        uploaded.size,
      )
      return {
        data: {
          ok: true,
        } as T,
      }
    }

    if (path === "/runs/uploads" && method === "POST") {
      const projectId =
        (bodyFormData?.get("project_id") as string | null) ??
        state.scenario.contextDefaults.selectedProjectId
      const uploaded = await readUploadedFile(bodyFormData, "demo-upload.txt")
      const uri = `deliveries/${uploaded.name}`
      upsertWorkspaceFile(state, projectId, uri, uploaded.content, uploaded.size)
      return {
        data: {
          uri,
        } as T,
      }
    }

    if (path === "/files/read" && method === "GET") {
      const projectId = params.project_id as string
      const pathParam = params.path as string
      const nodes = state.workspaceFiles.get(projectId) ?? []
      const node = findFileNode(nodes, pathParam)
      if (!node || node.type !== "file") {
        throw new ApiError("File not found", { status: 404 })
      }
      return {
        data: {
          content: node.content,
        } as T,
      }
    }

    if (path === "/notifications" && method === "POST") {
      return {
        data: {
          id: `notification-${Date.now()}`,
          ...(bodyJson ?? {}),
          enabled: true,
        } as T,
      }
    }

    const notificationMatch = matchPath(/^\/notifications\/([^/]+)$/, path)
    if (notificationMatch && method === "DELETE") {
      return { data: null as T }
    }

    throw new ApiError(`Demo runtime does not handle ${method} ${path}`, {
      status: 404,
    })
  }

  return {
    mode: "demo",
    capabilities: {
      auth: false,
      terminal: false,
      destructiveActions: false,
    },
    contextDefaults: DEMO_RUNTIME_SCENARIO.contextDefaults,
    request,
    buildApiUrl(path: string, params?: RequestParams) {
      if (path.includes("/outputs/download")) {
        return encodeDataUrl("Demo Results Download", `Requested: ${path}`)
      }
      if (path === "/files/download") {
        const filePath = String(params?.path ?? "demo.txt")
        return encodeDataUrl("Demo File Download", `Requested: ${filePath}`)
      }
      return encodeDataUrl("Demo Link", `Requested: ${path}`)
    },
    buildWebSocketUrl() {
      return "ws://demo.invalid/runtime-disabled"
    },
    subscribe(options: RuntimeEventSubscription) {
      const id = ++state.subscriptionSequence
      state.subscribers.set(id, options)
      options.onOpen?.()
      return () => {
        state.subscribers.delete(id)
      }
    },
  }
}

let runtimeSingleton: AppRuntime | null = null

export function createDemoRuntime() {
  return createDemoRuntimeInternal()
}

export function getDemoRuntimeSingleton() {
  if (!runtimeSingleton || runtimeSingleton.mode !== "demo") {
    runtimeSingleton = createDemoRuntimeInternal()
  }
  return runtimeSingleton
}

export type ComposerCapabilities = {
  modelSelection: boolean
  permissionSelection: boolean
  environmentSelection: {
    auto: boolean
    manualMultiSelect: boolean
  }
  planMode: boolean
}

export type ConversationSettings = {
  model: {
    provider: string
    model: string
    displayName: string
  }
  permissionMode: "ask_changes" | "ask_dangerous" | "full_access"
  workspaceAccess: "read_only" | "read_write"
  revision: number
  environmentScope: {
    mode: "auto" | "manual"
    environmentIds: string[]
  }
}

export type ConversationSummary = {
  id: string
  title: string | null
  status: "active" | "archived" | "closing" | "deleted"
  workspaceId: string
  projectId: string | null
}

export type ConversationExecutionConfig = {
  settingsRevision: number
  model: {
    provider: string
    model: string
    displayName: string
  }
  permissionMode: "ask_changes" | "ask_dangerous" | "full_access"
  workspaceAccess: "read_only" | "read_write"
  environmentScope: {
    mode: "auto" | "manual"
    environmentIds: string[]
  }
  environmentTargets: Array<{
    environmentId: string
    displayName: string
    kind: "local" | "ssh"
    host: string | null
  }>
}

export type ConversationRunAudit = {
  id: string
  status: "queued" | "running" | "waiting_user" | "completed" | "failed" | "cancelled"
  startedAt: string | null
  completedAt: string | null
  executionConfig: ConversationExecutionConfig | null
}

export type MessageReference = {
  kind: "attachment" | "file" | "directory" | "workflow" | "run"
  id: string
  label: string
  path: string | null
}

export type MessageTranscriptBlock = {
  type: "message"
  id: string
  runId: string | null
  createdAt: string | null
  role: "user" | "assistant" | "tool"
  text: string
  references: MessageReference[]
  streaming: boolean
}

export type ReasoningTranscriptBlock = {
  type: "reasoning"
  id: string
  runId: string | null
  createdAt: string | null
  text: string
  streaming: boolean
  provider: string | null
  model: string | null
  sourceField: string
  truncated: boolean
  startedAt: string | null
  completedAt: string | null
  durationMs: number | null
}

export type PlanTranscriptBlock = {
  type: "plan"
  id: string
  runId: string | null
  createdAt: string | null
  planId: string
  revision: number
  title: string | null
  items: Array<{
    id: string
    text: string
    status: "pending" | "in_progress" | "completed"
  }>
  updatedAt: string
}

export type ActivityStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "blocked"
  | "cancelled"
  | "interaction_required"

export type ActivityDetail = {
  id: string
  kind:
    | "arguments"
    | "command"
    | "working_directory"
    | "path"
    | "input"
    | "output"
    | "changes"
    | "error"
    | "metadata"
  label: string | null
  value: string
  format: "text" | "path" | "code" | "json" | "diff"
  copyable: boolean
  truncated: boolean
  redacted: boolean
}

export type ActivityItem = {
  id: string
  callId: string
  name: string
  displayName: string
  category: string
  summary: string
  status: ActivityStatus
  input: unknown
  output: unknown
  error: string | null
  startedAt: string | null
  completedAt: string | null
  details?: ActivityDetail[]
}

export type ActivityGroupTranscriptBlock = {
  type: "activity_group"
  id: string
  runId: string | null
  createdAt: string | null
  executionMode: "parallel" | "serial" | "mixed"
  activities: ActivityItem[]
}

export type InteractionTranscriptBlock = {
  type: "interaction"
  id: string
  runId: string | null
  createdAt: string | null
  interactionId: string
  status: "pending" | "resolved"
  request: ConversationInteractionRequest | null
  response: ConversationInteractionResponse | null
}

export type ConversationInteractionTarget = {
  environmentId: string
  displayName: string
  kind: "local" | "ssh"
  host: string | null
}

export type ConversationAskUserOption = {
  id: string
  label: string
  description: string
  recommended: boolean
}

export type ConversationAskUserQuestion = {
  id: string
  header: string
  question: string
  multiSelect: boolean
  options: ConversationAskUserOption[]
}

export type ConversationInteractionRequest =
  | {
      type: "approval"
      callId: string
      toolName: string
      summary: string
      inputPreview: string | null
      allowedResponses: readonly ("approve" | "reject")[]
      risk: {
        level: string
        effects: string[]
        reasons: string[]
        affectedResources: string[]
      }
      target: ConversationInteractionTarget | null
    }
  | {
      type: "ask_user"
      callId: string
      questions: ConversationAskUserQuestion[]
    }
  | {
      type: "recovery"
      callId: string
      toolName: string
      messageCode: string | null
      messageParams: Record<string, string | number>
      messageFallback: string
      options: ConversationAskUserOption[]
    }

export type ConversationInteractionResponse =
  | { type: "approval"; approved: boolean }
  | { type: "ask_user"; answers: ConversationJsonObject }
  | { type: "recovery"; choice: "inspect" | "retry" | "cancel" }

type ConversationJsonValue =
  | string
  | number
  | boolean
  | null
  | ConversationJsonValue[]
  | ConversationJsonObject

type ConversationJsonObject = {
  [key: string]: ConversationJsonValue
}

export type ArtifactTranscriptBlock = {
  type: "artifact"
  id: string
  runId: string | null
  createdAt: string | null
  artifactId: string
  title: string | null
  mediaType: string | null
}

export type NoticeTranscriptBlock = {
  type: "notice"
  id: string
  runId: string | null
  createdAt: string | null
  code: string
  params: Record<string, string | number>
  fallback: string
}

export type OutcomeTranscriptBlock = {
  type: "outcome"
  id: string
  runId: string
  createdAt: string | null
  status: "completed" | "failed" | "cancelled"
  reason: string | null
  error: { code: string; message: string } | null
}

export type UnknownTranscriptBlock = {
  type: "unknown"
  id: string
  runId: string | null
  createdAt: string | null
  originalType: string
  diagnosticCode: string
  diagnosticParams: Record<string, string | number>
}

export type TranscriptBlock =
  | MessageTranscriptBlock
  | ReasoningTranscriptBlock
  | PlanTranscriptBlock
  | ActivityGroupTranscriptBlock
  | InteractionTranscriptBlock
  | ArtifactTranscriptBlock
  | NoticeTranscriptBlock
  | OutcomeTranscriptBlock
  | UnknownTranscriptBlock

export type ActiveWork = {
  runId: string
  status: "queued" | "running" | "waiting_user"
  phase: "model" | "tools" | "interaction" | null
  startedAt: string | null
}

export type ConversationViewModel = {
  protocolVersion: number
  conversation: ConversationSummary
  composer: {
    placement: "centered" | "docked"
    canSend: boolean
    settings: ConversationSettings
    capabilities: ComposerCapabilities
  }
  transcript: TranscriptBlock[]
  runs: ConversationRunAudit[]
  activeWork: ActiveWork | null
}

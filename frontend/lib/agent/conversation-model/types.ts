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
  request: unknown
  response: unknown | null
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
  message: string
  details: unknown
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
  message: string
  diagnosticCode: string
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
  activeWork: ActiveWork | null
}

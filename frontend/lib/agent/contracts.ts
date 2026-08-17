type JsonPrimitive = string | number | boolean | null
export type JsonObject = { [key: string]: JsonValue }
export type JsonValue = JsonPrimitive | JsonValue[] | JsonObject

export type PresentationEnvelope = {
  presentation_protocol: "bioinfoflow.agent.presentation"
  presentation_schema_version: number
}

export type AgentPermissionMode =
  | "ask_changes"
  | "ask_dangerous"
  | "full_access"
export type AgentWorkspaceAccess = "read_only" | "read_write"
export type AgentEnvironmentScope =
  | { mode: "auto" }
  | { mode: "manual"; selected_environment_ids: string[] }
export type AgentSessionEnvironmentScope =
  | { mode: "auto"; environment_ids: null }
  | { mode: "manual"; environment_ids: string[] }
export type AgentSessionStatus = "active" | "archived" | "closing" | "deleted"
export type AgentRunStatus =
  | "queued"
  | "running"
  | "waiting_user"
  | "completed"
  | "failed"
  | "cancelled"
export type AgentRunPhase = "model" | "tools" | "interaction"
export type ToolProgressStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "blocked"
  | "cancelled"
  | "interaction_required"
export type ToolCategory =
  | "read"
  | "search"
  | "command"
  | "edit"
  | "write"
  | "workflow"
  | "plan"
  | "interaction"
  | "other"
export type ToolExecutionMode = "parallel" | "serial" | "mixed"

export type AgentModelSummary = {
  provider: string
  model: string
  display_name: string
  supports_vision: boolean
  supports_reasoning: boolean
  supports_tools: boolean
}

export type RunErrorView = {
  code: string
  message: string
}

export type RunExecutionConfigView = {
  settings_revision: number
  model: AgentModelSummary
  permission_mode: AgentPermissionMode
  workspace_access: AgentWorkspaceAccess
  environment_scope: {
    mode: "auto" | "manual"
    environment_ids: string[]
  }
  environment_targets: Array<{
    environment_id: string
    display_name: string
    kind: "local" | "ssh"
    host: string | null
  }>
}

export type SessionView = {
  id: string
  user_id: string
  workspace_id: string
  project_id: string | null
  title: string | null
  model: AgentModelSummary
  permission_mode: AgentPermissionMode
  workspace_access: AgentWorkspaceAccess
  settings_revision?: number
  environment_scope?: AgentSessionEnvironmentScope
  status: AgentSessionStatus
  created_at: string
  updated_at: string
}

export type RunView = {
  id: string
  session_id: string
  status: AgentRunStatus
  phase: AgentRunPhase | null
  revision: number
  started_at: string | null
  completed_at: string | null
  termination_reason: string | null
  error: RunErrorView | null
  execution_config?: RunExecutionConfigView | null
  created_at: string
  updated_at: string
}

export type ReasoningTraceMetadata = {
  provider: string
  model: string
  source: string
  truncated: boolean
  started_at: string | null
  completed_at: string | null
}

type OptionalReasoningTraceMetadata = {
  provider?: string | null
  model?: string | null
  source?: string | null
  truncated?: boolean
  started_at?: string | null
  completed_at?: string | null
}

type AssistantDraftPartBase = {
  id: string
  text: string
  end_offset: number
}

export type AssistantDraftPartView =
  | (AssistantDraftPartBase &
      OptionalReasoningTraceMetadata & {
        type: "text" | "reasoning_summary"
      })
  | (AssistantDraftPartBase &
      ReasoningTraceMetadata & {
        type: "reasoning_trace"
      })

export type AssistantDraftView = {
  id: string
  run_id: string
  parts: AssistantDraftPartView[]
}

export type ToolPublicDetail = {
  id: string
  kind:
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
  format: "text" | "code" | "path" | "json" | "diff"
  copyable: boolean
  truncated: boolean
  redacted: boolean
}

export type ToolProgressView = {
  call_id: string
  group_id: string
  execution_mode: ToolExecutionMode
  name: string
  display_name: string
  category: ToolCategory
  summary: string
  arguments: JsonObject
  status: ToolProgressStatus
  revision: number
  started_at: string | null
  completed_at: string | null
  input_summary: string | null
  output_summary: string | null
  error: string | null
  public_details?: ToolPublicDetail[]
}

export type AskUserOption = {
  id: string
  label: string
  description: string
  recommended: boolean
}

export type AskUserQuestion = {
  id: string
  header: string
  question: string
  multi_select: boolean
  options: AskUserOption[]
}

export type AskUserRequest = {
  type: "ask_user"
  call_id: string
  questions: AskUserQuestion[]
}

export type ApprovalRiskView = {
  level: string
  effects: string[]
  reasons: string[]
  reason_codes?: string[]
  justification?: string | null
  affected_resources: string[]
}

export type ApprovalAllowedResponse = "approve" | "reject"

export type ApprovalTargetView = {
  environment_id: string
  display_name: string
  kind: "local" | "ssh"
  host?: string | null
}

export type ApprovalRequest = {
  type: "approval"
  call_id: string
  tool_name: string
  summary: string
  input_preview: string | null
  allowed_responses: ApprovalAllowedResponse[]
  target?: ApprovalTargetView
  risk: ApprovalRiskView
}

export type RecoveryRequest = {
  type: "recovery"
  call_id: string
  tool_name: string
  message: string
  message_code?: string | null
  message_params?: JsonObject
  options: AskUserOption[]
}

export type InteractionRequest =
  | AskUserRequest
  | ApprovalRequest
  | RecoveryRequest

export type AskUserInteractionResponse = {
  type: "ask_user"
  answers: JsonObject
}

export type ApprovalInteractionResponse = {
  type: "approval"
  approved: boolean
}

export type RecoveryInteractionResponse = {
  type: "recovery"
  choice: "inspect" | "retry" | "cancel"
}

export type InteractionResponse =
  | AskUserInteractionResponse
  | ApprovalInteractionResponse
  | RecoveryInteractionResponse

export type PendingInteractionView = {
  interaction_id: string
  run_id: string
  revision: number
  request: InteractionRequest
}

type MessagePartBase = {
  id: string
}

export type TextPart = MessagePartBase & {
  type: "text"
  text: string
}

export type ReasoningSummaryPart = MessagePartBase & {
  type: "reasoning_summary"
  text: string
}

export type ReasoningTracePart = MessagePartBase & {
  type: "reasoning_trace"
  text: string
} & ReasoningTraceMetadata

export type ToolCallPart = MessagePartBase & {
  type: "tool_call"
  call_id: string
  group_id: string
  execution_mode: ToolExecutionMode
  name: string
  display_name: string
  category: ToolCategory
  summary: string
  arguments: JsonObject
  public_details?: ToolPublicDetail[]
}

type ToolTextOutput = {
  type: "text"
  text: string
}

type ToolJsonOutput = {
  type: "json"
  value: JsonValue
}

type ToolContentPartsOutput = {
  type: "content_parts"
  parts: ToolOutputContentPart[]
}

export type ToolOutput =
  | ToolTextOutput
  | ToolJsonOutput
  | ToolContentPartsOutput

export type ToolResultPart = MessagePartBase & {
  type: "tool_result"
  call_id: string
  status: ToolProgressStatus
  summary: string | null
  output: ToolOutput | null
  started_at: string | null
  completed_at: string | null
  error: string | null
  public_details?: ToolPublicDetail[]
}

export type AttachmentRefPart = MessagePartBase & {
  type: "attachment_ref"
  attachment_id: string
  filename: string
  kind: string
  mime_type: string | null
  size_bytes: number
}

export type FileRefPart = MessagePartBase & {
  type: "file_ref"
  label: string
  project_id?: string | null
  attachment_id?: string | null
  path?: string | null
}

export type DirectoryRefPart = MessagePartBase & {
  type: "directory_ref"
  label: string
  project_id?: string | null
  attachment_id?: string | null
  path?: string | null
}

export type WorkflowRefPart = MessagePartBase & {
  type: "workflow_ref"
  workflow_id: string
  label: string
  project_id?: string | null
}

export type RunRefPart = MessagePartBase & {
  type: "run_ref"
  run_id: string
  label: string
}

export type InputTextPart = {
  type: "text"
  text: string
}

export type InputAttachmentRefPart = {
  type: "attachment_ref"
  attachment_id: string
}

export type InputFileRefPart =
  | { type: "file_ref"; attachment_id: string }
  | { type: "file_ref"; project_id: string; path: string }

export type InputDirectoryRefPart =
  | { type: "directory_ref"; attachment_id: string }
  | { type: "directory_ref"; project_id: string; path: string }

export type InputWorkflowRefPart =
  | { type: "workflow_ref"; workflow_id: string; scope: "global" }
  | {
      type: "workflow_ref"
      workflow_id: string
      scope: "project"
      project_id: string
    }

export type InputRunRefPart = {
  type: "run_ref"
  run_id: string
}

export type InputPart =
  | InputTextPart
  | InputAttachmentRefPart
  | InputFileRefPart
  | InputDirectoryRefPart
  | InputWorkflowRefPart
  | InputRunRefPart

type AgentCommandBase = {
  command_id: string
}

export type MessageCommand = AgentCommandBase & {
  type: "message"
  parts: InputPart[]
}

export type SteerCommand = AgentCommandBase & {
  type: "steer"
  parts: InputPart[]
}

export type RespondCommand = AgentCommandBase & {
  type: "respond"
  interaction_id: string
  response: InteractionResponse
}

export type CancelCommand = AgentCommandBase & {
  type: "cancel"
  reason?: string | null
}

export type AgentCommand =
  | MessageCommand
  | SteerCommand
  | RespondCommand
  | CancelCommand

export type ArtifactRefPart = MessagePartBase & {
  type: "artifact_ref"
  artifact_id: string
  title: string | null
  media_type: string | null
}

export type UnknownPart = MessagePartBase & {
  type: "unknown"
  original_type: string
  display_text: string
}

type ToolOutputContentPart =
  | TextPart
  | ReasoningSummaryPart
  | ReasoningTracePart
  | AttachmentRefPart
  | FileRefPart
  | DirectoryRefPart
  | WorkflowRefPart
  | RunRefPart
  | ArtifactRefPart
  | UnknownPart

export type MessagePart =
  | TextPart
  | ReasoningSummaryPart
  | ReasoningTracePart
  | ToolCallPart
  | ToolResultPart
  | AttachmentRefPart
  | FileRefPart
  | DirectoryRefPart
  | WorkflowRefPart
  | RunRefPart
  | ArtifactRefPart
  | UnknownPart

type MessagePayload = {
  role: "user" | "assistant" | "tool"
  parts: MessagePart[]
}

type InteractionRequestPayload = {
  interaction_id: string
  request: InteractionRequest
}

type InteractionResponsePayload = {
  interaction_id: string
  response: InteractionResponse
}

type PlanItemStatus = "pending" | "in_progress" | "completed"

type PlanItem = {
  id: string
  text: string
  status: PlanItemStatus
}

type PlanPayload = {
  plan_id: string
  revision: number
  title?: string | null
  items: PlanItem[]
  updated_at: string
}

type NoticePayload = {
  code: string
  message: string
  params?: JsonObject
  details: JsonObject | null
}

type HistoryEntryBase = {
  id: string
  session_id: string
  run_id: string | null
  sequence: number
  schema_version: number
  created_at: string
}

export type MessageEntry = HistoryEntryBase & {
  type: "message"
  payload: MessagePayload
}

export type InteractionRequestEntry = HistoryEntryBase & {
  type: "interaction_request"
  payload: InteractionRequestPayload
}

export type InteractionResponseEntry = HistoryEntryBase & {
  type: "interaction_response"
  payload: InteractionResponsePayload
}

export type PlanEntry = HistoryEntryBase & {
  type: "plan"
  payload: PlanPayload
}

export type NoticeEntry = HistoryEntryBase & {
  type: "notice"
  payload: NoticePayload
}

export type UnknownEntry = HistoryEntryBase & {
  type: "unknown"
  payload: {
    original_type: string
    display_text: string
  }
}

export type HistoryEntry =
  | MessageEntry
  | PlanEntry
  | InteractionRequestEntry
  | InteractionResponseEntry
  | NoticeEntry
  | UnknownEntry

export type ActiveRunView = {
  run: RunView
  assistant_draft: AssistantDraftView | null
  tool_progress: ToolProgressView[]
  pending_interaction: PendingInteractionView | null
}

export type SessionSnapshot = {
  session: SessionView
  runs: RunView[]
  entries: HistoryEntry[]
  active_run: ActiveRunView | null
}

export type PresentationSnapshot = SessionSnapshot & PresentationEnvelope

export type SnapshotEvent = {
  type: "snapshot"
  snapshot: SessionSnapshot
}

export type RunUpdatedEvent = {
  type: "run.updated"
  run: RunView
}

type AssistantDeltaEventBase = {
  type: "assistant.delta"
  run_id: string
  draft_id: string
  part_id: string
  start_offset: number
  end_offset: number
  delta: string
}

export type AssistantDeltaEvent =
  | (AssistantDeltaEventBase &
      OptionalReasoningTraceMetadata & {
        part_type: "text" | "reasoning_summary"
      })
  | (AssistantDeltaEventBase &
      ReasoningTraceMetadata & {
        part_type: "reasoning_trace"
      })

export type ToolUpdatedEvent = {
  type: "tool.updated"
  run_id: string
  tool: ToolProgressView
}

export type InteractionRequestedEvent = {
  type: "interaction.requested"
  run_id: string
  interaction: PendingInteractionView
}

export type EntryCommittedEvent = {
  type: "entry.committed"
  entry: HistoryEntry
}

export type AgentEvent =
  | SnapshotEvent
  | RunUpdatedEvent
  | AssistantDeltaEvent
  | ToolUpdatedEvent
  | InteractionRequestedEvent
  | EntryCommittedEvent

export type PresentationEvent = AgentEvent & PresentationEnvelope

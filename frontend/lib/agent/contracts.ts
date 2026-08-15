export type JsonPrimitive = string | number | boolean | null
export type JsonObject = { [key: string]: JsonValue }
export type JsonValue = JsonPrimitive | JsonValue[] | JsonObject

export type AgentPermissionMode = "read_only" | "ask_dangerous" | "full_access"
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

export type SessionView = {
  id: string
  user_id: string
  workspace_id: string
  project_id: string | null
  title: string | null
  permission_mode: AgentPermissionMode
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
  error: JsonValue
  created_at: string
  updated_at: string
}

export type AssistantDraftPartType = "text" | "reasoning_summary"

export type AssistantDraftPartView = {
  id: string
  type: AssistantDraftPartType
  text: string
  end_offset: number
}

export type AssistantDraftView = {
  id: string
  run_id: string
  parts: AssistantDraftPartView[]
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
  affected_resources: string[]
}

export type ApprovalRequest = {
  type: "approval"
  call_id: string
  tool_name: string
  summary: string
  input_preview: string | null
  risk: ApprovalRiskView
}

export type RecoveryRequest = {
  type: "recovery"
  call_id: string
  tool_name: string
  message: string
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
}

export type ToolTextOutput = {
  type: "text"
  text: string
}

export type ToolJsonOutput = {
  type: "json"
  value: JsonValue
}

export type ToolContentPartsOutput = {
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

export type InputPart =
  | TextPart
  | AttachmentRefPart
  | FileRefPart
  | DirectoryRefPart
  | WorkflowRefPart
  | RunRefPart

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

export type ToolOutputContentPart =
  | TextPart
  | ReasoningSummaryPart
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
  | ToolCallPart
  | ToolResultPart
  | AttachmentRefPart
  | FileRefPart
  | DirectoryRefPart
  | WorkflowRefPart
  | RunRefPart
  | ArtifactRefPart
  | UnknownPart

export type MessagePayload = {
  role: "user" | "assistant" | "tool"
  parts: MessagePart[]
}

export type InteractionRequestPayload = {
  interaction_id: string
  request: InteractionRequest
}

export type InteractionResponsePayload = {
  interaction_id: string
  response: InteractionResponse
}

export type PlanItemStatus = "pending" | "in_progress" | "completed"

export type PlanItem = {
  id: string
  text: string
  status: PlanItemStatus
}

export type PlanPayload = {
  plan_id: string
  revision: number
  title?: string | null
  items: PlanItem[]
  updated_at: string
}

export type CompactionPayload = {
  summary: string
  through_sequence: number
}

export type NoticePayload = {
  code: string
  message: string
  details: JsonValue
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

export type CompactionEntry = HistoryEntryBase & {
  type: "compaction"
  payload: CompactionPayload
}

export type NoticeEntry = HistoryEntryBase & {
  type: "notice"
  payload: NoticePayload
}

export type HistoryEntry =
  | MessageEntry
  | PlanEntry
  | InteractionRequestEntry
  | InteractionResponseEntry
  | CompactionEntry
  | NoticeEntry

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
  history_revision: number
}

export type SnapshotEvent = {
  type: "snapshot"
  snapshot: SessionSnapshot
}

export type RunUpdatedEvent = {
  type: "run.updated"
  run: RunView
}

export type AssistantDeltaEvent = {
  type: "assistant.delta"
  run_id: string
  draft_id: string
  part_id: string
  part_type: AssistantDraftPartType
  start_offset: number
  end_offset: number
  delta: string
}

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

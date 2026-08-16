/* Generated from docs/contracts/agent-ui-v1.json. Do not edit by hand. */

export type CreatedAt = string
export type Id = string
export type Payload = {
  [k: string]: JsonValue
} | null
export type JsonValue = unknown
export type ProtocolVersion = 1
export type Filename = string
export type Kind = "stored_file"
export type MimeType = string
export type Sha256 = string
export type SizeBytes = number
export type RunId = string | null
export type SessionId = string
export type Summary = string | null
export type Title = string
export type Type = string
export type UpdatedAt = string
export type Approvals = boolean
export type Artifacts = boolean
export type EditAndResend = boolean
export type MultiTargetExecution = boolean
export type Reasoning = boolean
export type Retry = boolean
export type StarterPrompts = boolean
export type ToolActivity = boolean
export type ComposerHint = string | null
export type Mode = "auto" | "manual"
export type TargetIds = string[]
export type Alias = string
export type DisabledReason = string | null
export type Handle = string
export type Id1 = string
export type Kind1 = "local" | "remote_ssh"
export type Primary = boolean
export type Status = "online" | "offline" | "error" | "unknown"
export type ExecutionTargets = ExecutionTargetView[]
export type CatalogModelId = string | null
export type DisplayName = string
export type Model = string
export type Provider = string
export type SupportsReasoning = boolean
export type SupportsTools = boolean
export type SupportsVision = boolean
export type PermissionMode = "ask_changes" | "ask_dangerous" | "full_access"
export type ProtocolVersion1 = 1
export type Icon = "check" | "explain" | "review" | "chat"
export type Id2 = string
export type Prompt = string
export type Title1 = string
export type StarterPrompts1 = StarterPromptView[]
export type Event =
  | SnapshotEvent
  | RunUpdatedEvent
  | AssistantDeltaEvent
  | ToolUpdatedEvent
  | InteractionRequestedEvent
  | EntryCommittedEvent
export type ProtocolVersion2 = 1
export type Id3 = string
export type EndOffset = number
export type Id4 = string
export type Text = string
export type Type1 = "text" | "reasoning_summary"
export type Parts = AssistantDraftPartView[]
export type RunId1 = string
export type InteractionId = string
export type Request = AskUserInteractionRequest | ApprovalInteractionRequest | RecoveryInteractionRequest
export type CallId = string
/**
 * @minItems 1
 * @maxItems 3
 */
export type Questions =
  [AskUserQuestion] | [AskUserQuestion, AskUserQuestion] | [AskUserQuestion, AskUserQuestion, AskUserQuestion]
export type Header = string
export type Id5 = string
export type MultiSelect = boolean
/**
 * @minItems 2
 * @maxItems 3
 */
export type Options = [InteractionOption, InteractionOption] | [InteractionOption, InteractionOption, InteractionOption]
export type Description = string
export type Id6 = string
export type Label = string
export type Recommended = boolean
export type Question = string
export type Type2 = "ask_user"
/**
 * @minItems 1
 */
export type AllowedResponses = ["approve" | "reject", ...("approve" | "reject")[]]
export type CallId1 = string
export type InputPreview = string | null
export type AffectedResources = string[]
export type Effects = string[]
export type Level = string
export type Reasons = string[]
export type Summary1 = string
export type Alias1 = string
export type Handle1 = string
export type Id7 = string
export type Kind2 = "local" | "remote_ssh"
export type Root = string | null
export type ToolName = string
export type Type3 = "approval"
export type CallId2 = string
export type Message = string
export type Options1 = InteractionOption[]
export type ToolName1 = string
export type Type4 = "recovery"
export type Revision = number
export type RunId2 = string
export type CompletedAt = string | null
export type CreatedAt1 = string
export type Code = string
export type Message1 = string
export type Id8 = string
export type Phase = ("model" | "tools" | "interaction") | null
export type Revision1 = number
export type SessionId1 = string
export type AllowedTargets = ExecutionTargetView[]
export type PermissionMode1 = "ask_changes" | "ask_dangerous" | "full_access"
export type StartedAt = string | null
export type Status1 = "queued" | "running" | "waiting_user" | "completed" | "failed" | "cancelled"
export type TerminationReason = string | null
export type UpdatedAt1 = string
export type CallId3 = string
export type Category = "read" | "search" | "command" | "edit" | "write" | "workflow" | "plan" | "interaction" | "other"
export type CompletedAt1 = string | null
export type DisplayName1 = string
export type Error = string | null
export type ExecutionMode = "parallel" | "serial" | "mixed"
export type GroupId = string
export type InputSummary = string | null
export type Name = string
export type OutputSummary = string | null
export type Copyable = boolean
export type Format = "text" | "code" | "path" | "json" | "diff"
export type Id9 = string
export type Kind3 = "command" | "working_directory" | "path" | "input" | "output" | "changes" | "error" | "metadata"
export type Label1 = string | null
export type Redacted = boolean
export type Truncated = boolean
export type Value = string
export type PublicDetails = ToolPublicDetail[]
export type Revision2 = number
export type StartedAt1 = string | null
export type Status2 = "pending" | "running" | "completed" | "failed" | "blocked" | "cancelled" | "interaction_required"
export type Summary2 = string
export type ToolProgress = ToolProgressView[]
export type CreatedAt2 = string
export type Id10 = string
export type Id11 = string
export type Text1 = string
export type Type5 = "text"
export type Id12 = string
export type Text2 = string
export type Type6 = "reasoning_summary"
export type AttachmentId = string
export type Filename1 = string
export type Id13 = string
export type Kind4 = string
export type MimeType1 = string | null
export type SizeBytes1 = number
export type Type7 = "attachment_ref"
export type AttachmentId1 = string | null
export type Id14 = string
export type Label2 = string
export type Path = string | null
export type ProjectId = string | null
export type Type8 = "file_ref"
export type AttachmentId2 = string | null
export type Id15 = string
export type Label3 = string
export type Path1 = string | null
export type ProjectId1 = string | null
export type Type9 = "directory_ref"
export type Id16 = string
export type Label4 = string
export type ProjectId2 = string | null
export type Type10 = "workflow_ref"
export type WorkflowId = string
export type Id17 = string
export type Label5 = string
export type RunId3 = string
export type Type11 = "run_ref"
export type ArtifactId = string
export type Id18 = string
export type MediaType = string | null
export type Title2 = string | null
export type Type12 = "artifact_ref"
export type CallId4 = string
export type Category1 = "read" | "search" | "command" | "edit" | "write" | "workflow" | "plan" | "interaction" | "other"
export type DisplayName2 = string
export type ExecutionMode1 = "parallel" | "serial" | "mixed"
export type GroupId1 = string
export type Id19 = string
export type Name1 = string
export type PublicDetails1 = ToolPublicDetail[]
export type Summary3 = string
export type Type13 = "tool_call"
export type CallId5 = string
export type CompletedAt2 = string | null
export type Error1 = string | null
export type Id20 = string
export type Output = (ToolTextOutput | ToolJsonOutput | ToolContentPartsOutput) | null
export type Text3 = string
export type Type14 = "text"
export type Type15 = "json"
export type DisplayText = string
export type Id21 = string
export type OriginalType = string
export type Type16 = "unknown"
export type Parts2 = (
  | TextPart
  | ReasoningSummaryPart
  | AttachmentRefPart
  | FileRefPart
  | DirectoryRefPart
  | WorkflowRefPart
  | RunRefPart
  | ArtifactRefPart
  | UnknownPart
)[]
export type Type17 = "content_parts"
export type PublicDetails2 = ToolPublicDetail[]
export type StartedAt2 = string | null
export type Status3 = "pending" | "running" | "completed" | "failed" | "blocked" | "cancelled" | "interaction_required"
export type Summary4 = string | null
export type Type18 = "tool_result"
export type Parts1 = (
  | TextPart
  | ReasoningSummaryPart
  | AttachmentRefPart
  | FileRefPart
  | DirectoryRefPart
  | WorkflowRefPart
  | RunRefPart
  | ArtifactRefPart
  | ToolCallPart
  | ToolResultPart
  | UnknownPart
)[]
export type Role = "user" | "assistant" | "tool"
export type RunId4 = string | null
export type SchemaVersion = number
export type Sequence = number
export type SessionId2 = string
export type Type19 = "message"
export type CreatedAt3 = string
export type Id22 = string
export type InteractionId1 = string
export type Request1 = AskUserInteractionRequest | ApprovalInteractionRequest | RecoveryInteractionRequest
export type RunId5 = string | null
export type SchemaVersion1 = number
export type Sequence1 = number
export type SessionId3 = string
export type Type20 = "interaction_request"
export type CreatedAt4 = string
export type Id23 = string
export type InteractionId2 = string
export type Response = AskUserInteractionResponse | ApprovalInteractionResponse | RecoveryInteractionResponse
export type Type21 = "ask_user"
export type Approved = boolean
export type Type22 = "approval"
export type Choice = "inspect" | "retry" | "cancel"
export type Type23 = "recovery"
export type RunId6 = string | null
export type SchemaVersion2 = number
export type Sequence2 = number
export type SessionId4 = string
export type Type24 = "interaction_response"
export type CreatedAt5 = string
export type Id24 = string
export type Code1 = string
export type Details = {
  [k: string]: unknown
} | null
export type Message2 = string
export type RunId7 = string | null
export type SchemaVersion3 = number
export type Sequence3 = number
export type SessionId5 = string
export type Type25 = "notice"
export type CreatedAt6 = string
export type Id25 = string
export type Id26 = string
export type Status4 = "pending" | "in_progress" | "completed"
export type Text4 = string
export type Items = PlanItem[]
export type PlanId = string
export type Revision3 = number
export type Title3 = string | null
export type UpdatedAt2 = string
export type RunId8 = string | null
export type SchemaVersion4 = number
export type Sequence4 = number
export type SessionId6 = string
export type Type26 = "plan"
export type Entries = (MessageEntry | InteractionRequestEntry | InteractionResponseEntry | NoticeEntry | PlanEntry)[]
export type ProtocolVersion3 = 1
export type Runs = RunView[]
export type CreatedAt7 = string
export type Id27 = string
export type PermissionMode2 = "ask_changes" | "ask_dangerous" | "full_access"
export type ProjectId3 = string | null
export type Status5 = "active" | "archived" | "closing" | "deleted"
export type Title4 = string | null
export type UpdatedAt3 = string
export type UserId = string
export type WorkspaceAccess = "read_only" | "read_write"
export type WorkspaceId = string
export type Type27 = "snapshot"
export type ProtocolVersion4 = 1
export type Type28 = "run.updated"
export type Delta = string
export type DraftId = string
export type EndOffset1 = number
export type PartId = string
export type PartType = "text" | "reasoning_summary"
export type ProtocolVersion5 = 1
export type RunId9 = string
export type StartOffset = number
export type Type29 = "assistant.delta"
export type ProtocolVersion6 = 1
export type RunId10 = string
export type Type30 = "tool.updated"
export type ProtocolVersion7 = 1
export type RunId11 = string
export type Type31 = "interaction.requested"
export type Entry = MessageEntry | InteractionRequestEntry | InteractionResponseEntry | NoticeEntry | PlanEntry
export type ProtocolVersion8 = 1
export type Type32 = "entry.committed"
export type ProtocolVersion9 = 1

export interface AgentUiContractBundle {
  artifact: AgentArtifactView
  bootstrap: AgentUiBootstrap
  event: Event
  protocol_version?: ProtocolVersion9
  snapshot: SessionSnapshot
}
export interface AgentArtifactView {
  created_at: CreatedAt
  id: Id
  payload?: Payload
  protocol_version?: ProtocolVersion
  resource_ref?: StoredArtifactResourceView | null
  run_id?: RunId
  session_id: SessionId
  summary?: Summary
  title: Title
  type: Type
  updated_at: UpdatedAt
}
export interface StoredArtifactResourceView {
  filename: Filename
  kind?: Kind
  mime_type: MimeType
  sha256: Sha256
  size_bytes: SizeBytes
}
export interface AgentUiBootstrap {
  capabilities?: UiCapabilities
  composer_hint?: ComposerHint
  execution_scope?: ExecutionScopeSelection
  execution_targets?: ExecutionTargets
  model?: ModelSummary | null
  permission_mode?: PermissionMode
  protocol_version?: ProtocolVersion1
  starter_prompts?: StarterPrompts1
}
export interface UiCapabilities {
  approvals?: Approvals
  artifacts?: Artifacts
  edit_and_resend?: EditAndResend
  multi_target_execution?: MultiTargetExecution
  reasoning?: Reasoning
  retry?: Retry
  starter_prompts?: StarterPrompts
  tool_activity?: ToolActivity
}
export interface ExecutionScopeSelection {
  mode?: Mode
  target_ids?: TargetIds
}
export interface ExecutionTargetView {
  alias: Alias
  disabled_reason?: DisabledReason
  handle: Handle
  id: Id1
  kind: Kind1
  primary?: Primary
  status?: Status
}
export interface ModelSummary {
  catalog_model_id?: CatalogModelId
  display_name: DisplayName
  model: Model
  provider: Provider
  supports_reasoning?: SupportsReasoning
  supports_tools?: SupportsTools
  supports_vision?: SupportsVision
}
export interface StarterPromptView {
  icon?: Icon
  id: Id2
  prompt: Prompt
  title: Title1
}
export interface SnapshotEvent {
  protocol_version?: ProtocolVersion2
  snapshot: SessionSnapshot
  type?: Type27
}
export interface SessionSnapshot {
  active_run?: ActiveRunView | null
  capabilities?: UiCapabilities
  entries: Entries
  protocol_version?: ProtocolVersion3
  runs: Runs
  session: SessionView
}
export interface ActiveRunView {
  assistant_draft?: AssistantDraftView | null
  pending_interaction?: PendingInteractionView | null
  run: RunView
  tool_progress?: ToolProgress
}
export interface AssistantDraftView {
  id: Id3
  parts: Parts
  run_id: RunId1
}
export interface AssistantDraftPartView {
  end_offset?: EndOffset
  id: Id4
  text?: Text
  type: Type1
}
export interface PendingInteractionView {
  interaction_id: InteractionId
  request: Request
  revision: Revision
  run_id: RunId2
}
export interface AskUserInteractionRequest {
  call_id: CallId
  questions: Questions
  type?: Type2
}
export interface AskUserQuestion {
  header: Header
  id: Id5
  multi_select?: MultiSelect
  options: Options
  question: Question
}
export interface InteractionOption {
  description?: Description
  id: Id6
  label: Label
  recommended?: Recommended
}
export interface ApprovalInteractionRequest {
  allowed_responses: AllowedResponses
  call_id: CallId1
  input_preview?: InputPreview
  risk: ApprovalRiskView
  summary: Summary1
  target?: ToolTargetView | null
  tool_name: ToolName
  type?: Type3
}
export interface ApprovalRiskView {
  affected_resources?: AffectedResources
  effects?: Effects
  level: Level
  reasons?: Reasons
}
export interface ToolTargetView {
  alias: Alias1
  handle: Handle1
  id: Id7
  kind: Kind2
  root?: Root
}
export interface RecoveryInteractionRequest {
  call_id: CallId2
  message: Message
  options: Options1
  tool_name: ToolName1
  type?: Type4
}
export interface RunView {
  completed_at?: CompletedAt
  created_at: CreatedAt1
  error?: RunErrorView | null
  id: Id8
  phase?: Phase
  revision?: Revision1
  session_id: SessionId1
  settings?: RunSettingsView | null
  started_at?: StartedAt
  status: Status1
  termination_reason?: TerminationReason
  updated_at: UpdatedAt1
}
export interface RunErrorView {
  code: Code
  message: Message1
}
export interface RunSettingsView {
  allowed_targets?: AllowedTargets
  execution_scope: ExecutionScopeSelection
  model: ModelSummary
  permission_mode: PermissionMode1
}
export interface ToolProgressView {
  arguments?: Arguments
  call_id: CallId3
  category: Category
  completed_at?: CompletedAt1
  display_name: DisplayName1
  error?: Error
  execution_mode: ExecutionMode
  group_id: GroupId
  input_summary?: InputSummary
  name: Name
  output_summary?: OutputSummary
  public_details?: PublicDetails
  revision?: Revision2
  started_at?: StartedAt1
  status: Status2
  summary: Summary2
  target?: ToolTargetView | null
}
export interface Arguments {
  [k: string]: JsonValue
}
export interface ToolPublicDetail {
  copyable?: Copyable
  format?: Format
  id: Id9
  kind: Kind3
  label?: Label1
  redacted?: Redacted
  truncated?: Truncated
  value: Value
}
export interface MessageEntry {
  created_at: CreatedAt2
  id: Id10
  payload: MessagePayload
  run_id?: RunId4
  schema_version?: SchemaVersion
  sequence: Sequence
  session_id: SessionId2
  type?: Type19
}
export interface MessagePayload {
  parts: Parts1
  role: Role
}
export interface TextPart {
  id: Id11
  text: Text1
  type?: Type5
}
export interface ReasoningSummaryPart {
  id: Id12
  text: Text2
  type?: Type6
}
export interface AttachmentRefPart {
  attachment_id: AttachmentId
  filename: Filename1
  id: Id13
  kind: Kind4
  mime_type?: MimeType1
  size_bytes?: SizeBytes1
  type?: Type7
}
export interface FileRefPart {
  attachment_id?: AttachmentId1
  id: Id14
  label: Label2
  path?: Path
  project_id?: ProjectId
  type?: Type8
}
export interface DirectoryRefPart {
  attachment_id?: AttachmentId2
  id: Id15
  label: Label3
  path?: Path1
  project_id?: ProjectId1
  type?: Type9
}
export interface WorkflowRefPart {
  id: Id16
  label: Label4
  project_id?: ProjectId2
  type?: Type10
  workflow_id: WorkflowId
}
export interface RunRefPart {
  id: Id17
  label: Label5
  run_id: RunId3
  type?: Type11
}
export interface ArtifactRefPart {
  artifact_id: ArtifactId
  id: Id18
  media_type?: MediaType
  title?: Title2
  type?: Type12
}
export interface ToolCallPart {
  arguments?: Arguments1
  call_id: CallId4
  category?: Category1
  display_name: DisplayName2
  execution_mode: ExecutionMode1
  group_id: GroupId1
  id: Id19
  name: Name1
  public_details?: PublicDetails1
  summary: Summary3
  target?: ToolTargetView | null
  type?: Type13
}
export interface Arguments1 {
  [k: string]: JsonValue
}
export interface ToolResultPart {
  call_id: CallId5
  completed_at?: CompletedAt2
  error?: Error1
  id: Id20
  output?: Output
  public_details?: PublicDetails2
  started_at?: StartedAt2
  status: Status3
  summary?: Summary4
  target?: ToolTargetView | null
  type?: Type18
}
export interface ToolTextOutput {
  text: Text3
  type?: Type14
}
export interface ToolJsonOutput {
  type?: Type15
  value: JsonValue
}
export interface ToolContentPartsOutput {
  parts: Parts2
  type?: Type17
}
export interface UnknownPart {
  display_text: DisplayText
  id: Id21
  original_type: OriginalType
  type?: Type16
}
export interface InteractionRequestEntry {
  created_at: CreatedAt3
  id: Id22
  payload: InteractionRequestPayload
  run_id?: RunId5
  schema_version?: SchemaVersion1
  sequence: Sequence1
  session_id: SessionId3
  type?: Type20
}
export interface InteractionRequestPayload {
  interaction_id: InteractionId1
  request: Request1
}
export interface InteractionResponseEntry {
  created_at: CreatedAt4
  id: Id23
  payload: InteractionResponsePayload
  run_id?: RunId6
  schema_version?: SchemaVersion2
  sequence: Sequence2
  session_id: SessionId4
  type?: Type24
}
export interface InteractionResponsePayload {
  interaction_id: InteractionId2
  response: Response
}
export interface AskUserInteractionResponse {
  answers: Answers
  type?: Type21
}
export interface Answers {
  [k: string]: JsonValue
}
export interface ApprovalInteractionResponse {
  approved: Approved
  type?: Type22
}
export interface RecoveryInteractionResponse {
  choice: Choice
  type?: Type23
}
export interface NoticeEntry {
  created_at: CreatedAt5
  id: Id24
  payload: NoticePayload
  run_id?: RunId7
  schema_version?: SchemaVersion3
  sequence: Sequence3
  session_id: SessionId5
  type?: Type25
}
export interface NoticePayload {
  code: Code1
  details?: Details
  message: Message2
}
export interface PlanEntry {
  created_at: CreatedAt6
  id: Id25
  payload: PlanPayload
  run_id?: RunId8
  schema_version?: SchemaVersion4
  sequence: Sequence4
  session_id: SessionId6
  type?: Type26
}
export interface PlanPayload {
  items: Items
  plan_id: PlanId
  revision: Revision3
  title?: Title3
  updated_at: UpdatedAt2
}
export interface PlanItem {
  id: Id26
  status: Status4
  text: Text4
}
export interface SessionView {
  created_at: CreatedAt7
  execution_scope?: ExecutionScopeSelection
  id: Id27
  model: ModelSummary
  permission_mode: PermissionMode2
  project_id?: ProjectId3
  status: Status5
  title?: Title4
  updated_at: UpdatedAt3
  user_id: UserId
  workspace_access: WorkspaceAccess
  workspace_id: WorkspaceId
}
export interface RunUpdatedEvent {
  protocol_version?: ProtocolVersion4
  run: RunView
  type?: Type28
}
export interface AssistantDeltaEvent {
  delta: Delta
  draft_id: DraftId
  end_offset: EndOffset1
  part_id: PartId
  part_type: PartType
  protocol_version?: ProtocolVersion5
  run_id: RunId9
  start_offset: StartOffset
  type?: Type29
}
export interface ToolUpdatedEvent {
  protocol_version?: ProtocolVersion6
  run_id: RunId10
  tool: ToolProgressView
  type?: Type30
}
export interface InteractionRequestedEvent {
  interaction: PendingInteractionView
  protocol_version?: ProtocolVersion7
  run_id: RunId11
  type?: Type31
}
export interface EntryCommittedEvent {
  entry: Entry
  protocol_version?: ProtocolVersion8
  type?: Type32
}

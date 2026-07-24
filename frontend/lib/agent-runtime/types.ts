export type AgentPermissionMode = "ask_each_action" | "guarded_auto" | "bypass"
export type AgentAutomationMode = "advise_only" | "assisted" | "autonomous"
export type AgentPendingStrategy = "future_only" | "approve_pending_tools"
export type AgentPendingReconciliation = {
  affected_count: number
  excluded_count: number
  already_resolved_count: number
}
export type AgentMode = "plan" | "execution"
export type AgentActionDecision = "approve" | "reject" | "answer"
export type AgentSessionStatus = "active" | "archived" | "deleted"
export type AgentTurnStatus =
  | "queued"
  | "running"
  | "waiting_user"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled"

export type AgentModelSelection = {
  provider?: string | null
  model?: string | null
  model_id?: string | null
  profile_id?: string | null
}

export type AgentExecutionTargetKind = "local" | "remote_ssh"

export type AgentExecutionTarget = {
  kind?: AgentExecutionTargetKind
  type?: AgentExecutionTargetKind
  remote_connection_id?: string | null
  connection_id?: string | null
}

export type AgentExecutionScopeMode = "auto" | "manual"

export type AgentExecutionScopeTarget = AgentExecutionTarget

export type AgentExecutionScope = {
  mode: AgentExecutionScopeMode
  selected_targets?: AgentExecutionScopeTarget[] | null
}

export type AgentTokenUsageSummary = {
  has_token_usage: boolean
  input_tokens: number
  output_tokens: number
  total_tokens: number
  cached_input_tokens?: number | null
  reasoning_tokens?: number | null
  context_window?: number | null
  max_output_tokens?: number | null
  turns_with_usage: number
  raw_totals: Record<string, number>
}

export type AgentRuntimeSkill = {
  name: string
  title?: string | null
  version: string
  description: string
  category?: string | null
  tags: string[]
  source?: string | null
  root?: string | null
  path?: string | null
}

export type AgentRuntimeWorkflowMention = {
  id: string
  name: string
  version: string
  engine: string
  source: string
  description?: string | null
  scope: "project" | "global"
  projectId?: string | null
  pinned?: boolean
}

export type AgentRuntimeSession = {
  id: string
  project_id?: string | null
  workspace_id: string
  user_id: string
  title?: string | null
  role_profile: string
  permission_mode: AgentPermissionMode
  automation_mode: AgentAutomationMode
  permission_policy_version?: number
  default_model_profile_id?: string | null
  runtime_mode: string
  prompt_snapshot?: Record<string, unknown> | null
  toolset_policy?: Record<string, unknown> | null
  context_policy?: Record<string, unknown> | null
  compression_state?: Record<string, unknown> | null
  lineage?: Record<string, unknown> | null
  model_selection?: AgentModelSelection | null
  execution_target?: AgentExecutionTarget | null
  execution_scope?: AgentExecutionScope | null
  token_usage_summary?: AgentTokenUsageSummary | null
  status: AgentSessionStatus
  pending_strategy?: AgentPendingStrategy | null
  pending_reconciliation?: AgentPendingReconciliation | null
  metadata?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export type AgentRuntimeFileRefPart = {
  kind: "file_ref"
  path: string
  label?: string
  includeContent?: boolean
}

export type AgentRuntimeWorkflowRefPart = {
  kind: "workflow_ref"
  workflow_id?: string | null
  project_id?: string | null
  scope?: "project" | "global"
  display_name?: string | null
  display_version?: string | null
}

export type AgentRuntimeTextInputPart = {
  type: "text"
  text: string
}

export type AgentRuntimeInputPart =
  | AgentRuntimeTextInputPart
  | AgentRuntimeFileRefPart
  | AgentRuntimeWorkflowRefPart

export type AgentRuntimeTurn = {
  id: string
  session_id: string
  project_id?: string | null
  workspace_id: string
  user_id: string
  input_text: string
  input_parts?: AgentRuntimeInputPart[] | null
  active_skill_names?: string[] | null
  status: AgentTurnStatus
  model_selection?: AgentModelSelection | null
  model_profile_snapshot?: Record<string, unknown> | null
  final_text?: string | null
  token_usage?: Record<string, unknown> | null
  termination_reason?: string | null
  loop_state?: Record<string, unknown> | null
  iteration_count: number
  budget_snapshot?: Record<string, unknown> | null
  interrupt_requested_at?: string | null
  error_code?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
}

export type AgentRuntimeEvent = {
  id: string
  session_id: string
  turn_id?: string | null
  seq: number
  type: string
  payload: Record<string, unknown>
  visibility: "user" | "internal" | "audit"
  schema_version: number
  created_at: string
  updated_at: string
}

export type AgentRuntimeTextBlockStatus =
  | "streaming"
  | "completed"
  | "failed"
  | "cancelled"

export type AgentRuntimeTextBlockSource = "snapshot" | "events" | "snapshot+events"

export type AgentRuntimeTextBlock = {
  id: string
  turnId: string
  messageId: string | null
  seqStart: number
  seqEnd: number
  text: string
  status: AgentRuntimeTextBlockStatus
  source: AgentRuntimeTextBlockSource
  sources: AgentRuntimeSource[]
  footerSources: AgentRuntimeSource[]
}

export type AgentRuntimeSourceType =
  | "web"
  | "pubmed"
  | "ncbi"
  | "biorxiv"
  | "github"
  | "docs"
  | "workflow"
  | "artifact"

export type AgentRuntimeSource = {
  id: string
  title: string
  url: string
  domain: string
  snippet?: string | null
  sourceType: AgentRuntimeSourceType | string
  query?: string | null
  toolRunId?: string | null
  citationId?: string | null
  citationAliases?: string[]
  accessedAt?: string | null
  resultCount?: number | null
}

type AgentRuntimeThinkingState = {
  content: string
  isComplete: boolean
}

export type AgentRuntimeThinkingBlock = {
  id: string
  turnId: string
  messageId: string | null
  seqStart: number
  seqEnd: number
  content: string
  isComplete: boolean
}

export type AgentRuntimeToolCallState = {
  callId: string
  name: string
  status: string
  index: number
  arguments?: Record<string, unknown>
  argumentsDelta?: string | null
}

export type AgentRuntimeAssistantState = {
  messageId: string | null
  text: string
  textBlocks: AgentRuntimeTextBlock[]
  status: "pending" | "streaming" | "completed" | "failed" | "cancelled"
  errorMessage?: string | null
  thinking?: AgentRuntimeThinkingState | null
  thinkingBlocks: AgentRuntimeThinkingBlock[]
  toolCalls: AgentRuntimeToolCallState[]
}

export type AgentRuntimeToolActivityStatus =
  | "building"
  | "requested"
  | "waiting"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "rejected"

export type AgentRuntimeToolActivity = {
  id: string
  callId: string | null
  actionId: string | null
  name: string
  status: AgentRuntimeToolActivityStatus
  arguments?: Record<string, unknown> | null
  inputPreview?: string | null
  outputPreview?: string | null
  exitCode?: number | null
  durationMs?: number | null
  errorMessage?: string | null
  relatedFiles: string[]
  summary?: string | null
  sources: AgentRuntimeSource[]
  sourceQuery?: string | null
  sourceResultCount?: number | null
  artifactId?: string | null
  artifactType?: string | null
  seqStart: number
  seqEnd: number
}

export type AgentRuntimeActivityGroupKind =
  | "search"
  | "workspace"
  | "read"
  | "command"
  | "write"
  | "register"
  | "run"
  | "verify"
  | "other"

export type AgentRuntimeActivityGroup = {
  id: string
  kind: AgentRuntimeActivityGroupKind
  status: AgentRuntimeToolActivityStatus
  activities: AgentRuntimeToolActivity[]
  seqStart: number
  seqEnd: number
}

export type AgentRuntimeInlinePlanStatus = "pending" | "approved" | "rejected" | "answered"

export type AgentRuntimeInlinePlan = {
  actionId: string
  plan: string
  status: AgentRuntimeInlinePlanStatus
}

export type AgentRuntimeDecisionState =
  | "pending"
  | "approved"
  | "rejected"
  | "answered"
  | "completed"
  | "failed"
  | "cancelled"

export type AgentRuntimeDecisionView = AgentWaitingDecision & {
  state: AgentRuntimeDecisionState
  turnId: string
  seqStart: number
  seqEnd: number
  scrollTargetId: string
}

type AgentRuntimeSegmentBase = {
  id: string
  turnId: string
  seqStart: number
  seqEnd: number
  status: string
}

export type AgentRuntimeAssistantTextSegment = AgentRuntimeSegmentBase & {
  kind: "assistant_text"
  textBlock: AgentRuntimeTextBlock
}

export type AgentRuntimeAssistantThinkingSegment = AgentRuntimeSegmentBase & {
  kind: "assistant_thinking"
  thinkingBlock: AgentRuntimeThinkingBlock
}

export type AgentRuntimeActivityGroupSegment = AgentRuntimeSegmentBase & {
  kind: "activity_group"
  activityGroup: AgentRuntimeActivityGroup
}

export type AgentRuntimeDecisionSegment = AgentRuntimeSegmentBase & {
  kind: "decision"
  decision: AgentRuntimeDecisionView
}

export type AgentRuntimeTurnErrorSegment = AgentRuntimeSegmentBase & {
  kind: "turn_error"
  message: string | null
}

export type AgentRuntimeUserSteerSegment = AgentRuntimeSegmentBase & {
  kind: "user_steer"
  steer: {
    id: string
    text: string
    status: "pending" | "delivered" | "cancelled"
    inputDisplay?: Record<string, unknown> | null
  }
}

export type AgentRuntimeTranscriptSegment =
  | AgentRuntimeAssistantTextSegment
  | AgentRuntimeAssistantThinkingSegment
  | AgentRuntimeActivityGroupSegment
  | AgentRuntimeDecisionSegment
  | AgentRuntimeUserSteerSegment
  | AgentRuntimeTurnErrorSegment

export type AgentRuntimeTimelineEntry = {
  turn: AgentRuntimeTurn
  assistant: AgentRuntimeAssistantState
  activities: AgentRuntimeToolActivity[]
  activityGroups: AgentRuntimeActivityGroup[]
  inlinePlans: AgentRuntimeInlinePlan[]
  segments: AgentRuntimeTranscriptSegment[]
}

export type AgentRuntimeStatePayload = {
  session: AgentRuntimeSession
  turns: AgentRuntimeTurn[]
  events: AgentRuntimeEvent[]
}

export type AgentRuntimeArtifact = {
  id: string
  session_id: string
  turn_id: string
  action_id?: string | null
  type: string
  title: string
  summary?: string | null
  payload?: Record<string, unknown> | null
  file_path?: string | null
  resource_ref?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export type AgentTodoStatus = "pending" | "in_progress" | "completed"

export type AgentTodoDisplayStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "stopped"
  | "failed"
  | "cancelled"

export type AgentTodoItem = {
  content: string
  status: AgentTodoStatus
  activeForm?: string
}

export type AgentTodoDisplayItem = AgentTodoItem & {
  displayStatus: AgentTodoDisplayStatus
  terminalReason?: string | null
  errorMessage?: string | null
}

export type AgentAskUserOption = {
  label: string
  description?: string
  recommended?: boolean
}

export type AgentAskUserQuestion = {
  question: string
  header: string
  multiSelect?: boolean
  options: AgentAskUserOption[]
}

export type AgentWaitingDecision = {
  actionId: string
  name?: string
  kind?: string
  riskLevel?: string
  toolCallId?: string | null
  inputPreview?: string | null
  answer?: AgentAnswer | null
  target?: AgentDecisionTarget | null
  interaction?:
    | { kind: "user_input"; questions: AgentAskUserQuestion[] }
    | { kind: "plan_approval"; plan: string }
    | null
}

export type AgentDecisionTarget = {
  kind: AgentExecutionTargetKind | "container"
  trustDomain?: string | null
  identity?: string | null
  connectionId?: string | null
}

export type AgentAnswer = Record<string, string | string[]>

export type AgentFsEntry = {
  name: string
  path: string
  type: "file" | "dir"
  size?: number | null
}

export type AgentFsTree = {
  path: string
  entries: AgentFsEntry[]
}

export type AgentFsFile = {
  path: string
  content: string
  truncated: boolean
  size: number
  language?: string | null
  mime_type?: string | null
  binary?: boolean
}

export type AgentPermissionMode = "ask_each_action" | "guarded_auto" | "bypass"
export type AgentAutomationMode = "advise_only" | "assisted" | "autonomous"
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

export type AgentRuntimeSession = {
  id: string
  project_id?: string | null
  workspace_id: string
  user_id: string
  title?: string | null
  role_profile: string
  permission_mode: AgentPermissionMode
  automation_mode: AgentAutomationMode
  default_model_profile_id?: string | null
  runtime_mode: string
  prompt_snapshot?: Record<string, unknown> | null
  toolset_policy?: Record<string, unknown> | null
  context_policy?: Record<string, unknown> | null
  compression_state?: Record<string, unknown> | null
  lineage?: Record<string, unknown> | null
  model_selection?: AgentModelSelection | null
  status: AgentSessionStatus
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

export type AgentRuntimeTextInputPart = {
  type: "text"
  text: string
}

export type AgentRuntimeInputPart = AgentRuntimeTextInputPart | AgentRuntimeFileRefPart

export type AgentRuntimeTurn = {
  id: string
  session_id: string
  project_id?: string | null
  workspace_id: string
  user_id: string
  input_text: string
  input_parts?: AgentRuntimeInputPart[] | null
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

type AgentRuntimeThinkingState = {
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
  status: "pending" | "streaming" | "completed" | "failed" | "cancelled"
  errorMessage?: string | null
  thinking?: AgentRuntimeThinkingState | null
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
  artifactId?: string | null
  artifactType?: string | null
}

export type AgentRuntimeActivityGroupKind =
  | "workspace"
  | "read"
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
}

export type AgentRuntimeInlinePlanStatus = "pending" | "approved" | "rejected" | "answered"

export type AgentRuntimeInlinePlan = {
  actionId: string
  plan: string
  status: AgentRuntimeInlinePlanStatus
}

export type AgentRuntimeTimelineEntry = {
  turn: AgentRuntimeTurn
  assistant: AgentRuntimeAssistantState
  activities: AgentRuntimeToolActivity[]
  activityGroups: AgentRuntimeActivityGroup[]
  inlinePlans: AgentRuntimeInlinePlan[]
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

export type AgentTodoItem = {
  content: string
  status: AgentTodoStatus
  activeForm?: string
}

export type AgentAskUserOption = {
  label: string
  description?: string
}

export type AgentAskUserQuestion = {
  question: string
  header: string
  multiSelect?: boolean
  options: AgentAskUserOption[]
}

// Shape of the enriched `action.waiting_decision` event payload (see the
// backend AgentActionService): enough for the UI to render the approval /
// question / plan card without a second fetch.
export type AgentWaitingDecision = {
  actionId: string
  name?: string
  kind?: string
  riskLevel?: string
  toolCallId?: string | null
  inputPreview?: string | null
  interaction?:
    | { kind: "user_input"; questions: AgentAskUserQuestion[] }
    | { kind: "plan_approval"; plan: string }
    | null
}

// User's reply to ask_user, keyed by question header → selected label(s).
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
}

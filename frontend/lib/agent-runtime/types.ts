export type AgentPermissionMode = "ask_each_action" | "guarded_auto" | "bypass"
export type AgentAutomationMode = "advise_only" | "assisted" | "autonomous"
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

export type AgentRuntimeTurn = {
  id: string
  session_id: string
  project_id?: string | null
  workspace_id: string
  user_id: string
  input_text: string
  input_parts?: Array<Record<string, unknown>> | null
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

export type AgentRuntimeStatePayload = {
  session: AgentRuntimeSession
  turns: AgentRuntimeTurn[]
  events: AgentRuntimeEvent[]
}

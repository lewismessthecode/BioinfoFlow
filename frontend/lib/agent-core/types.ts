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
export type AgentActionStatus =
  | "requested"
  | "waiting_decision"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "rejected"
export type AgentActionDecision = "approve" | "reject" | "modify"

export type AgentModelSelection = {
  provider?: string | null
  model?: string | null
  model_id?: string | null
  profile_id?: string | null
}

export type AgentCoreSession = {
  id: string
  project_id: string
  workspace_id: string
  user_id: string
  title?: string | null
  role_profile: string
  permission_mode: AgentPermissionMode
  automation_mode: AgentAutomationMode
  default_model_profile_id?: string | null
  model_selection?: AgentModelSelection | null
  status: AgentSessionStatus
  metadata?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export type AgentCoreTurn = {
  id: string
  session_id: string
  project_id: string
  workspace_id: string
  user_id: string
  input_text: string
  input_parts?: Array<Record<string, unknown>> | null
  status: AgentTurnStatus
  model_selection?: AgentModelSelection | null
  model_profile_snapshot?: Record<string, unknown> | null
  final_text?: string | null
  token_usage?: Record<string, unknown> | null
  error_code?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
}

export type AgentCoreEvent = {
  id: string
  session_id: string
  turn_id: string
  seq: number
  type: string
  payload: Record<string, unknown>
  visibility: "user" | "internal" | "audit"
  schema_version: number
  created_at: string
  updated_at: string
}

export type AgentCoreAction = {
  id: string
  session_id: string
  turn_id: string
  parent_action_id?: string | null
  kind: string
  name: string
  input: Record<string, unknown>
  input_preview?: string | null
  redacted_input?: Record<string, unknown> | null
  risk_level: string
  risk_reasons?: unknown[] | null
  read_scope?: unknown[] | null
  write_scope?: unknown[] | null
  affected_resources?: unknown[] | null
  permission_decision?: Record<string, unknown> | null
  status: AgentActionStatus
  result?: Record<string, unknown> | null
  error?: Record<string, unknown> | null
  audit_summary?: string | null
  rollback_hint?: string | null
  artifact_policy?: Record<string, unknown> | null
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
}

export type AgentCoreArtifact = {
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

export type AgentCoreMemory = {
  id: string
  workspace_id: string
  project_id?: string | null
  session_id?: string | null
  scope: string
  type: string
  content: Record<string, unknown>
  source?: Record<string, unknown> | null
  confidence?: number | null
  status: "proposed" | "accepted" | "rejected" | "disabled"
  created_at: string
  updated_at: string
}

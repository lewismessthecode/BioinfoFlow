export type Pagination = {
  limit?: number
  has_more?: boolean
  next_cursor?: string | null
  total_count?: number
}

export type ApiMeta = {
  timestamp?: string
  request_id?: string
  pagination?: Pagination
  status?: Record<string, unknown>
}

export type ApiErrorPayload = {
  code?: string
  message: string
  details?: unknown
}

export type ApiEnvelope<T> =
  | { success: true; data: T; meta?: ApiMeta }
  | { success: false; error: ApiErrorPayload; meta?: ApiMeta }

export type TerminalConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "disconnected"
  | "error"
  | "exited"

export type TerminalSession = {
  id: string
  project_id: string
  shell: string
  cwd: string
  status: string
  target_type: "local" | "remote"
  target_label: string
  remote_connection_id?: string | null
}


export type TerminalServerMessage =
  | { type: "ready"; session: TerminalSession }
  | { type: "output"; data: string }
  | { type: "cwd"; cwd: string }
  | { type: "exit"; exit_code: number }
  | { type: "error"; message: string }
  | { type: "pong" }

export type Project = {
  id: string
  name: string
  description?: string | null
  storage_mode?: "managed" | "external" | "remote"
  project_root?: string
  external_root_path?: string | null
  remote_connection_id?: string | null
  remote_root_path?: string | null
  data_roots?: string[] | null
  is_default?: boolean
  created_at?: string
  updated_at?: string
}

export type WorkflowSource = "nf-core" | "github" | "local"
export type WorkflowEngine = "nextflow" | "wdl"

export type WorkflowParameter = {
  name: string
  type: string
  optional: boolean
  default: string | null
  description: string | null
  value_kind?: "scalar" | "file" | "directory" | "file_list"
  source_hint?: "project" | "deliveries" | "reference" | "mixed"
  is_internal?: boolean
}

export type WorkflowTask = {
  name: string
  inputs: string[]
  outputs: string[]
  container: string | null
}

export type WorkflowDependency = {
  source: string
  target: string
}

export type WorkflowSchema = {
  workflow_name: string | null
  version: string | null
  description: string | null
  inputs: WorkflowParameter[]
  outputs: WorkflowParameter[]
  tasks: WorkflowTask[]
  dependencies: WorkflowDependency[]
}

// Legacy submission hint shape — backend still serializes this column on
// Workflow rows for back-compat until Phase 3 of the run-layer rewrite drops
// the column. New code reads /workflows/{id}/form-spec instead and ignores
// these fields. Kept as `unknown` so the API contract stays accurate without
// inviting consumers to depend on the old shape.
export type Workflow = {
  id: string
  name: string
  description?: string | null
  source: WorkflowSource
  engine: WorkflowEngine
  source_ref?: string | null
  entrypoint_relpath?: string | null
  bundle_kind?: "local_bundle" | "remote_ref" | string | null
  version: string
  estimated_time?: string | null
  schema_json?: WorkflowSchema | null
  schema_json_data?: WorkflowSchema | null
  submission_hint?: unknown | null
  submission_hint_data?: unknown | null
  created_at?: string
  updated_at?: string
}

export type WorkflowValidationError = {
  line: number | null
  column: number | null
  message: string
  severity: string
}

export type ValidateWorkflowResponse = {
  valid: boolean
  errors: WorkflowValidationError[]
  warnings: WorkflowValidationError[]
  schema: WorkflowSchema | null
  dag: DagData | null
}

export type ProjectWorkflowGroup = {
  source: WorkflowSource
  name: string
  pinned_workflow: Workflow
  versions: Workflow[]
}

export type HubWorkflowGroup = {
  source: WorkflowSource
  name: string
  engine: WorkflowEngine
  latest_workflow: Workflow
  versions: Workflow[]
}

export type RunStatus = "pending" | "queued" | "preparing" | "running" | "completed" | "failed" | "cancelled"

export type RunError = {
  stage: "validation" | "preparation" | "execution" | "post"
  code: string
  message: string
  hint?: string | null
}

export type Run = {
  id: string
  run_id: string
  project_id: string
  workflow_id?: string | null
  status: RunStatus
  config: Record<string, unknown>
  samplesheet_path?: string | null
  started_at?: string | null
  completed_at?: string | null
  duration_seconds?: number | null
  samples_count: number
  tasks_total: number
  tasks_completed: number
  current_task?: string | null
  error_message?: string | null
  error?: RunError | null
  last_heartbeat_at?: string | null
  nextflow_run_name?: string | null
  created_at?: string
  updated_at?: string
}

export type RunLogEntry = {
  message: string
  task?: string | null
  timestamp?: string | null
  level?: string | null
}

export type RunLogs = {
  logs: RunLogEntry[]
}

export type RunOutputFile = {
  name: string
  path: string
  uri?: string | null
  size_bytes?: number | null
  type: "file" | "directory"
}

export type RunOutputs = {
  files: RunOutputFile[]
}

export type RetryPolicy = {
  max_retries: number
  delay_seconds: number
  backoff_multiplier: number
  max_delay_seconds: number
  retry_on: string[]
}


export type ActiveRun = {
  run_id: string
  weight: number
  workflow_name: string | null
}

export type SchedulerStatus = {
  mode: string
  effective_mode: string
  scheduler_available: boolean
  resource_monitoring_enabled: boolean
  workers: number
  queue_depth: number
  states: {
    queued: number
    dispatched: number
    completed: number
    failed: number
    cancelled: number
  }
  total_slots: number
  used_slots: number
  available_slots: number
  active_runs: ActiveRun[]
}

export type SystemResources = {
  enabled: boolean
  sampled_at: string | null
  cpu: { total: number | null; available: number | null }
  memory: { total_gb: number | null; available_gb: number | null }
  disk: { total_gb: number | null; available_gb: number | null }
  gpu: {
    count: number
    memory_gb: number
  }
}

export type ResourceStreamFrame = {
  mode: string
  effective_mode: string
  scheduler_available: boolean
  resources: SystemResources
  active_runs: ActiveRun[]
  queue_depth: number
  states?: SchedulerStatus["states"]
  total_slots?: number
  used_slots?: number
  available_slots?: number
}

export type ResourceStreamConnectionState =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"

export type AuditLogEntry = {
  id: string
  run_id: string
  action: string
  actor: string
  details?: Record<string, unknown> | null
  created_at: string
}

export type NotificationTrigger = "run.completed" | "run.failed" | "run.cancelled" | "batch.completed" | "batch.failed"

export type NotificationConfig = {
  id: string
  project_id: string
  trigger: NotificationTrigger
  webhook_url: string
  enabled: boolean
  created_at?: string
}

export type ImageStatus = "local" | "remote" | "pulling" | "failed"

export type ImageStatusMeta = {
  docker?: "available" | "unavailable"
  images_stale?: boolean
  last_synced_at?: string | null
}

export type DockerImage = {
  id: string
  name: string
  tag: string
  full_name: string
  description?: string | null
  size_bytes?: number | null
  status: ImageStatus
  registry: string
  pull_progress?: number | null
  error_message?: string | null
  labels?: Record<string, string> | null
  env?: string[] | null
  entrypoint?: string[] | null
  created_at?: string
  updated_at?: string
}

export type ContainerRegistryConfig = {
  id?: string | null
  name?: string | null
  endpoint?: string | null
  registry?: string | null
  host?: string | null
  url?: string | null
  namespace?: string | null
  provider?: string | null
  description?: string | null
  is_default?: boolean | null
  insecure?: boolean | null
  credential_source?: "none" | "env" | "stored" | string | null
  env_username_var?: string | null
  env_password_var?: string | null
  username_hint?: string | null
  password_hint?: string | null
  last_status?: "untested" | "ok" | "error" | string | null
  last_error?: string | null
  last_checked_at?: string | null
}

export type EventEnvelope<T = unknown> = {
  id: string
  event: string
  project_id: string
  timestamp: string
  data: T
  run_id?: string
  image_id?: string
}

export type RunStatusEvent = {
  run_id: string
  status: RunStatus
  current_task?: string | null
  tasks_completed?: number | null
  tasks_total?: number | null
  message?: string
}

export type RunLogEvent = {
  run_id: string
  level?: string | null
  message: string
  task?: string | null
  timestamp?: string | null
}

export type ImageProgressEvent = {
  image_id: string
  progress?: number | null
  status: ImageStatus
}

export type DagNode = {
  id: string
  type: string
  position: { x: number; y: number }
  data: {
    label: string
    status: "pending" | "queued" | "running" | "success" | "failed"
    displayLabel?: string
    duration?: number
    startedAt?: string
    inputs?: Record<string, string>
    outputs?: Record<string, string>
    logPreview?: string
    container?: string
    source?: "schema" | "runtime"
  }
}

export type DagEdge = {
  id: string
  source: string
  target: string
  animated: boolean
}

export type DagData = {
  nodes: DagNode[]
  edges: DagEdge[]
}

export type RunDagEvent = {
  run_id: string
  dag: DagData
}

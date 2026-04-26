import type { FormSpec } from "@/lib/form-spec"
import type {
  AgentConversationHistory,
  AgentConversationRead,
  AuditLogEntry,
  DagData,
  DockerImage,
  ImageStatusMeta,
  Project,
  ProjectWorkflowGroup,
  Run,
  RunLogs,
  RunOutputs,
  SchedulerStatus,
  Workflow,
} from "@/lib/types"
import type {
  DashboardStats,
  GpuInfo,
  SystemHealth,
} from "@/app/(app)/dashboard/components/dashboard-types"

type DemoDirectory = {
  name: string
  type: "directory"
  path: string
  children: DemoFileNode[]
}

type DemoFile = {
  name: string
  type: "file"
  path: string
  size_bytes?: number | null
  content: string
}

export type DemoFileNode = DemoDirectory | DemoFile

export type DemoScenario = {
  contextDefaults: {
    selectedProjectId: string
  }
  projects: Project[]
  workflows: Workflow[]
  projectWorkflowGroups: Record<string, ProjectWorkflowGroup[]>
  workflowDag: Record<string, DagData>
  workflowSource: Record<string, string>
  formSpecs: Record<string, FormSpec>
  conversations: Record<string, AgentConversationRead[]>
  conversationHistory: Record<string, AgentConversationHistory>
  runs: Run[]
  runLogs: Record<string, RunLogs>
  runOutputs: Record<string, RunOutputs>
  runDag: Record<string, DagData>
  runAudit: Record<string, AuditLogEntry[]>
  workspaceFiles: Record<string, DemoFileNode[]>
  images: DockerImage[]
  imageStatus: ImageStatusMeta
  dashboard: {
    stats: DashboardStats
    health: SystemHealth
    gpu: GpuInfo
    scheduler: SchedulerStatus
  }
}

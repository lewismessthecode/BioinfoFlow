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
import type { DemoScenario, DemoFileNode } from "./scenario"

const DEMO_PROJECT_ID = "project-demo"
const DEMO_CONVERSATION_ID = "conv-demo-main"

const demoProject: Project = {
  id: DEMO_PROJECT_ID,
  name: "Bioinfoflow Demo Project",
  description: "A seeded workspace for the Vercel demo deployment.",
  created_at: "2026-04-24T09:00:00Z",
  updated_at: "2026-04-24T09:00:00Z",
}

const workflowDag: DagData = {
  nodes: [
    {
      id: "reads_stats",
      type: "pipeline",
      position: { x: 250, y: 50 },
      data: {
        label: "READS_STATS",
        displayLabel: "Read Quality Stats",
        status: "pending",
      },
    },
    {
      id: "reference_stats",
      type: "pipeline",
      position: { x: 250, y: 200 },
      data: {
        label: "REFERENCE_STATS",
        displayLabel: "Reference Alignment",
        status: "pending",
      },
    },
    {
      id: "summary_report",
      type: "pipeline",
      position: { x: 250, y: 350 },
      data: {
        label: "SUMMARY_REPORT",
        displayLabel: "Summary Report",
        status: "pending",
      },
    },
  ],
  edges: [
    { id: "e1", source: "reads_stats", target: "reference_stats", animated: false },
    { id: "e2", source: "reference_stats", target: "summary_report", animated: false },
  ],
}

const workflows: Workflow[] = [
  {
    id: "wf-rnaseq-quant-mini",
    name: "rnaseq-quant-mini",
    description:
      "A lightweight RNA-seq quantification workflow for fast local validation.",
    source: "local",
    engine: "nextflow",
    version: "1.0.0",
    source_ref: "workflows/rnaseq-quant-mini/main.nf",
    schema_json: {
      workflow_name: "rnaseq-quant-mini",
      version: "1.0.0",
      description: "Lightweight demo pipeline",
      inputs: [
        {
          name: "reads_r1",
          type: "File",
          optional: false,
          default: null,
          description: "Read 1 FASTQ",
        },
        {
          name: "reads_r2",
          type: "File",
          optional: false,
          default: null,
          description: "Read 2 FASTQ",
        },
        {
          name: "reference",
          type: "File",
          optional: false,
          default: null,
          description: "Reference FASTA",
        },
      ],
      outputs: [
        {
          name: "summary_report",
          type: "File",
          optional: false,
          default: null,
          description: "Markdown report",
        },
      ],
      tasks: [
        {
          name: "READS_STATS",
          inputs: ["reads_r1", "reads_r2"],
          outputs: ["qc_metrics"],
          container: "community/fastqc:latest",
        },
        {
          name: "REFERENCE_STATS",
          inputs: ["reference"],
          outputs: ["alignment_summary"],
          container: "community/minimap2:latest",
        },
        {
          name: "SUMMARY_REPORT",
          inputs: ["qc_metrics", "alignment_summary"],
          outputs: ["summary_report"],
          container: "python:3.12-slim",
        },
      ],
      dependencies: [
        { source: "READS_STATS", target: "REFERENCE_STATS" },
        { source: "REFERENCE_STATS", target: "SUMMARY_REPORT" },
      ],
    },
    created_at: "2026-04-24T09:00:00Z",
    updated_at: "2026-04-24T09:00:00Z",
  },
  {
    id: "wf-variant-lite",
    name: "variant-lite",
    description: "A compact variant calling showcase workflow.",
    source: "github",
    engine: "wdl",
    version: "0.3.0",
    source_ref: "https://github.com/bioinfoflow/demo/variant-lite",
    created_at: "2026-04-18T09:00:00Z",
    updated_at: "2026-04-20T09:00:00Z",
  },
]

const projectWorkflowGroups: ProjectWorkflowGroup[] = [
  {
    source: "local",
    name: "rnaseq-quant-mini",
    pinned_workflow: workflows[0],
    versions: [workflows[0]],
  },
]

const formSpec: FormSpec = {
  fields: [
    {
      id: "reads_r1",
      label: "Read 1 FASTQ",
      section: "data",
      kind: "file",
      required: true,
      default: "deliveries/ecoli_R1.fastq.gz",
      platform_managed: false,
      allow_roots: ["project_data"],
    },
    {
      id: "reads_r2",
      label: "Read 2 FASTQ",
      section: "data",
      kind: "file",
      required: true,
      default: "deliveries/ecoli_R2.fastq.gz",
      platform_managed: false,
      allow_roots: ["project_data"],
    },
    {
      id: "reference",
      label: "Reference FASTA",
      section: "data",
      kind: "file",
      required: true,
      default: "reference/ecoli_k12.fa",
      platform_managed: false,
      allow_roots: ["reference"],
    },
    {
      id: "profile",
      label: "Execution profile",
      section: "params",
      kind: "select",
      required: true,
      default: "demo-local",
      platform_managed: false,
      options: [
        { value: "demo-local", label: "Demo Local" },
        { value: "balanced", label: "Balanced" },
      ],
    },
  ],
}

const conversation: AgentConversationRead = {
  id: DEMO_CONVERSATION_ID,
  project_id: DEMO_PROJECT_ID,
  title: "RNA-seq dry run",
  execution_policy: "auto",
  created_at: "2026-04-24T09:01:00Z",
  updated_at: "2026-04-24T09:01:00Z",
}

const conversationHistory: AgentConversationHistory = {
  conversation_id: DEMO_CONVERSATION_ID,
  project_id: DEMO_PROJECT_ID,
  title: conversation.title,
  execution_policy: "auto",
  messages: [],
}

const seededRuns: Run[] = [
  {
    id: "run-model-seeded",
    run_id: "run_seeded_001",
    project_id: DEMO_PROJECT_ID,
    workflow_id: "wf-rnaseq-quant-mini",
    status: "completed",
    config: {},
    started_at: "2026-04-24T08:30:00Z",
    completed_at: "2026-04-24T08:38:00Z",
    duration_seconds: 480,
    samples_count: 2,
    tasks_total: 3,
    tasks_completed: 3,
    current_task: null,
    created_at: "2026-04-24T08:30:00Z",
    updated_at: "2026-04-24T08:38:00Z",
  },
]

const seededRunLogs: Record<string, RunLogs> = {
  run_seeded_001: {
    logs: [
      {
        message: "Loaded paired-end FASTQs from deliveries/",
        task: "READS_STATS",
        timestamp: "2026-04-24T08:31:00Z",
        level: "info",
      },
      {
        message: "Generated summary report",
        task: "SUMMARY_REPORT",
        timestamp: "2026-04-24T08:37:40Z",
        level: "info",
      },
    ],
  },
}

const seededRunOutputs: Record<string, RunOutputs> = {
  run_seeded_001: {
    files: [
      {
        name: "summary.md",
        path: "reports/summary.md",
        size_bytes: 3241,
        type: "file",
      },
      {
        name: "counts.tsv",
        path: "counts/counts.tsv",
        size_bytes: 642,
        type: "file",
      },
      {
        name: "metrics.json",
        path: "reports/metrics.json",
        size_bytes: 452,
        type: "file",
      },
    ],
  },
}

const seededRunDag: Record<string, DagData> = {
  run_seeded_001: {
    nodes: workflowDag.nodes.map((node, index) => ({
      ...node,
      data: {
        ...node.data,
        status: "success",
        duration: [124, 188, 96][index],
      },
    })),
    edges: workflowDag.edges.map((edge) => ({ ...edge, animated: false })),
  },
}

const seededRunAudit: Record<string, AuditLogEntry[]> = {
  run_seeded_001: [
    {
      id: "audit-seeded-1",
      run_id: "run_seeded_001",
      action: "run.submitted",
      actor: "Demo Operator",
      details: { workflow: "rnaseq-quant-mini", profile: "demo-local" },
      created_at: "2026-04-24T08:30:00Z",
    },
    {
      id: "audit-seeded-2",
      run_id: "run_seeded_001",
      action: "run.completed",
      actor: "Bioinfoflow Scheduler",
      details: { duration_seconds: 480, outputs: 3 },
      created_at: "2026-04-24T08:38:00Z",
    },
  ],
}

const workspaceFiles: DemoFileNode[] = [
  {
    name: "deliveries",
    type: "directory",
    path: "deliveries",
    children: [
      {
        name: "ecoli_R1.fastq.gz",
        type: "file",
        path: "deliveries/ecoli_R1.fastq.gz",
        size_bytes: 240114,
        content: "Demo FASTQ placeholder for read 1",
      },
      {
        name: "ecoli_R2.fastq.gz",
        type: "file",
        path: "deliveries/ecoli_R2.fastq.gz",
        size_bytes: 238908,
        content: "Demo FASTQ placeholder for read 2",
      },
    ],
  },
  {
    name: "reference",
    type: "directory",
    path: "reference",
    children: [
      {
        name: "ecoli_k12.fa",
        type: "file",
        path: "reference/ecoli_k12.fa",
        size_bytes: 4411535,
        content: ">chr1\nATGCATGCATGCATGCATGC\n",
      },
    ],
  },
  {
    name: "runs",
    type: "directory",
    path: "runs",
    children: [
      {
        name: "run_seeded_001",
        type: "directory",
        path: "runs/run_seeded_001",
        children: [
          {
            name: "summary.md",
            type: "file",
            path: "runs/run_seeded_001/summary.md",
            size_bytes: 3241,
            content: "# RNA-seq demo summary\n\n- Reads passed QC\n- Reference alignment matched expected profile\n",
          },
        ],
      },
    ],
  },
  {
    name: "reports",
    type: "directory",
    path: "reports",
    children: [
      {
        name: "summary.md",
        type: "file",
        path: "reports/summary.md",
        size_bytes: 812,
        content:
          "# Demo report\n\n- Total reads: 1,234,567\n- Mean quality: Q32\n- Reference alignment: expected profile\n",
      },
      {
        name: "metrics.json",
        type: "file",
        path: "reports/metrics.json",
        size_bytes: 264,
        content:
          JSON.stringify(
            {
              total_reads: 1234567,
              mean_quality: "Q32",
              gc_content: "50.8%",
            },
            null,
            2,
          ),
      },
    ],
  },
  {
    name: "counts",
    type: "directory",
    path: "counts",
    children: [
      {
        name: "counts.tsv",
        type: "file",
        path: "counts/counts.tsv",
        size_bytes: 428,
        content: "gene\tcount\nrpoB\t145\nrecA\t92\nfusA\t211\n",
      },
    ],
  },
]

const demoImages: DockerImage[] = [
  {
    id: "img-rnaseq-toolkit",
    name: "ghcr.io/demo/rnaseq-toolkit",
    tag: "1.4.0",
    full_name: "ghcr.io/demo/rnaseq-toolkit:1.4.0",
    description: "Seeded local image for the RNA-seq golden path demo.",
    size_bytes: 181_403_648,
    status: "local",
    registry: "ghcr.io",
    labels: {
      maintainer: "Bioinfoflow",
      workflow: "rnaseq-quant-mini",
    },
    env: ["BIOINFOFLOW_DEMO=1", "PATH=/usr/local/bin:/usr/bin"],
    entrypoint: ["/bin/bash"],
    created_at: "2026-04-24T07:40:00Z",
    updated_at: "2026-04-24T07:40:00Z",
  },
  {
    id: "img-fastqc",
    name: "biocontainers/fastqc",
    tag: "0.12.1",
    full_name: "biocontainers/fastqc:0.12.1",
    description: "Recommended QC image ready to import in the demo.",
    size_bytes: 523_018_240,
    status: "remote",
    registry: "docker.io",
    labels: {
      maintainer: "BioContainers",
    },
    env: ["PATH=/usr/local/bin:/usr/bin"],
    entrypoint: ["fastqc"],
    created_at: "2026-04-23T18:15:00Z",
    updated_at: "2026-04-23T18:15:00Z",
  },
  {
    id: "img-bwa",
    name: "biocontainers/bwa",
    tag: "0.7.17",
    full_name: "biocontainers/bwa:0.7.17",
    description: "Local alignment image seeded for realistic dashboard counts.",
    size_bytes: 302_104_576,
    status: "local",
    registry: "docker.io",
    labels: {
      maintainer: "BioContainers",
    },
    env: ["PATH=/usr/local/bin:/usr/bin"],
    entrypoint: ["bwa"],
    created_at: "2026-04-23T11:00:00Z",
    updated_at: "2026-04-24T07:20:00Z",
  },
  {
    id: "img-parabricks",
    name: "nvcr.io/nvidia/clara/parabricks",
    tag: "4.4.0-1",
    full_name: "nvcr.io/nvidia/clara/parabricks:4.4.0-1",
    description: "GPU-enabled analysis image used by the health and system cards.",
    size_bytes: 5_914_837_504,
    status: "local",
    registry: "nvcr.io",
    labels: {
      maintainer: "NVIDIA",
    },
    env: ["NVIDIA_VISIBLE_DEVICES=all"],
    entrypoint: ["/opt/parabricks/parabricks"],
    created_at: "2026-04-22T10:10:00Z",
    updated_at: "2026-04-24T07:10:00Z",
  },
]

const demoImageStatus: ImageStatusMeta = {
  docker: "available",
  images_stale: false,
  last_synced_at: "2026-04-24T09:02:00Z",
}

const dashboardStats: DashboardStats = {
  runs: {
    total: 1,
    running: 0,
    completed: 1,
    failed: 0,
    queued: 0,
    pending: 0,
    cancelled: 0,
  },
  workflows: {
    total: workflows.length,
  },
  images: {
    total: 4,
    local: 3,
    remote: 1,
    pulling: 0,
  },
  projects: {
    total: 1,
  },
  recent_runs: [
    {
      run_id: "run_seeded_001",
      workflow_id: "wf-rnaseq-quant-mini",
      status: "completed",
      started_at: "2026-04-24T08:30:00Z",
      duration_seconds: 480,
      current_task: null,
    },
  ],
}

const systemHealth: SystemHealth = {
  status: "healthy",
  docker: {
    available: true,
    nvidia_runtime: true,
  },
  gpu: {
    available: true,
    parabricks_compatible: true,
  },
  parabricks: {
    image_available: true,
    image_name: "nvcr.io/nvidia/clara/parabricks:4.4.0-1",
  },
}

const gpuInfo: GpuInfo = {
  available: true,
  parabricks_compatible: true,
  gpus: [
    {
      index: 0,
      name: "NVIDIA RTX 4090",
      memory_total_mb: 24564,
      memory_free_mb: 19880,
      gpu_type: "consumer",
    },
  ],
}

const schedulerStatus: SchedulerStatus = {
  mode: "persistent",
  effective_mode: "persistent",
  scheduler_available: true,
  resource_monitoring_enabled: true,
  workers: 1,
  queue_depth: 0,
  states: {
    queued: 0,
    dispatched: 1,
    completed: 1,
    failed: 0,
    cancelled: 0,
  },
  total_slots: 1,
  used_slots: 0,
  available_slots: 1,
  active_runs: [],
}

export const DEMO_RUNTIME_SCENARIO: DemoScenario = {
  contextDefaults: {
    selectedProjectId: DEMO_PROJECT_ID,
  },
  projects: [demoProject],
  workflows,
  projectWorkflowGroups: {
    [DEMO_PROJECT_ID]: projectWorkflowGroups,
  },
  workflowDag: {
    "wf-rnaseq-quant-mini": workflowDag,
  },
  workflowSource: {
    "wf-rnaseq-quant-mini":
      "nextflow.enable.dsl=2\n\nworkflow {\n  READS_STATS()\n  REFERENCE_STATS()\n  SUMMARY_REPORT()\n}\n",
  },
  formSpecs: {
    "wf-rnaseq-quant-mini": formSpec,
  },
  conversations: {
    [DEMO_PROJECT_ID]: [conversation],
  },
  conversationHistory: {
    [DEMO_CONVERSATION_ID]: conversationHistory,
  },
  runs: seededRuns,
  runLogs: seededRunLogs,
  runOutputs: seededRunOutputs,
  runDag: seededRunDag,
  runAudit: seededRunAudit,
  workspaceFiles: {
    [DEMO_PROJECT_ID]: workspaceFiles,
  },
  images: demoImages,
  imageStatus: demoImageStatus,
  dashboard: {
    stats: dashboardStats,
    health: systemHealth,
    gpu: gpuInfo,
    scheduler: schedulerStatus,
  },
}

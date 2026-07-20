import { apiRequest } from "@/lib/api"

type FirstRunWorkflowContext = {
  id: string
  name: string
  version: string
  source: string
  engine: string
  scope: "project"
  project_id: string
}

export type FirstRunStarterContext = {
  project_id: string
  workflow: FirstRunWorkflowContext
  values: {
    samples_tsv: string
    sample_a_fastq: string
    sample_b_fastq: string
  }
}

export type FirstRunBootstrapResult = {
  ready: boolean
  created: boolean
  demo_project_id: string | null
  workflow_id: string | null
  starter_context: FirstRunStarterContext | null
}

export async function bootstrapFirstRun(): Promise<FirstRunBootstrapResult> {
  const response = await apiRequest<FirstRunBootstrapResult>(
    "/first-run/bootstrap",
    { method: "POST" },
  )
  return response.data
}

const FIRST_RUN_ACTIVATION_PREFIX = "bioinfoflow:first-run-demo-activated:"
export const LAST_USED_PROJECT_STORAGE_KEY = "bioinfoflow:last-used-project"

export function firstRunActivationStorageKey(projectId: string) {
  return `${FIRST_RUN_ACTIVATION_PREFIX}${projectId}`
}

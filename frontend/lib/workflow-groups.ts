import type { HubWorkflowGroup, Workflow } from "@/lib/types"

function compareWorkflowVersionsDesc(left: Workflow, right: Workflow): number {
  const versionOrder = right.version.localeCompare(left.version, undefined, {
    numeric: true,
    sensitivity: "base",
  })
  if (versionOrder !== 0) return versionOrder

  return (right.updated_at ?? "").localeCompare(left.updated_at ?? "")
}

export function buildHubWorkflowGroups(workflows: Workflow[]): HubWorkflowGroup[] {
  const grouped = new Map<string, Workflow[]>()

  for (const workflow of workflows) {
    const key = [workflow.source, workflow.engine, workflow.name].join("::")
    const existing = grouped.get(key)
    if (existing) {
      existing.push(workflow)
    } else {
      grouped.set(key, [workflow])
    }
  }

  return Array.from(grouped.values())
    .map((versions) => {
      const sortedVersions = [...versions].sort(compareWorkflowVersionsDesc)
      const latestWorkflow = sortedVersions[0]!
      return {
        source: latestWorkflow.source,
        name: latestWorkflow.name,
        engine: latestWorkflow.engine,
        latest_workflow: latestWorkflow,
        versions: sortedVersions,
      } satisfies HubWorkflowGroup
    })
    .sort((left, right) => compareWorkflowVersionsDesc(left.latest_workflow, right.latest_workflow))
}

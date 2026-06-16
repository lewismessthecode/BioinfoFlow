import type {
  AgentRuntimeActivityGroup,
  AgentRuntimeActivityGroupKind,
  AgentRuntimeToolActivity,
  AgentRuntimeToolActivityStatus,
} from "./types"

export function buildAgentRuntimeActivityGroups(
  activities: AgentRuntimeToolActivity[],
): AgentRuntimeActivityGroup[] {
  const groups: AgentRuntimeActivityGroup[] = []

  for (const activity of activities) {
    const kind = classifyActivity(activity)
    const previous = groups.at(-1)
    if (previous?.kind === kind) {
      previous.activities.push(activity)
      previous.status = aggregateStatus(previous.activities)
      continue
    }
    groups.push({
      id: `${kind}-${groups.length}`,
      kind,
      status: activity.status,
      activities: [activity],
    })
  }

  return groups
}

export function classifyActivity(
  activity: AgentRuntimeToolActivity,
): AgentRuntimeActivityGroupKind {
  const text = `${activity.name} ${activity.inputPreview ?? ""} ${JSON.stringify(activity.arguments ?? {})}`.toLowerCase()

  if (/\b(register|workflow|workflows?__|workflows?\.)\b/.test(text)) return "register"
  if (/\b(runs?__submit|runs?\.submit|submit run|nextflow run|miniwdl run)\b/.test(text)) return "run"
  if (/\b(test|pytest|vitest|lint|ruff|doctor|verify|validate|check)\b/.test(text)) return "verify"
  if (/\b(write|edit|patch|create|mkdir|touch|rm|delete|move|rename|files__write|files__edit)\b/.test(text)) return "write"
  if (/(__read|__list|__grep|__glob|__search|\b(read|grep|glob|search|find|list|ls|cat|rg)\b)/.test(text)) return "read"
  if (/\b(workspace|pwd|tree|init|setup|prepare|cp|clone)\b/.test(text)) return "workspace"
  return "other"
}

function aggregateStatus(activities: AgentRuntimeToolActivity[]): AgentRuntimeToolActivityStatus {
  if (activities.some((activity) => activity.status === "failed")) return "failed"
  if (activities.some((activity) => activity.status === "cancelled")) return "cancelled"
  if (activities.some((activity) => activity.status === "rejected")) return "rejected"
  if (activities.some((activity) => activity.status === "waiting")) return "waiting"
  if (activities.some((activity) => activity.status === "running")) return "running"
  if (activities.some((activity) => activity.status === "requested")) return "requested"
  if (activities.some((activity) => activity.status === "building")) return "building"
  return "completed"
}

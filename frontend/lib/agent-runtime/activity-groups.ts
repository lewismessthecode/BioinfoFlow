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

  for (const activity of [...activities].sort(compareActivities)) {
    const kind = classifyActivity(activity)
    const previous = groups.at(-1)
    if (previous?.kind === kind) {
      previous.activities.push(activity)
      previous.status = aggregateStatus(previous.activities)
      previous.seqEnd = Math.max(previous.seqEnd, activity.seqEnd)
      continue
    }
    groups.push({
      id: `${kind}-${groups.length}-${activity.seqStart}`,
      kind,
      status: activity.status,
      activities: [activity],
      seqStart: activity.seqStart,
      seqEnd: activity.seqEnd,
    })
  }

  return groups
}

export function classifyActivity(
  activity: AgentRuntimeToolActivity,
): AgentRuntimeActivityGroupKind {
  const text = `${activity.name} ${activity.inputPreview ?? ""} ${JSON.stringify(activity.arguments ?? {})}`.toLowerCase()
  const name = activity.name.toLowerCase()

  if (/\b(workflows?__|workflows?\.)/.test(name) || /\bregister\b/.test(text)) return "register"
  if (/\b(runs?__submit|runs?\.submit|submit run|nextflow run|miniwdl run)\b/.test(text)) return "run"
  if (/\b(test|pytest|vitest|lint|ruff|doctor|verify|validate|check)\b/.test(text)) return "verify"
  if (/\b(write|edit|patch|create|mkdir|touch|rm|delete|move|rename|files__write|files__edit)\b/.test(text)) return "write"
  if (/(__read|__list|__grep|__glob|__search|\b(read|grep|glob|search|find|list|ls|cat|rg)\b)/.test(text)) return "read"
  if (/\b(workspace|pwd|tree|init|setup|prepare|cp|clone)\b/.test(text)) return "workspace"
  return "other"
}

function compareActivities(a: AgentRuntimeToolActivity, b: AgentRuntimeToolActivity) {
  return a.seqStart - b.seqStart || a.seqEnd - b.seqEnd || a.id.localeCompare(b.id)
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

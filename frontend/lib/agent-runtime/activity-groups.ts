import type {
  AgentRuntimeActivityGroupKind,
  AgentRuntimeToolActivity,
} from "./types"

export function classifyActivity(
  activity: AgentRuntimeToolActivity,
): AgentRuntimeActivityGroupKind {
  const text = `${activity.name} ${activity.inputPreview ?? ""} ${JSON.stringify(activity.arguments ?? {})}`.toLowerCase()
  const name = activity.name.toLowerCase()

  if (/\bregister\b/.test(text) || /\b(workflows?__|workflows?\.)/.test(name)) return "register"
  if (/\b(runs?__submit|runs?\.submit|submit run|nextflow run|miniwdl run)\b/.test(text)) return "run"
  if (/\b(test|pytest|vitest|lint|ruff|doctor|verify|validate|check)\b/.test(text)) return "verify"
  if (/\b(write|edit|patch|create|mkdir|touch|rm|delete|move|rename|files__write|files__edit)\b/.test(text)) return "write"
  if (/(__read|__list|__grep|__glob|__search|\b(read|grep|glob|search|find|list|ls|cat|rg)\b)/.test(text)) return "read"
  if (/\b(workspace|pwd|tree|init|setup|prepare|cp|clone)\b/.test(text)) return "workspace"
  return "other"
}

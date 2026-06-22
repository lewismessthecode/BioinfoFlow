import type {
  AgentRuntimeActivityGroupKind,
  AgentRuntimeToolActivity,
} from "./types"

export function classifyActivity(
  activity: AgentRuntimeToolActivity,
): AgentRuntimeActivityGroupKind {
  const name = normalizeToolName(activity.name)
  const preview = (activity.inputPreview ?? "").toLowerCase()
  const argumentHint = stringifyArguments(activity.arguments).toLowerCase()
  const fallbackText = `${preview} ${argumentHint}`.trim()

  if (activity.sources.length || isSearchTool(name) || isSearchCommand(fallbackText)) {
    return "search"
  }
  if (isRunTool(name)) return "run"
  if (isWorkflowMutationTool(name)) return "register"
  if (isFileMutationTool(name)) return "write"
  if (isVerificationTool(name)) return "verify"
  if (isReadTool(name)) return "read"
  if (isWorkspaceTool(name)) return "workspace"

  if (/\b(nextflow|miniwdl)\s+run\b/.test(fallbackText)) return "run"
  if (/\b(register|validate)\s+workflow\b/.test(fallbackText)) return "register"
  if (isFileMutationCommand(fallbackText)) return "write"
  if (isVerificationCommand(fallbackText)) return "verify"
  if (isReadCommand(fallbackText)) return "read"
  if (isWorkspaceCommand(fallbackText)) return "workspace"
  if (isCommandTool(name) || isCommandLike(fallbackText)) return "command"
  return "other"
}

function normalizeToolName(name: string) {
  return name.trim().toLowerCase().replaceAll(".", "__")
}

function terminalName(name: string) {
  return name.split("__").filter(Boolean).at(-1) ?? name
}

function isSearchTool(name: string) {
  return /(^|__)web__?search$/.test(name) || /\b(literature|pubmed|web)__?search\b/.test(name)
}

function isRunTool(name: string) {
  return /^(runs?__)?submit(_run)?$/.test(name) || name === "runs__submit"
}

function isWorkflowMutationTool(name: string) {
  const last = terminalName(name)
  return (
    (name.startsWith("workflows__") || name.includes("__workflows__")) &&
    ["register", "validate", "import", "create", "update", "delete", "bind", "unbind", "pin"].includes(last)
  )
}

function isFileMutationTool(name: string) {
  const last = terminalName(name)
  return (
    name.startsWith("files__") &&
    ["write", "edit", "patch", "create", "mkdir", "touch", "rm", "delete", "move", "rename"].includes(last)
  )
}

function isReadTool(name: string) {
  const last = terminalName(name)
  return (
    [
      "audit",
      "dag",
      "form_spec",
      "glob",
      "grep",
      "logs",
      "outputs",
      "rg",
      "search",
      "find",
      "ls",
      "cat",
      "read",
      "list",
      "get",
      "source",
      "status",
    ].includes(last) ||
    /__(read|list|get|source|grep|glob|search|find)$/.test(name)
  )
}

function isVerificationTool(name: string) {
  const last = terminalName(name)
  return ["test", "pytest", "vitest", "lint", "ruff", "doctor", "verify", "check"].includes(last)
}

function isWorkspaceTool(name: string) {
  const last = terminalName(name)
  return ["workspace", "pwd", "tree", "init", "setup", "prepare", "clone"].includes(last)
}

function isCommandTool(name: string) {
  const last = terminalName(name)
  return ["bash", "shell", "command", "terminal", "build", "inspect", "pull", "run"].includes(last)
}

function isSearchCommand(text: string) {
  return /\b(web[_.-]?search|searched web|literature search)\b/.test(text)
}

function isFileMutationCommand(text: string) {
  return /(?:^|[\s"'`:{,[;&|]\s*)(write|edit|patch|create|mkdir|touch|rm|delete|move|rename|mv)\b/.test(text)
}

function isReadCommand(text: string) {
  return /\b(read|grep|glob|search|find|list|ls|cat|rg)\b/.test(text)
}

function isVerificationCommand(text: string) {
  return /\b(test|pytest|vitest|lint|ruff|doctor|verify|validate|check)\b/.test(text)
}

function isWorkspaceCommand(text: string) {
  return /\b(workspace|pwd|tree|init|setup|prepare|cp|clone)\b/.test(text)
}

function isCommandLike(text: string) {
  return /\b(docker|bun|npm|pnpm|yarn|uv|python|python3|pip|alembic|git)\b/.test(text)
}

function stringifyArguments(argumentsValue: Record<string, unknown> | null | undefined) {
  if (!argumentsValue) return ""
  try {
    return JSON.stringify(argumentsValue)
  } catch {
    return ""
  }
}

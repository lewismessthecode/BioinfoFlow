import type {
  AgentRuntimeActivityGroupKind,
  AgentRuntimeToolActivity,
} from "./types"

export function classifyActivity(
  activity: AgentRuntimeToolActivity,
): AgentRuntimeActivityGroupKind {
  const name = normalizeToolName(activity.name)
  const preview = (activity.inputPreview ?? "").toLowerCase()

  if (isRunTool(name) || /\b(nextflow|miniwdl)\s+run\b/.test(preview)) return "run"
  if (isWorkflowMutationTool(name) || /\b(register|validate)\s+workflow\b/.test(preview)) {
    return "register"
  }
  if (isFileMutationTool(name) || isFileMutationCommand(preview)) return "write"
  if (isVerificationTool(name) || isVerificationCommand(preview)) return "verify"
  if (isReadTool(name) || isReadCommand(preview)) return "read"
  if (isWorkspaceTool(name)) return "workspace"
  if (isCommandTool(name) || isCommandLike(preview)) return "command"
  return "other"
}

function normalizeToolName(name: string) {
  return name.trim().toLowerCase().replaceAll(".", "__")
}

function terminalName(name: string) {
  return name.split("__").filter(Boolean).at(-1) ?? name
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

function isFileMutationCommand(preview: string) {
  return /(?:^|[;&|]\s*)(write|edit|patch|create|mkdir|touch|rm|delete|move|rename|mv)\b/.test(preview)
}

function isReadCommand(preview: string) {
  return /\b(read|grep|glob|search|find|list|ls|cat|rg)\b/.test(preview)
}

function isVerificationCommand(preview: string) {
  return /\b(test|pytest|vitest|lint|ruff|doctor|verify|validate|check)\b/.test(preview)
}

function isCommandLike(preview: string) {
  return /\b(docker|bun|npm|pnpm|yarn|uv|python|python3|pip|alembic|git)\b/.test(preview)
}

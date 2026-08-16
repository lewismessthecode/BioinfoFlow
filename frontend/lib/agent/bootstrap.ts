import { apiRequest } from "@/lib/api"

export type AgentExecutionScope = {
  mode: "auto" | "manual"
  targetIds: string[]
}

export type AgentExecutionTarget = {
  id: string
  handle: string
  alias: string
  kind: "local" | "remote_ssh"
  status: "online" | "offline" | "error" | "unknown"
  primary: boolean
  disabledReason: string | null
}

export type AgentStarterPrompt = {
  id: string
  title: string
  prompt: string
  icon: "check" | "explain" | "review" | "chat"
}

export type AgentUiCapabilities = {
  reasoning: boolean
  toolActivity: boolean
  approvals: boolean
  artifacts: boolean
  starterPrompts: boolean
  multiTargetExecution: boolean
  retry: boolean
  editAndResend: boolean
}

export type AgentUiBootstrap = {
  protocolVersion: 1
  capabilities: AgentUiCapabilities
  executionTargets: AgentExecutionTarget[]
  executionScope: AgentExecutionScope
  starterPrompts: AgentStarterPrompt[]
  composerHint: string | null
  degradedReason: "unsupported_version" | "invalid_payload" | null
}

export async function getAgentUiBootstrap(
  projectId: string | null,
  locale: string,
): Promise<AgentUiBootstrap> {
  const response = await apiRequest<unknown>("/agent/ui/bootstrap", {
    params: { project_id: projectId ?? undefined, locale },
  })
  return normalizeAgentUiBootstrap(response.data, locale)
}

export function normalizeAgentUiBootstrap(
  value: unknown,
  locale: string,
): AgentUiBootstrap {
  if (!isRecord(value) || value.protocol_version !== 1) {
    return fallbackBootstrap(
      locale,
      isRecord(value) && typeof value.protocol_version === "number"
        ? "unsupported_version"
        : "invalid_payload",
    )
  }

  const targets = Array.isArray(value.execution_targets)
    ? value.execution_targets.flatMap(normalizeTarget)
    : []
  const scope = normalizeScope(value.execution_scope, targets)
  const prompts = Array.isArray(value.starter_prompts)
    ? value.starter_prompts.flatMap(normalizeStarterPrompt).slice(0, 4)
    : []
  const fallback = fallbackBootstrap(locale, null)

  return {
    protocolVersion: 1,
    capabilities: normalizeCapabilities(value.capabilities),
    executionTargets: targets.length > 0 ? targets : fallback.executionTargets,
    executionScope: scope ?? fallback.executionScope,
    starterPrompts: prompts.length > 0 ? prompts : fallback.starterPrompts,
    composerHint:
      typeof value.composer_hint === "string" && value.composer_hint.trim()
        ? value.composer_hint.trim()
        : fallback.composerHint,
    degradedReason: null,
  }
}

function normalizeCapabilities(value: unknown): AgentUiCapabilities {
  const record = isRecord(value) ? value : {}
  return {
    reasoning: record.reasoning === true,
    toolActivity: record.tool_activity === true,
    approvals: record.approvals === true,
    artifacts: record.artifacts === true,
    starterPrompts: record.starter_prompts === true,
    multiTargetExecution: record.multi_target_execution === true,
    retry: record.retry === true,
    editAndResend: record.edit_and_resend === true,
  }
}

function normalizeTarget(value: unknown): AgentExecutionTarget[] {
  if (!isRecord(value)) return []
  if (
    !isText(value.id, 200) ||
    !isText(value.handle, 200) ||
    !isText(value.alias, 200) ||
    (value.kind !== "local" && value.kind !== "remote_ssh")
  ) {
    return []
  }
  const status = ["online", "offline", "error", "unknown"].includes(
    String(value.status),
  )
    ? (value.status as AgentExecutionTarget["status"])
    : "unknown"
  return [
    {
      id: value.id,
      handle: value.handle,
      alias: value.alias,
      kind: value.kind,
      status,
      primary: value.primary === true,
      disabledReason:
        typeof value.disabled_reason === "string" ? value.disabled_reason : null,
    },
  ]
}

function normalizeScope(
  value: unknown,
  targets: AgentExecutionTarget[],
): AgentExecutionScope | null {
  if (!isRecord(value) || (value.mode !== "auto" && value.mode !== "manual")) {
    return null
  }
  const known = new Set(targets.map((target) => target.id))
  const targetIds = Array.isArray(value.target_ids)
    ? [...new Set(value.target_ids.filter((id): id is string => typeof id === "string" && known.has(id)))]
    : []
  if (value.mode === "manual" && targetIds.length === 0) return null
  return { mode: value.mode, targetIds }
}

function normalizeStarterPrompt(value: unknown): AgentStarterPrompt[] {
  if (!isRecord(value)) return []
  if (
    !isText(value.id, 100) ||
    !isText(value.title, 120) ||
    !isText(value.prompt, 2000)
  ) {
    return []
  }
  const icon = ["check", "explain", "review", "chat"].includes(String(value.icon))
    ? (value.icon as AgentStarterPrompt["icon"])
    : "chat"
  return [{ id: value.id, title: value.title, prompt: value.prompt, icon }]
}

function fallbackBootstrap(
  locale: string,
  degradedReason: AgentUiBootstrap["degradedReason"],
): AgentUiBootstrap {
  const chinese = locale.toLowerCase().startsWith("zh")
  return {
    protocolVersion: 1,
    capabilities: {
      reasoning: true,
      toolActivity: true,
      approvals: true,
      artifacts: true,
      starterPrompts: true,
      multiTargetExecution: false,
      retry: true,
      editAndResend: true,
    },
    executionTargets: [
      {
        id: "local",
        handle: "local",
        alias: chinese ? "本地" : "Local",
        kind: "local",
        status: "online",
        primary: true,
        disabledReason: null,
      },
    ],
    executionScope: { mode: "auto", targetIds: [] },
    starterPrompts: chinese
      ? [
          { id: "inspect-workspace", title: "检查工作区", prompt: "检查当前工作区并概括项目、工作流和最近运行。", icon: "check" },
          { id: "plan-analysis", title: "规划一次分析", prompt: "帮我规划一次新的生物信息分析，并列出需要准备的内容。", icon: "explain" },
          { id: "review-failures", title: "检查失败运行", prompt: "检查最近失败的运行，解释原因并给出下一步建议。", icon: "review" },
        ]
      : [
          { id: "inspect-workspace", title: "Inspect the workspace", prompt: "Inspect this workspace and summarize its projects, workflows, and recent runs.", icon: "check" },
          { id: "plan-analysis", title: "Plan an analysis", prompt: "Help me plan a bioinformatics analysis and list what I need before starting.", icon: "explain" },
          { id: "review-failures", title: "Review failed runs", prompt: "Review recent failed runs, explain likely causes, and recommend next steps.", icon: "review" },
        ],
    composerHint: chinese
      ? "输入 / 选择技能，或添加文件、工作流和运行记录作为上下文"
      : "Type / to choose a skill, or add files, workflows, and runs as context",
    degradedReason,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function isText(value: unknown, maxLength: number): value is string {
  return typeof value === "string" && value.trim().length > 0 && value.length <= maxLength
}

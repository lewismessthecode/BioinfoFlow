import type {
  AgentLifecycleStatus,
  AgentRuntimeEvent,
  AgentTreeNode,
} from "./types"

const AGENT_STATUSES = new Set<AgentLifecycleStatus>([
  "pending_init",
  "running",
  "completed",
  "errored",
  "interrupted",
])

export function reduceAgentTree(events: AgentRuntimeEvent[]): AgentTreeNode[] {
  const agents = new Map<string, AgentTreeNode>()

  for (const event of [...events].sort((a, b) => a.seq - b.seq)) {
    if (event.type !== "agent.lifecycle") continue
    const childSessionId = stringValue(event.payload.child_session_id)
    if (!childSessionId) continue
    const previous = agents.get(childSessionId)
    if (previous && event.seq <= previous.sequence) continue

    const incomingTurnId = stringValue(event.payload.child_turn_id)
    const turnChanged = Boolean(
      previous?.childTurnId &&
        incomingTurnId &&
        previous.childTurnId !== incomingTurnId,
    )
    const incomingStatus = lifecycleStatus(event.payload.status)
    const previousStatus = turnChanged ? undefined : previous?.status
    const status =
      previousStatus && isTerminal(previousStatus)
        ? previousStatus
        : incomingStatus ?? previousStatus ?? "pending_init"
    const previousTurnFields = turnChanged ? undefined : previous
    agents.set(childSessionId, {
      childSessionId,
      childTurnId: incomingTurnId ?? previous?.childTurnId,
      taskPath:
        stringValue(event.payload.task_name) ?? previous?.taskPath ?? `/root/${childSessionId}`,
      status,
      sequence: event.seq,
      updatedAt: event.created_at ?? previous?.updatedAt,
      requestedModel: valueOrPrevious(
        event.payload.requested_model,
        previous?.requestedModel,
      ),
      effectiveModel: valueOrPrevious(
        event.payload.effective_model,
        previous?.effectiveModel,
      ),
      modelFallback:
        typeof event.payload.model_fallback === "boolean"
          ? event.payload.model_fallback
          : previous?.modelFallback,
      fallbackReason: valueOrPrevious(
        event.payload.fallback_reason,
        previous?.fallbackReason,
      ),
      finalText: valueOrPrevious(
        event.payload.final_text,
        previousTurnFields?.finalText,
      ),
      errorCode: valueOrPrevious(
        event.payload.error_code,
        previousTurnFields?.errorCode,
      ),
      errorMessage: valueOrPrevious(
        event.payload.error_message,
        previousTurnFields?.errorMessage,
      ),
      terminationReason: valueOrPrevious(
        event.payload.termination_reason,
        previousTurnFields?.terminationReason,
      ),
      tokenUsage:
        recordValue(event.payload.token_usage) ?? previousTurnFields?.tokenUsage,
    })
  }

  return [...agents.values()].sort(
    (a, b) => a.taskPath.localeCompare(b.taskPath) || a.childSessionId.localeCompare(b.childSessionId),
  )
}

export function summarizeAgentTree(agents: AgentTreeNode[]) {
  return agents.reduce(
    (summary, agent) => {
      summary.total += 1
      if (agent.status === "pending_init" || agent.status === "running") {
        summary.active += 1
      } else if (agent.status === "completed") {
        summary.completed += 1
      } else {
        summary.attention += 1
      }
      return summary
    },
    { total: 0, active: 0, completed: 0, attention: 0 },
  )
}

function isTerminal(status: AgentLifecycleStatus) {
  return status === "completed" || status === "errored" || status === "interrupted"
}

function lifecycleStatus(value: unknown): AgentLifecycleStatus | null {
  return typeof value === "string" && AGENT_STATUSES.has(value as AgentLifecycleStatus)
    ? (value as AgentLifecycleStatus)
    : null
}

function valueOrPrevious(
  value: unknown,
  previous: string | null | undefined,
): string | null | undefined {
  return typeof value === "string" && value.trim() ? value : previous
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value : null
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

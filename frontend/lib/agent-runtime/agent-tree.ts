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

    const status = lifecycleStatus(event.payload.status) ?? previous?.status ?? "pending_init"
    agents.set(childSessionId, {
      childSessionId,
      childTurnId: valueOrPrevious(event.payload.child_turn_id, previous?.childTurnId),
      taskPath:
        stringValue(event.payload.task_name) ?? previous?.taskPath ?? `/root/${childSessionId}`,
      status,
      sequence: event.seq,
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
      finalText: valueOrPrevious(event.payload.final_text, previous?.finalText),
      errorCode: valueOrPrevious(event.payload.error_code, previous?.errorCode),
      errorMessage: valueOrPrevious(
        event.payload.error_message,
        previous?.errorMessage,
      ),
      terminationReason: valueOrPrevious(
        event.payload.termination_reason,
        previous?.terminationReason,
      ),
    })
  }

  return [...agents.values()].sort(
    (a, b) => a.taskPath.localeCompare(b.taskPath) || a.childSessionId.localeCompare(b.childSessionId),
  )
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

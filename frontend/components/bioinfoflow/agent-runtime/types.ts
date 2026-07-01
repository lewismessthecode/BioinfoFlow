import type {
  AgentActionDecision,
  AgentAnswer,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"

export type AgentDecisionHandler = (
  actionId: string,
  decision: AgentActionDecision,
  options?: { answer?: AgentAnswer; note?: string },
) => void

export type AgentRetryHandler = (turn: AgentRuntimeTurn) => void

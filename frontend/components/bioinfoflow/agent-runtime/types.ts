import type { AgentActionDecision, AgentAnswer } from "@/lib/agent-runtime"

export type AgentDecisionHandler = (
  actionId: string,
  decision: AgentActionDecision,
  options?: { answer?: AgentAnswer; note?: string },
) => void

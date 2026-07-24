export type AgentTurnPolicy = "steer" | "queue"

export const DEFAULT_AGENT_TURN_POLICY: AgentTurnPolicy = "steer"
export const AGENT_TURN_POLICY_STORAGE_KEY = "bioinfoflow.agentRuntime.turnPolicy"

export function isAgentTurnPolicy(value: unknown): value is AgentTurnPolicy {
  return value === "steer" || value === "queue"
}

export function readAgentTurnPolicy(): AgentTurnPolicy {
  if (typeof window === "undefined") return DEFAULT_AGENT_TURN_POLICY
  const stored = window.localStorage.getItem(AGENT_TURN_POLICY_STORAGE_KEY)
  if (stored === "interrupt") {
    window.localStorage.setItem(AGENT_TURN_POLICY_STORAGE_KEY, "steer")
    return "steer"
  }
  return isAgentTurnPolicy(stored) ? stored : DEFAULT_AGENT_TURN_POLICY
}

export function writeAgentTurnPolicy(policy: AgentTurnPolicy) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(AGENT_TURN_POLICY_STORAGE_KEY, policy)
}

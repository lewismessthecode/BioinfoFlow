import { apiRequest } from "@/lib/api"

export const AGENT_CUSTOM_INSTRUCTIONS_MAX_LENGTH = 20_000

export type AgentSettings = {
  custom_instructions: string
}

export async function getAgentSettings(): Promise<AgentSettings> {
  const response = await apiRequest<AgentSettings>("/agent/settings")
  return response.data
}

export async function updateAgentSettings(
  customInstructions: string,
): Promise<AgentSettings> {
  const response = await apiRequest<AgentSettings>("/agent/settings", {
    method: "PUT",
    body: JSON.stringify({ custom_instructions: customInstructions }),
  })
  return response.data
}

import { apiRequest } from "@/lib/api"

export type AgentStarterPromptSource = "cache" | "fallback"

export type AgentStarterPrompts = {
  prompts: string[]
  source: AgentStarterPromptSource
  refresh_pending: boolean
}

export async function getAgentStarterPrompts(input: {
  projectId: string
  locale: string
  signal?: AbortSignal
}): Promise<AgentStarterPrompts> {
  const response = await apiRequest<AgentStarterPrompts>(
    "/agent/starter-prompts",
    {
      params: { project_id: input.projectId, locale: input.locale },
      signal: input.signal,
    },
  )
  return response.data
}

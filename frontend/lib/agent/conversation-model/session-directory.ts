import { listAgentSessions } from "../client"
import type { ConversationSummary } from "./types"

export type ConversationRouteSummary = Pick<
  ConversationSummary,
  "id" | "projectId" | "status"
>

export async function listConversationRouteSummaries(options?: {
  includeArchived?: boolean
}): Promise<ConversationRouteSummary[]> {
  const sessions = await listAgentSessions(options)
  return sessions.map(({ id, project_id, status }) => ({
    id,
    projectId: project_id,
    status,
  }))
}

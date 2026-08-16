import type { AgentSessionSummary } from "./client"
import type { ConversationSummary } from "./conversation-model/types"
import type { SessionView } from "./contracts"

const SESSION_SUMMARY_UPDATED_EVENT = "bioinfoflow:agent-session-summary-updated"

export type AgentSessionSummaryUpdate =
  | { kind: "snapshot"; summary: AgentSessionSummary }
  | { kind: "conversation"; summary: ConversationSummary }

function publishSessionSummaryUpdate(update: AgentSessionSummaryUpdate) {
  if (typeof window === "undefined") return
  window.dispatchEvent(
    new CustomEvent<AgentSessionSummaryUpdate>(SESSION_SUMMARY_UPDATED_EVENT, {
      detail: update,
    }),
  )
}

export function publishAgentSessionSummary(summary: AgentSessionSummary) {
  publishSessionSummaryUpdate({ kind: "snapshot", summary })
}

export function publishConversationSummary(summary: ConversationSummary) {
  publishSessionSummaryUpdate({ kind: "conversation", summary })
}

export function subscribeAgentSessionSummaries(
  listener: (update: AgentSessionSummaryUpdate) => void,
) {
  if (typeof window === "undefined") return () => {}

  const handleEvent = (event: Event) => {
    const update = (event as CustomEvent<AgentSessionSummaryUpdate>).detail
    if (update) listener(update)
  }

  window.addEventListener(SESSION_SUMMARY_UPDATED_EVENT, handleEvent)
  return () => window.removeEventListener(SESSION_SUMMARY_UPDATED_EVENT, handleEvent)
}

export function sortAgentSessionSummaries(sessions: AgentSessionSummary[]) {
  return [...sessions].sort(
    (left, right) =>
      new Date(right.updated_at || right.created_at).getTime() -
      new Date(left.updated_at || left.created_at).getTime(),
  )
}

export function sessionSummaryFromView(
  session: SessionView,
): AgentSessionSummary {
  return {
    id: session.id,
    project_id: session.project_id,
    title: session.title,
    permission_mode: session.permission_mode,
    workspace_access: session.workspace_access,
    status: session.status,
    created_at: session.created_at,
    updated_at: session.updated_at,
  }
}

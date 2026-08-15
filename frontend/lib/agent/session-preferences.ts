import type { AgentSessionSummary } from "./client"
import type { SessionView } from "./contracts"

const SESSION_SUMMARY_UPDATED_EVENT = "bioinfoflow:agent-session-summary-updated"

export function publishAgentSessionSummary(summary: AgentSessionSummary) {
  if (typeof window === "undefined") return
  window.dispatchEvent(
    new CustomEvent<AgentSessionSummary>(SESSION_SUMMARY_UPDATED_EVENT, {
      detail: summary,
    }),
  )
}

export function subscribeAgentSessionSummaries(
  listener: (summary: AgentSessionSummary) => void,
) {
  if (typeof window === "undefined") return () => {}

  const handleEvent = (event: Event) => {
    const summary = (event as CustomEvent<AgentSessionSummary>).detail
    if (summary) listener(summary)
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

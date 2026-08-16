import type { ConversationViewModel } from "@/lib/agent/conversation-model/types"
import type { AgentStoreState } from "@/lib/agent/store"

import { createConversationProjection } from "./conversation-projection"

export function projectLegacyConversationState(
  state: Pick<AgentStoreState, "session" | "runs" | "entries" | "activeRun">,
): ConversationViewModel | null {
  if (!state.session) return null
  const projection = createConversationProjection({
    session: state.session,
    runs: state.runs,
    entries: state.entries,
    active_run: state.activeRun,
  })
  return projection.ok ? projection.view : null
}

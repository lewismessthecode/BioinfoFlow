import type {
  ActiveRunView,
  AgentEvent,
  AssistantDeltaEvent,
  HistoryEntry,
  RunView,
  SessionSnapshot,
} from "./contracts"

export type AgentStoreState = {
  session: SessionSnapshot["session"] | null
  runs: RunView[]
  entries: HistoryEntry[]
  activeRun: ActiveRunView | null
  historyRevision: number
}

export type AgentEventApplication = {
  outcome: "applied" | "ignored" | "needs_snapshot"
  state: AgentStoreState
}

export const initialAgentStoreState: AgentStoreState = {
  session: null,
  runs: [],
  entries: [],
  activeRun: null,
  historyRevision: 0,
}

export function applyAgentEvent(
  state: AgentStoreState,
  event: AgentEvent,
): AgentEventApplication {
  switch (event.type) {
    case "snapshot":
      return applied(stateFromSnapshot(event.snapshot))
    case "run.updated":
      return applyRunUpdate(state, event.run)
    case "assistant.delta":
      return applyAssistantDelta(state, event)
    case "tool.updated":
      return applyToolUpdate(state, event)
    case "interaction.requested":
      return applyInteractionRequest(state, event)
    case "entry.committed":
      return applyCommittedEntry(state, event.entry)
  }
}

function stateFromSnapshot(snapshot: SessionSnapshot): AgentStoreState {
  return {
    session: snapshot.session,
    runs: snapshot.runs,
    entries: snapshot.entries,
    activeRun: snapshot.active_run,
    historyRevision: snapshot.history_revision,
  }
}

function applyRunUpdate(
  state: AgentStoreState,
  run: RunView,
): AgentEventApplication {
  const current = state.runs.find((item) => item.id === run.id)
  if (current && current.revision >= run.revision) return ignored(state)

  const runs = current
    ? state.runs.map((item) => (item.id === run.id ? run : item))
    : [...state.runs, run]
  const activeRun =
    state.activeRun?.run.id === run.id
      ? isTerminalRun(run)
        ? null
        : { ...state.activeRun, run }
      : !state.activeRun && !isTerminalRun(run)
        ? {
            run,
            assistant_draft: null,
            tool_progress: [],
            pending_interaction: null,
          }
        : state.activeRun

  return applied({ ...state, runs, activeRun })
}

function applyAssistantDelta(
  state: AgentStoreState,
  event: AssistantDeltaEvent,
): AgentEventApplication {
  const activeRun = state.activeRun
  const draft = activeRun?.assistant_draft
  if (!activeRun || activeRun.run.id !== event.run_id) {
    return needsSnapshot(state)
  }

  if (!draft) {
    if (event.start_offset !== 0 || event.end_offset < event.start_offset) {
      return needsSnapshot(state)
    }
    return applied({
      ...state,
      activeRun: {
        ...activeRun,
        assistant_draft: {
          id: event.draft_id,
          run_id: event.run_id,
          parts: [
            {
              id: event.part_id,
              type: event.part_type,
              text: event.delta,
              end_offset: event.end_offset,
            },
          ],
        },
      },
    })
  }

  if (draft.id !== event.draft_id) return needsSnapshot(state)

  const partIndex = draft.parts.findIndex((part) => part.id === event.part_id)
  const part = draft.parts[partIndex]
  if (!part) {
    if (event.start_offset !== 0 || event.end_offset < event.start_offset) {
      return needsSnapshot(state)
    }
    return applied({
      ...state,
      activeRun: {
        ...activeRun,
        assistant_draft: {
          ...draft,
          parts: [
            ...draft.parts,
            {
              id: event.part_id,
              type: event.part_type,
              text: event.delta,
              end_offset: event.end_offset,
            },
          ],
        },
      },
    })
  }
  if (part.type !== event.part_type) return needsSnapshot(state)
  if (event.end_offset < event.start_offset) return needsSnapshot(state)
  if (event.end_offset <= part.end_offset) return ignored(state)
  if (event.start_offset !== part.end_offset) {
    return needsSnapshot(state)
  }

  const parts = [...draft.parts]
  parts[partIndex] = {
    ...part,
    text: `${part.text}${event.delta}`,
    end_offset: event.end_offset,
  }

  return applied({
    ...state,
    activeRun: {
      ...activeRun,
      assistant_draft: { ...draft, parts },
    },
  })
}

function applyToolUpdate(
  state: AgentStoreState,
  event: Extract<AgentEvent, { type: "tool.updated" }>,
): AgentEventApplication {
  const activeRun = state.activeRun
  if (!activeRun || activeRun.run.id !== event.run_id) {
    return needsSnapshot(state)
  }

  const toolIndex = activeRun.tool_progress.findIndex(
    (tool) => tool.call_id === event.tool.call_id,
  )
  const current = activeRun.tool_progress[toolIndex]
  if (current && current.revision >= event.tool.revision) return ignored(state)

  const toolProgress = [...activeRun.tool_progress]
  if (toolIndex === -1) {
    toolProgress.push(event.tool)
  } else {
    toolProgress[toolIndex] = event.tool
  }

  return applied({
    ...state,
    activeRun: { ...activeRun, tool_progress: toolProgress },
  })
}

function applyInteractionRequest(
  state: AgentStoreState,
  event: Extract<AgentEvent, { type: "interaction.requested" }>,
): AgentEventApplication {
  const activeRun = state.activeRun
  if (
    !activeRun ||
    activeRun.run.id !== event.run_id ||
    event.interaction.run_id !== event.run_id
  ) {
    return needsSnapshot(state)
  }

  const current = activeRun.pending_interaction
  if (
    current?.interaction_id === event.interaction.interaction_id &&
    current.revision >= event.interaction.revision
  ) {
    return ignored(state)
  }

  return applied({
    ...state,
    activeRun: {
      ...activeRun,
      pending_interaction: event.interaction,
    },
  })
}

function applyCommittedEntry(
  state: AgentStoreState,
  entry: HistoryEntry,
): AgentEventApplication {
  if (state.entries.some((item) => item.id === entry.id)) return ignored(state)

  const entries = [...state.entries, entry].sort(
    (left, right) => left.sequence - right.sequence,
  )
  const activeRun = reconcileCommittedEntry(state.activeRun, entry)
  return applied({
    ...state,
    entries,
    activeRun,
    historyRevision: Math.max(state.historyRevision, entry.sequence),
  })
}

function reconcileCommittedEntry(
  activeRun: ActiveRunView | null,
  entry: HistoryEntry,
) {
  if (!activeRun || entry.run_id !== activeRun.run.id) return activeRun

  if (entry.type === "interaction_response") {
    const pending = activeRun.pending_interaction
    if (pending?.interaction_id !== entry.payload.interaction_id) return activeRun
    return { ...activeRun, pending_interaction: null }
  }

  if (entry.type !== "message") return activeRun

  const completedCallIds = new Set(
    entry.payload.parts.flatMap((part) =>
      part.type === "tool_result" ? [part.call_id] : [],
    ),
  )
  const assistantDraft =
    entry.payload.role === "assistant" ? null : activeRun.assistant_draft
  const toolProgress = completedCallIds.size
    ? activeRun.tool_progress.filter(
        (tool) => !completedCallIds.has(tool.call_id),
      )
    : activeRun.tool_progress

  if (
    assistantDraft === activeRun.assistant_draft &&
    toolProgress === activeRun.tool_progress
  ) {
    return activeRun
  }

  return {
    ...activeRun,
    assistant_draft: assistantDraft,
    tool_progress: toolProgress,
  }
}

function isTerminalRun(run: RunView) {
  return ["completed", "failed", "cancelled"].includes(run.status)
}

function applied(state: AgentStoreState): AgentEventApplication {
  return { outcome: "applied", state }
}

function ignored(state: AgentStoreState): AgentEventApplication {
  return { outcome: "ignored", state }
}

function needsSnapshot(state: AgentStoreState): AgentEventApplication {
  return { outcome: "needs_snapshot", state }
}

export type TraceJsonValue =
  | string
  | number
  | boolean
  | null
  | TraceJsonValue[]
  | { [key: string]: TraceJsonValue }

export type AgentTraceCategory =
  | "system"
  | "user"
  | "context"
  | "assistant"
  | "tool"
  | "unknown"

export type AgentTracePhase =
  | "pre_call"
  | "user_input"
  | "agent_work"
  | "final_response"

export type AgentTraceModel = {
  provider: string
  model: string
  displayName: string
}

export type AgentTraceEvent = {
  id: string
  turnId: string | null
  category: AgentTraceCategory
  title: string
  summary: string
  firstLine: string
  status: string | null
  sequence: number
  hasDetail: boolean
  createdAt: string
  phase: AgentTracePhase
}

export type AgentTraceTurn = {
  id: string
  runId: string
  index: number
  status: string
  model: AgentTraceModel | null
  events: AgentTraceEvent[]
}

export type AgentTraceContextComposition = {
  category: AgentTraceCategory
  characters: number
  tokens: number | null
}

export type AgentTraceContextSnapshot = {
  id: string
  turnId: string
  modelTraceId: string
  sequence: number
  throughSequence: number
  compacted: boolean
  inputTokens: number | null
  outputTokens: number | null
  cachedInputTokens: number | null
  reasoningTokens: number | null
  totalTokens: number | null
  maxContextTokens: number | null
  composition: AgentTraceContextComposition[]
}

export type AgentTraceViewModel = {
  protocolVersion: number
  session: {
    id: string
    title: string | null
    status: string
    model: AgentTraceModel
  }
  preambleEvents: AgentTraceEvent[]
  turns: AgentTraceTurn[]
  contextFlow: AgentTraceContextSnapshot[]
  eventCount: number
}

export type AgentTraceTiming = {
  startedAt: string | null
  requestPreparedAt: string | null
  firstByteAt: string | null
  completedAt: string | null
  durationMs: number | null
}

export type AgentTraceEventDetail = {
  protocolVersion: number
  eventId: string
  summary: { [key: string]: TraceJsonValue }
  payload: TraceJsonValue
  result: TraceJsonValue
  schema: TraceJsonValue
  timing: AgentTraceTiming | null
}

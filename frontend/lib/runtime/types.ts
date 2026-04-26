import type {
  AgentEventData,
  ApiMeta,
  EventEnvelope,
  ImageProgressEvent,
  RunDagEvent,
  RunLogEvent,
  RunStatusEvent,
} from "@/lib/types"

export type RuntimeMode = "live" | "demo"

export type RuntimeCapabilities = {
  auth: boolean
  terminal: boolean
  destructiveActions: boolean
}

export type RuntimeContextDefaults = {
  selectedProjectId?: string
}

export type RequestParams = Record<
  string,
  string | number | boolean | null | undefined
>

export type RuntimeRequestOptions = RequestInit & {
  params?: RequestParams
}

export type RuntimeRequestResult<T> = {
  data: T
  meta?: ApiMeta
}

export type RuntimeEventSubscription = {
  projectId?: string | null
  conversationId?: string | null
  runId?: string | null
  imageId?: string | null
  onRunStatus?: (event: EventEnvelope<RunStatusEvent>) => void
  onRunLog?: (event: EventEnvelope<RunLogEvent>) => void
  onRunDag?: (event: EventEnvelope<RunDagEvent>) => void
  onImageProgress?: (event: EventEnvelope<ImageProgressEvent>) => void
  onAgentEvent?: (event: EventEnvelope<AgentEventData>) => void
  onOpen?: () => void
  onError?: (event: Event) => void
}

export interface AppRuntime {
  mode: RuntimeMode
  capabilities: RuntimeCapabilities
  contextDefaults?: RuntimeContextDefaults
  request<T>(path: string, options?: RuntimeRequestOptions): Promise<RuntimeRequestResult<T>>
  buildApiUrl(path: string, params?: RequestParams): string
  buildWebSocketUrl(path: string, params?: RequestParams): string
  subscribe(options: RuntimeEventSubscription): () => void
}

import type { AgentExecutionScope, AgentExecutionTarget } from "./types"

export type ResolvedAgentExecutionTarget =
  | { kind: "local"; source: "normalized" | "legacy" | "default" }
  | {
      kind: "remote_ssh"
      remoteConnectionId: string
      source: "normalized" | "legacy"
    }

type SessionExecutionTargetSource = {
  execution_target?: AgentExecutionTarget | null
  execution_scope?: AgentExecutionScope | null
  metadata?: Record<string, unknown> | null
}

export function resolveAgentExecutionTarget(
  session?: SessionExecutionTargetSource | null,
): ResolvedAgentExecutionTarget {
  const normalized = normalizedExecutionTarget(session?.execution_target)
  if (normalized) return normalized

  const legacyRemoteConnectionId = metadataString(
    session?.metadata,
    "remote_connection_id",
  )
  if (legacyRemoteConnectionId) {
    return {
      kind: "remote_ssh",
      remoteConnectionId: legacyRemoteConnectionId,
      source: "legacy",
    }
  }

  return { kind: "local", source: "default" }
}

export function agentExecutionTargetForRequest(
  target: AgentExecutionTarget | null | undefined,
): AgentExecutionTarget | undefined {
  if (!target) return undefined
  const kind = target.kind ?? target.type
  if (kind === "local") return { ...target, kind: "local", type: "local" }
  if (kind !== "remote_ssh") return undefined

  const remoteConnectionId =
    stringValue(target.remote_connection_id) ?? stringValue(target.connection_id)
  if (!remoteConnectionId) return undefined

  return {
    ...target,
    kind: "remote_ssh",
    type: "remote_ssh",
    remote_connection_id: remoteConnectionId,
    connection_id: remoteConnectionId,
  }
}

export function agentExecutionScopeForRequest(
  scope: AgentExecutionScope | null | undefined,
): AgentExecutionScope | undefined {
  if (!scope) return undefined
  if (scope.mode === "auto") return { mode: "auto" }
  if (scope.mode !== "manual") return undefined

  const selectedTargets = (scope.selected_targets ?? [])
    .map((target) => agentExecutionTargetForRequest(target))
    .filter((target): target is AgentExecutionTarget => Boolean(target))

  return {
    mode: "manual",
    selected_targets: selectedTargets,
  }
}

function normalizedExecutionTarget(
  target: AgentExecutionTarget | null | undefined,
): ResolvedAgentExecutionTarget | null {
  if (!target) return null
  const kind = target.kind ?? target.type
  if (kind === "local") return { kind: "local", source: "normalized" }
  if (kind !== "remote_ssh") return null

  const remoteConnectionId =
    stringValue(target.remote_connection_id) ?? stringValue(target.connection_id)
  if (!remoteConnectionId) return null
  return {
    kind: "remote_ssh",
    remoteConnectionId,
    source: "normalized",
  }
}

function metadataString(
  metadata: Record<string, unknown> | null | undefined,
  key: string,
) {
  return stringValue(metadata?.[key])
}

function stringValue(value: unknown) {
  return typeof value === "string" && value ? value : null
}

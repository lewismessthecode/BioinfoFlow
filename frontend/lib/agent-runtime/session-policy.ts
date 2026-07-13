import type { AgentRuntimeSession } from "./types"

export function mergeSessionByPolicyVersion(
  existing: AgentRuntimeSession,
  incoming: AgentRuntimeSession,
) {
  if (existing.id !== incoming.id) return incoming
  if (sessionPolicyVersion(incoming) >= sessionPolicyVersion(existing)) return incoming
  return {
    ...incoming,
    role_profile: existing.role_profile,
    permission_mode: existing.permission_mode,
    automation_mode: existing.automation_mode,
    permission_policy_version: existing.permission_policy_version,
    toolset_policy: existing.toolset_policy,
    execution_target: existing.execution_target,
    metadata: existing.metadata,
    pending_strategy: existing.pending_strategy,
    pending_reconciliation: existing.pending_reconciliation,
  }
}

export function sessionPolicyVersion(
  session?: Pick<AgentRuntimeSession, "permission_policy_version">,
) {
  return session?.permission_policy_version ?? 0
}

export function restorePermissionPolicy(
  current: AgentRuntimeSession,
  snapshot: AgentRuntimeSession,
) {
  if (current.id !== snapshot.id) return current
  if (sessionPolicyVersion(current) > sessionPolicyVersion(snapshot)) return current
  return {
    ...current,
    permission_mode: snapshot.permission_mode,
    permission_policy_version: snapshot.permission_policy_version,
    pending_strategy: snapshot.pending_strategy,
    pending_reconciliation: snapshot.pending_reconciliation,
  }
}

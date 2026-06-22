import type {
  AgentRuntimeEvent,
  AgentRuntimeToolActivity,
  AgentRuntimeToolActivityStatus,
} from "./types"
import {
  mergeSources,
  resultError,
  sourceQueryFromAction,
  sourceResultCount,
  sourcesFromActionResult,
} from "./sources"

export function buildAgentRuntimeToolActivities(
  events: AgentRuntimeEvent[],
): AgentRuntimeToolActivity[] {
  const activities = new Map<string, AgentRuntimeToolActivity>()
  const keyByCallId = new Map<string, string>()
  const keyByActionId = new Map<string, string>()

  for (const event of events) {
    if (event.type.startsWith("assistant.tool_call.")) {
      const callId = stringValue(event.payload.call_id)
      if (!callId) continue
      const key = keyByCallId.get(callId) ?? `call:${callId}`
      keyByCallId.set(callId, key)
      const activity = ensureActivity(activities, key, event, {
        id: key,
        callId,
        actionId: null,
        name: stringValue(event.payload.name) || "tool",
        status: toolCallStatus(event),
        arguments: recordValue(event.payload.arguments),
        sources: [],
        relatedFiles: [],
        seqStart: event.seq,
        seqEnd: event.seq,
      })
      activity.callId = callId
      activity.name = stringValue(event.payload.name) || activity.name
      activity.status = toolCallStatus(event)
      activity.arguments = recordValue(event.payload.arguments) ?? activity.arguments
      activity.relatedFiles = uniqueStrings([
        ...activity.relatedFiles,
        ...relatedFilesFromRecord(activity.arguments),
      ])
      continue
    }

    if (event.type.startsWith("action.")) {
      const actionId = stringValue(event.payload.action_id)
      if (!actionId) continue
      const toolCallId = stringValue(event.payload.tool_call_id)
      const currentActionKey = keyByActionId.get(actionId) ?? null
      const callKey = toolCallId
        ? keyByCallId.get(toolCallId) ?? `call:${toolCallId}`
        : null
      const key = callKey ?? currentActionKey ?? `action:${actionId}`
      if (currentActionKey && currentActionKey !== key) {
        mergeActivities(activities, currentActionKey, key)
      }
      keyByActionId.set(actionId, key)
      if (toolCallId) keyByCallId.set(toolCallId, key)

      const result = recordValue(event.payload.result)
      const error = recordValue(event.payload.error)
      const sources = sourcesFromActionResult(result, event)
      const resultErrorMessage = resultError(result)
      const resultCount = sourceResultCount(result)
      const activity = ensureActivity(activities, key, event, {
        id: key,
        callId: toolCallId,
        actionId,
        name: stringValue(event.payload.name) || stringValue(event.payload.kind) || "action",
        status: resultErrorMessage ? "failed" : actionStatus(event),
        inputPreview: stringValue(event.payload.input_preview),
        outputPreview: outputPreview(result),
        exitCode: numberValue(result?.exit_code),
        durationMs: numberValue(event.payload.duration_ms),
        errorMessage:
          errorMessage(error) ?? stringValue(event.payload.error_message) ?? resultErrorMessage,
        sources,
        sourceQuery: sourceQueryFromAction(result, event.payload),
        sourceResultCount: resultCount,
        relatedFiles: [],
        seqStart: event.seq,
        seqEnd: event.seq,
      })
      activity.actionId = actionId
      activity.callId = toolCallId || activity.callId
      activity.name = stringValue(event.payload.name) || activity.name
      activity.status = resultErrorMessage ? "failed" : actionStatus(event)
      activity.inputPreview = stringValue(event.payload.input_preview) ?? activity.inputPreview
      activity.outputPreview = outputPreview(result) ?? activity.outputPreview
      activity.exitCode = numberValue(result?.exit_code) ?? activity.exitCode
      activity.durationMs = numberValue(event.payload.duration_ms) ?? activity.durationMs
      activity.errorMessage =
        errorMessage(error) ??
        stringValue(event.payload.error_message) ??
        resultErrorMessage ??
        activity.errorMessage
      activity.summary = stringValue(event.payload.summary) ?? activity.summary
      activity.sources = mergeSources(activity.sources, sources)
      activity.sourceQuery = sourceQueryFromAction(result, event.payload) ?? activity.sourceQuery
      activity.sourceResultCount =
        resultCount ?? activity.sourceResultCount ?? null
      activity.relatedFiles = uniqueStrings([
        ...activity.relatedFiles,
        ...relatedFilesFromRecord(recordValue(event.payload.input)),
        ...relatedFilesFromRecord(result),
      ])
      continue
    }

    if (event.type === "artifact.created") {
      const artifactId = stringValue(event.payload.artifact_id)
      const actionId = stringValue(event.payload.action_id)
      const key = actionId ? keyByActionId.get(actionId) ?? `action:${actionId}` : `artifact:${artifactId || event.id}`
      if (actionId) keyByActionId.set(actionId, key)
      const activity = ensureActivity(activities, key, event, {
        id: key,
        callId: null,
        actionId,
        name: stringValue(event.payload.title) || stringValue(event.payload.type) || "artifact",
        status: "completed",
        sources: [],
        relatedFiles: [],
        seqStart: event.seq,
        seqEnd: event.seq,
      })
      activity.actionId = actionId || activity.actionId
      activity.artifactId = artifactId ?? activity.artifactId
      activity.artifactType = stringValue(event.payload.type) ?? activity.artifactType
      activity.summary = stringValue(event.payload.title) ?? activity.summary
      activity.relatedFiles = uniqueStrings([
        ...activity.relatedFiles,
        ...relatedFilesFromRecord(event.payload),
      ])
    }
  }

  return [...activities.values()]
    .filter((activity) => activity.name.trim())
    .sort((a, b) => a.seqStart - b.seqStart || a.seqEnd - b.seqEnd || a.id.localeCompare(b.id))
}

function ensureActivity(
  activities: Map<string, AgentRuntimeToolActivity>,
  key: string,
  event: AgentRuntimeEvent,
  initial: AgentRuntimeToolActivity,
) {
  const existing = activities.get(key)
  if (existing) {
    existing.seqStart = Math.min(existing.seqStart, event.seq)
    existing.seqEnd = Math.max(existing.seqEnd, event.seq)
    return existing
  }
  activities.set(key, initial)
  return initial
}

function mergeActivities(
  activities: Map<string, AgentRuntimeToolActivity>,
  fromKey: string,
  toKey: string,
) {
  const from = activities.get(fromKey)
  if (!from) return
  const to = activities.get(toKey) ?? { ...from, id: toKey }
  to.callId = to.callId ?? from.callId
  to.actionId = to.actionId ?? from.actionId
  to.name = to.name === "action" || to.name === "tool" ? from.name : to.name
  to.arguments = to.arguments ?? from.arguments
  to.inputPreview = to.inputPreview ?? from.inputPreview
  to.outputPreview = to.outputPreview ?? from.outputPreview
  to.exitCode = to.exitCode ?? from.exitCode
  to.durationMs = to.durationMs ?? from.durationMs
  to.errorMessage = to.errorMessage ?? from.errorMessage
  to.summary = to.summary ?? from.summary
  to.sources = mergeSources(to.sources, from.sources)
  to.sourceQuery = to.sourceQuery ?? from.sourceQuery
  to.sourceResultCount = to.sourceResultCount ?? from.sourceResultCount
  to.artifactId = to.artifactId ?? from.artifactId
  to.artifactType = to.artifactType ?? from.artifactType
  to.relatedFiles = uniqueStrings([...to.relatedFiles, ...from.relatedFiles])
  to.seqStart = Math.min(to.seqStart, from.seqStart)
  to.seqEnd = Math.max(to.seqEnd, from.seqEnd)
  activities.set(toKey, to)
  activities.delete(fromKey)
}

function toolCallStatus(event: AgentRuntimeEvent): AgentRuntimeToolActivityStatus {
  if (event.type === "assistant.tool_call.completed") return "completed"
  return stringValue(event.payload.status) === "completed" ? "completed" : "building"
}

function actionStatus(event: AgentRuntimeEvent): AgentRuntimeToolActivityStatus {
  switch (event.type) {
    case "action.requested":
    case "action.risk_assessed":
      return "requested"
    case "action.waiting_decision":
      return "waiting"
    case "action.started":
      return "running"
    case "action.completed":
      return "completed"
    case "action.decision_recorded":
      return stringValue(event.payload.decision) === "reject" ? "rejected" : "completed"
    case "action.failed":
      return "failed"
    case "action.cancelled":
      return "cancelled"
    default:
      return "requested"
  }
}

function outputPreview(result: Record<string, unknown> | null | undefined) {
  if (!result) return null
  const stdout = stringValue(result.stdout)
  const stderr = stringValue(result.stderr)
  const output = stringValue(result.output)
  return truncate(stdout || stderr || output || "", 500)
}

function errorMessage(error: Record<string, unknown> | null | undefined) {
  if (!error) return null
  return stringValue(error.message) ?? stringValue(error.type)
}

function relatedFilesFromRecord(record: Record<string, unknown> | null | undefined) {
  if (!record) return []
  const files: string[] = []
  for (const key of ["path", "file_path", "filename", "cwd", "target", "source"]) {
    const value = record[key]
    if (typeof value === "string" && looksPathLike(value)) files.push(value)
  }
  return files
}

function looksPathLike(value: string) {
  return value.includes("/") || value.startsWith(".") || /\.[A-Za-z0-9]{1,8}$/.test(value)
}

function uniqueStrings(values: Array<string | null | undefined>) {
  return [...new Set(values.filter((value): value is string => Boolean(value)))]
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value : null
}

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function truncate(value: string, maxLength: number) {
  if (value.length <= maxLength) return value || null
  return `${value.slice(0, maxLength - 1)}…`
}

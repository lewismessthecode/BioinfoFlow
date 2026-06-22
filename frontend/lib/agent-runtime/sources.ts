import type { AgentRuntimeEvent, AgentRuntimeSource } from "./types"

export function sourcesFromActionResult(
  result: Record<string, unknown> | null | undefined,
  event: AgentRuntimeEvent,
  citationOffset = 0,
): AgentRuntimeSource[] {
  if (!result) return []
  const results = Array.isArray(result.results) ? result.results : []
  const searchSources = results.flatMap((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return []
    const record = item as Record<string, unknown>
    const url = stringValue(record.url)
    if (!url) return []
    const citationNumber = citationOffset + index + 1
    const citationId = stringValue(record.citationId) ?? String(citationNumber)
    const id = stringValue(record.id) ?? `source-${event.id}-${index + 1}`
    return [
      {
        id,
        title: stringValue(record.title) ?? url,
        url,
        domain: domainFromUrl(url),
        snippet: stringValue(record.snippet),
        sourceType: sourceTypeFromUrl(url),
        query: sourceQueryFromAction(result, event.payload),
        toolRunId: stringValue(event.payload.action_id),
        citationId,
        citationAliases: uniqueStrings([id, citationId]),
        accessedAt: event.created_at,
        resultCount: results.length,
      },
    ]
  })

  const fetchedUrl = stringValue(result.url)
  if (!searchSources.length && fetchedUrl) {
    const id = `source-${event.id}-fetch`
    return [
      {
        id,
        title: fetchedUrl,
        url: fetchedUrl,
        domain: domainFromUrl(fetchedUrl),
        snippet: truncate(stringValue(result.content) ?? "", 240),
        sourceType: sourceTypeFromUrl(fetchedUrl),
        query: sourceQueryFromAction(result, event.payload),
        toolRunId: stringValue(event.payload.action_id),
        citationId: String(citationOffset + 1),
        citationAliases: uniqueStrings([id, String(citationOffset + 1)]),
        accessedAt: event.created_at,
        resultCount: 1,
      },
    ]
  }

  return searchSources
}

export function parseSourcePayloads(
  value: unknown,
  event: AgentRuntimeEvent,
  citationOffset = 0,
): AgentRuntimeSource[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return []
    const record = item as Record<string, unknown>
    const url = stringValue(record.url)
    if (!url) return []
    const title = stringValue(record.title) ?? url
    const id =
      stringValue(record.id) ??
      stringValue(record.citationId) ??
      `source-${event.id}-${index + 1}`
    const citationId =
      stringValue(record.citationId) ??
      stringValue(record.citation_id) ??
      String(citationOffset + index + 1)
    return [
      {
        id,
        title,
        url,
        domain: stringValue(record.domain) ?? domainFromUrl(url),
        snippet: stringValue(record.snippet),
        sourceType: stringValue(record.sourceType) ?? stringValue(record.source_type) ?? "web",
        query: stringValue(record.query),
        toolRunId:
          stringValue(record.toolRunId) ??
          stringValue(record.tool_run_id) ??
          stringValue(event.payload.call_id) ??
          stringValue(event.payload.action_id),
        citationId,
        citationAliases: uniqueStrings([id, citationId]),
        accessedAt: stringValue(record.accessedAt) ?? stringValue(record.accessed_at),
        resultCount: numberValue(record.resultCount) ?? numberValue(record.result_count),
      },
    ]
  })
}

export function mergeSources(
  existing: AgentRuntimeSource[],
  next: AgentRuntimeSource[],
): AgentRuntimeSource[] {
  if (!next.length) return existing
  const merged = new Map(existing.map((source) => [sourceKey(source), source]))
  for (const source of next) {
    const key = sourceKey(source)
    const current = merged.get(key)
    merged.set(key, current ? mergeSource(current, source) : source)
  }
  return [...merged.values()]
}

export function sourceResultCount(result: Record<string, unknown> | null | undefined) {
  if (!result || !Array.isArray(result.results)) return null
  return result.results.length
}

export function resultError(result: Record<string, unknown> | null | undefined) {
  return stringValue(result?.error)
}

export function sourceQueryFromAction(
  result: Record<string, unknown> | null | undefined,
  payload: Record<string, unknown>,
) {
  return (
    stringValue(result?.query) ??
    stringValue(recordValue(payload.input)?.query) ??
    stringValue(recordValue(payload.arguments)?.query) ??
    stringValue(payload.input_preview)
  )
}

export function sanitizeSourceHref(url: string | null | undefined) {
  if (!url) return undefined
  try {
    const parsed = new URL(url)
    return ["http:", "https:"].includes(parsed.protocol) ? url : undefined
  } catch {
    return undefined
  }
}

function mergeSource(
  existing: AgentRuntimeSource,
  next: AgentRuntimeSource,
): AgentRuntimeSource {
  return {
    ...existing,
    ...next,
    title: next.title || existing.title,
    snippet: next.snippet ?? existing.snippet,
    query: next.query ?? existing.query,
    toolRunId: next.toolRunId ?? existing.toolRunId,
    citationId: existing.citationId ?? next.citationId,
    citationAliases: uniqueStrings([
      existing.id,
      existing.citationId,
      ...(existing.citationAliases ?? []),
      next.id,
      next.citationId,
      ...(next.citationAliases ?? []),
    ]),
    accessedAt: next.accessedAt ?? existing.accessedAt,
    resultCount: next.resultCount ?? existing.resultCount,
  }
}

function sourceKey(source: AgentRuntimeSource) {
  return canonicalUrl(source.url) || source.citationId || source.id
}

function canonicalUrl(url: string) {
  try {
    const parsed = new URL(url)
    parsed.hash = ""
    return parsed.toString().replace(/\/$/, "")
  } catch {
    return url.trim().toLowerCase()
  }
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

function uniqueStrings(values: Array<string | null | undefined>) {
  return [...new Set(values.filter((value): value is string => Boolean(value)))]
}

function truncate(value: string, maxLength: number) {
  if (value.length <= maxLength) return value || null
  return `${value.slice(0, maxLength - 1)}…`
}

function domainFromUrl(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}

function sourceTypeFromUrl(url: string) {
  const host = hostnameFromUrl(url)
  if (host === "pubmed.ncbi.nlm.nih.gov") return "pubmed"
  if (hostMatches(host, "ncbi.nlm.nih.gov")) return "ncbi"
  if (hostMatches(host, "biorxiv.org")) return "biorxiv"
  if (hostMatches(host, "github.com") || hostMatches(host, "githubusercontent.com")) {
    return "github"
  }
  return "web"
}

function hostnameFromUrl(url: string) {
  try {
    return new URL(url).hostname.toLowerCase().replace(/\.$/, "").replace(/^www\./, "")
  } catch {
    return ""
  }
}

function hostMatches(host: string, baseHost: string) {
  return host === baseHost || host.endsWith(`.${baseHost}`)
}

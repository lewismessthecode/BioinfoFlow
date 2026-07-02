import type { AgentTokenUsageSummary } from "./types"

export type AgentTokenUsageStatus = "normal" | "warning" | "critical"

export type AgentTokenUsageView = {
  totalLabel: string
  inputLabel: string
  outputLabel: string
  cachedInputLabel: string | null
  reasoningLabel: string | null
  contextWindowLabel: string | null
  maxOutputLabel: string | null
  percentUsed: number | null
  percentRemaining: number | null
  status: AgentTokenUsageStatus
}

export function tokenUsageViewFromSummary(
  summary?: AgentTokenUsageSummary | null,
): AgentTokenUsageView | null {
  if (!summary?.has_token_usage || summary.total_tokens <= 0) return null
  const percentUsed = usagePercent(summary.total_tokens, summary.context_window)
  return {
    totalLabel: compactTokenCount(summary.total_tokens),
    inputLabel: compactTokenCount(summary.input_tokens),
    outputLabel: compactTokenCount(summary.output_tokens),
    cachedInputLabel:
      summary.cached_input_tokens == null
        ? null
        : compactTokenCount(summary.cached_input_tokens),
    reasoningLabel:
      summary.reasoning_tokens == null
        ? null
        : compactTokenCount(summary.reasoning_tokens),
    contextWindowLabel:
      summary.context_window == null ? null : compactTokenCount(summary.context_window),
    maxOutputLabel:
      summary.max_output_tokens == null
        ? null
        : compactTokenCount(summary.max_output_tokens),
    percentUsed,
    percentRemaining: percentUsed == null ? null : Math.max(100 - percentUsed, 0),
    status: tokenUsageStatus(percentUsed),
  }
}

export function compactTokenCount(value: number): string {
  const absolute = Math.abs(value)
  if (absolute >= 1_000_000) return `${trimCompact(value / 1_000_000)}M`
  if (absolute >= 1_000) return `${trimCompact(value / 1_000)}K`
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value)
}

export function tokenUsageStatus(percentUsed?: number | null): AgentTokenUsageStatus {
  if (percentUsed == null) return "normal"
  if (percentUsed >= 90) return "critical"
  if (percentUsed >= 70) return "warning"
  return "normal"
}

function usagePercent(totalTokens: number, contextWindow?: number | null) {
  if (!contextWindow || contextWindow <= 0) return null
  return Math.min(Math.round((totalTokens / contextWindow) * 100), 100)
}

function trimCompact(value: number): string {
  const rounded = Math.round(value * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}

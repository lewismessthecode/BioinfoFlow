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
  locale?: string,
): AgentTokenUsageView | null {
  if (!summary?.has_token_usage || summary.total_tokens <= 0) return null
  const percentUsed = usagePercent(summary.total_tokens, summary.context_window)
  return {
    totalLabel: compactTokenCount(summary.total_tokens, locale),
    inputLabel: compactTokenCount(summary.input_tokens, locale),
    outputLabel: compactTokenCount(summary.output_tokens, locale),
    cachedInputLabel:
      summary.cached_input_tokens == null
        ? null
        : compactTokenCount(summary.cached_input_tokens, locale),
    reasoningLabel:
      summary.reasoning_tokens == null
        ? null
        : compactTokenCount(summary.reasoning_tokens, locale),
    contextWindowLabel:
      summary.context_window == null
        ? null
        : compactTokenCount(summary.context_window, locale),
    maxOutputLabel:
      summary.max_output_tokens == null
        ? null
        : compactTokenCount(summary.max_output_tokens, locale),
    percentUsed,
    percentRemaining: percentUsed == null ? null : Math.max(100 - percentUsed, 0),
    status: tokenUsageStatus(percentUsed),
  }
}

export function compactTokenCount(value: number, locale?: string): string {
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 1,
    notation: "compact",
  }).format(value)
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

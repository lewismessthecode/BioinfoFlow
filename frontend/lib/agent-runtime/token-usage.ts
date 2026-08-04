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
  currentContextInputLabel: string | null
  currentContextOutputLabel: string | null
  currentContextTotalLabel: string | null
  currentContextSource: "reported" | "estimated" | "unknown" | null
  providerLabel: string | null
  modelLabel: string | null
}

export function tokenUsageViewFromSummary(
  summary?: AgentTokenUsageSummary | null,
  locale?: string,
): AgentTokenUsageView | null {
  if (!summary?.has_token_usage) return null
  const currentContext = summary.current_context
  const percentUsed = usagePercent(
    currentContext?.input_tokens,
    currentContext?.context_window,
  )
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
      (currentContext?.context_window ?? summary.context_window) == null
        ? null
        : compactTokenCount(
            currentContext?.context_window ?? summary.context_window!,
            locale,
          ),
    maxOutputLabel:
      summary.max_output_tokens == null
        ? null
        : compactTokenCount(summary.max_output_tokens, locale),
    percentUsed,
    percentRemaining: percentUsed == null ? null : Math.max(100 - percentUsed, 0),
    status: tokenUsageStatus(percentUsed),
    currentContextInputLabel:
      currentContext == null
        ? null
        : compactTokenCount(currentContext.input_tokens, locale),
    currentContextOutputLabel:
      currentContext == null
        ? null
        : compactTokenCount(currentContext.output_tokens, locale),
    currentContextTotalLabel:
      currentContext == null
        ? null
        : compactTokenCount(currentContext.total_tokens, locale),
    currentContextSource: currentContext?.source ?? null,
    providerLabel: currentContext?.provider ?? null,
    modelLabel: currentContext?.model ?? null,
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

function usagePercent(inputTokens?: number, contextWindow?: number | null) {
  if (inputTokens == null || !contextWindow || contextWindow <= 0) return null
  return Math.min(Math.round((inputTokens / contextWindow) * 100), 100)
}

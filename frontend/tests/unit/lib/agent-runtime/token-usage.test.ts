import { describe, expect, it } from "vitest"

import {
  compactTokenCount,
  tokenUsageStatus,
  tokenUsageViewFromSummary,
} from "@/lib/agent-runtime/token-usage"
import type { AgentTokenUsageSummary } from "@/lib/agent-runtime"

describe("agent token usage helpers", () => {
  it("formats compact token counts", () => {
    expect(compactTokenCount(950, "en")).toBe("950")
    expect(compactTokenCount(12_450, "en")).toBe("12.5K")
    expect(compactTokenCount(2_400_000, "en")).toBe("2.4M")
  })

  it("builds a view model from cumulative usage with a context window", () => {
    const summary: AgentTokenUsageSummary = {
      has_token_usage: true,
      input_tokens: 97_000,
      output_tokens: 3_000,
      total_tokens: 100_000,
      cached_input_tokens: 12_000,
      reasoning_tokens: 600,
      context_window: 258_000,
      max_output_tokens: 8_192,
      turns_with_usage: 3,
      raw_totals: {},
    }

    expect(tokenUsageViewFromSummary(summary, "en")).toEqual({
      totalLabel: "100K",
      inputLabel: "97K",
      outputLabel: "3K",
      cachedInputLabel: "12K",
      reasoningLabel: "600",
      contextWindowLabel: "258K",
      maxOutputLabel: "8.2K",
      percentUsed: 39,
      percentRemaining: 61,
      status: "normal",
    })
  })

  it("does not build a view model when no real usage exists", () => {
    expect(
      tokenUsageViewFromSummary({
        has_token_usage: false,
        input_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
        turns_with_usage: 0,
        raw_totals: {},
      }),
    ).toBeNull()
  })

  it("assigns warning and critical states from context usage", () => {
    expect(tokenUsageStatus(69)).toBe("normal")
    expect(tokenUsageStatus(70)).toBe("warning")
    expect(tokenUsageStatus(90)).toBe("critical")
  })
})

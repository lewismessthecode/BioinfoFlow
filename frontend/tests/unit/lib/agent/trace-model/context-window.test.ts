import { describe, expect, it } from "vitest"

import {
  createContextWindowPresentation,
  findContextSnapshotForSequence,
} from "@/lib/agent/trace-model/context-window"
import type { AgentTraceContextSnapshot } from "@/lib/agent/trace-model/types"

function snapshot(
  overrides: Partial<AgentTraceContextSnapshot> = {},
): AgentTraceContextSnapshot {
  return {
    id: "context-1",
    turnId: "turn-1",
    modelTraceId: "trace-1",
    sequence: 3,
    throughSequence: 2,
    compacted: false,
    inputTokens: 13_400,
    outputTokens: 2_100,
    cachedInputTokens: 9_200,
    reasoningTokens: 700,
    totalTokens: 16_200,
    maxContextTokens: 200_000,
    composition: [
      { category: "system", characters: 8_000, tokens: 4_000 },
      { category: "user", characters: 3_000, tokens: 1_500 },
      { category: "tool", characters: 15_800, tokens: 7_900 },
    ],
    ...overrides,
  }
}

describe("Context Window presentation", () => {
  it("uses submitted input against model capacity instead of total usage", () => {
    const presentation = createContextWindowPresentation(snapshot())

    expect(presentation).toMatchObject({
      usedTokens: 13_400,
      capacityTokens: 200_000,
      usedPercent: 6.7,
      cachedInputTokens: 9_200,
      outputTokens: 2_100,
      reasoningTokens: 700,
    })
  })

  it("clamps over-capacity usage and leaves unknown capacity unavailable", () => {
    expect(
      createContextWindowPresentation(
        snapshot({ inputTokens: 250_000, maxContextTokens: 200_000 }),
      ),
    ).toMatchObject({ usedPercent: 100 })

    expect(
      createContextWindowPresentation(
        snapshot({ inputTokens: 13_400, maxContextTokens: null }),
      ),
    ).toMatchObject({
      usedTokens: 13_400,
      capacityTokens: null,
      usedPercent: null,
    })
  })

  it("uses exact category tokens only when every segment reports them", () => {
    const exact = createContextWindowPresentation(snapshot())

    expect(exact.compositionBasis).toBe("tokens")
    expect(exact.compositionEstimated).toBe(false)
    expect(exact.composition).toEqual([
      { category: "system", percent: 29.9 },
      { category: "user", percent: 11.2 },
      { category: "tool", percent: 59 },
    ])

    const estimated = createContextWindowPresentation(
      snapshot({
        composition: [
          { category: "system", characters: 800, tokens: null },
          { category: "user", characters: 200, tokens: null },
        ],
      }),
    )

    expect(estimated.compositionBasis).toBe("characters")
    expect(estimated.compositionEstimated).toBe(true)
    expect(estimated.composition).toEqual([
      { category: "system", percent: 80 },
      { category: "user", percent: 20 },
    ])
  })

  it("maps timeline events to the request that contains or precedes them", () => {
    const snapshots = [
      snapshot({ id: "request-1", sequence: 3, throughSequence: 2 }),
      snapshot({ id: "request-2", sequence: 8, throughSequence: 7 }),
      snapshot({ id: "request-3", sequence: 13, throughSequence: 12 }),
    ]

    expect(
      findContextSnapshotForSequence(snapshots, 2, "containing")?.id,
    ).toBe("request-1")
    expect(
      findContextSnapshotForSequence(snapshots, 3, "containing")?.id,
    ).toBe("request-1")
    expect(
      findContextSnapshotForSequence(snapshots, 7, "containing")?.id,
    ).toBe("request-2")
    expect(
      findContextSnapshotForSequence(snapshots, 6, "preceding")?.id,
    ).toBe("request-1")
    expect(
      findContextSnapshotForSequence(snapshots, 15, "preceding")?.id,
    ).toBe("request-3")
  })
})

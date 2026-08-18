import type {
  AgentTraceCategory,
  AgentTraceContextSnapshot,
} from "./types"

type ContextWindowCompositionSegment = {
  category: AgentTraceCategory
  percent: number
}

export type ContextWindowPresentation = {
  usedTokens: number | null
  capacityTokens: number | null
  usedPercent: number | null
  cachedInputTokens: number | null
  outputTokens: number | null
  reasoningTokens: number | null
  compositionBasis: "tokens" | "characters"
  compositionEstimated: boolean
  composition: ContextWindowCompositionSegment[]
}

export function createContextWindowPresentation(
  snapshot: AgentTraceContextSnapshot,
): ContextWindowPresentation {
  const usedTokens = snapshot.inputTokens
  const capacityTokens = snapshot.maxContextTokens
  const hasCapacity =
    usedTokens !== null && capacityTokens !== null && capacityTokens > 0
  const usedPercent = hasCapacity
    ? roundPercent(Math.min(100, (usedTokens / capacityTokens) * 100))
    : null
  const hasExactComposition = snapshot.composition.every(
    (segment) => segment.tokens !== null,
  )
  const tokenWeight = snapshot.composition.reduce(
    (sum, segment) => sum + (segment.tokens ?? 0),
    0,
  )
  const characterWeight = snapshot.composition.reduce(
    (sum, segment) => sum + segment.characters,
    0,
  )
  const useExactComposition = hasExactComposition && tokenWeight > 0
  const compositionTotal = useExactComposition ? tokenWeight : characterWeight
  const composition = snapshot.composition.map((segment) => ({
    category: segment.category,
    percent:
      compositionTotal > 0
        ? roundPercent(
            ((useExactComposition ? segment.tokens! : segment.characters) /
              compositionTotal) *
              100,
          )
        : 0,
  }))

  return {
    usedTokens,
    capacityTokens,
    usedPercent,
    cachedInputTokens: snapshot.cachedInputTokens,
    outputTokens: snapshot.outputTokens,
    reasoningTokens: snapshot.reasoningTokens,
    compositionBasis: useExactComposition ? "tokens" : "characters",
    compositionEstimated: !useExactComposition,
    composition,
  }
}

export function findContextSnapshotForSequence(
  snapshots: AgentTraceContextSnapshot[],
  sequence: number,
  preference: "preceding" | "containing" = "preceding",
) {
  const ordered = snapshots.toSorted(
    (left, right) => left.sequence - right.sequence,
  )
  const preceding = [...ordered]
    .reverse()
    .find((snapshot) => snapshot.sequence <= sequence)
  const exact = ordered.find((snapshot) => snapshot.sequence === sequence)
  const containing = ordered.find(
    (snapshot) => snapshot.throughSequence >= sequence,
  )

  return preference === "containing"
    ? exact ?? containing ?? preceding ?? ordered[0] ?? null
    : preceding ?? containing ?? ordered[0] ?? null
}

function roundPercent(value: number) {
  return Math.round(value * 10) / 10
}

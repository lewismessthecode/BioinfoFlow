type WorkflowSourceDiffRowType = "context" | "add" | "remove"

export type WorkflowSourceDiffRow = {
  type: WorkflowSourceDiffRowType
  previousLineNumber: number | null
  currentLineNumber: number | null
  text: string
}

type WorkflowSourceDiffSummary = {
  additions: number
  deletions: number
  changes: number
}

export type WorkflowSourceDiff = {
  rows: WorkflowSourceDiffRow[]
  summary: WorkflowSourceDiffSummary
}

type WorkflowSplitDiffCell = {
  lineNumber: number
  text: string
}

export type WorkflowSplitDiffRow = {
  type: WorkflowSourceDiffRowType
  left: WorkflowSplitDiffCell | null
  right: WorkflowSplitDiffCell | null
}

function splitSourceLines(source: string): string[] {
  return source.length === 0 ? [] : source.split("\n")
}

export function buildWorkflowSourceDiff(
  previousSource: string,
  currentSource: string,
): WorkflowSourceDiff {
  const previousLines = splitSourceLines(previousSource)
  const currentLines = splitSourceLines(currentSource)

  const lcs: number[][] = Array.from({ length: previousLines.length + 1 }, () =>
    Array.from({ length: currentLines.length + 1 }, () => 0),
  )

  for (let previousIndex = previousLines.length - 1; previousIndex >= 0; previousIndex -= 1) {
    for (let currentIndex = currentLines.length - 1; currentIndex >= 0; currentIndex -= 1) {
      if (previousLines[previousIndex] === currentLines[currentIndex]) {
        lcs[previousIndex]![currentIndex] = (lcs[previousIndex + 1]![currentIndex + 1] ?? 0) + 1
      } else {
        lcs[previousIndex]![currentIndex] = Math.max(
          lcs[previousIndex + 1]![currentIndex] ?? 0,
          lcs[previousIndex]![currentIndex + 1] ?? 0,
        )
      }
    }
  }

  const rows: WorkflowSourceDiffRow[] = []
  let previousIndex = 0
  let currentIndex = 0
  let previousLineNumber = 1
  let currentLineNumber = 1
  let additions = 0
  let deletions = 0

  while (previousIndex < previousLines.length && currentIndex < currentLines.length) {
    if (previousLines[previousIndex] === currentLines[currentIndex]) {
      rows.push({
        type: "context",
        previousLineNumber,
        currentLineNumber,
        text: previousLines[previousIndex] ?? "",
      })
      previousIndex += 1
      currentIndex += 1
      previousLineNumber += 1
      currentLineNumber += 1
      continue
    }

    if ((lcs[previousIndex + 1]![currentIndex] ?? 0) >= (lcs[previousIndex]![currentIndex + 1] ?? 0)) {
      rows.push({
        type: "remove",
        previousLineNumber,
        currentLineNumber: null,
        text: previousLines[previousIndex] ?? "",
      })
      previousIndex += 1
      previousLineNumber += 1
      deletions += 1
      continue
    }

    rows.push({
      type: "add",
      previousLineNumber: null,
      currentLineNumber,
      text: currentLines[currentIndex] ?? "",
    })
    currentIndex += 1
    currentLineNumber += 1
    additions += 1
  }

  while (previousIndex < previousLines.length) {
    rows.push({
      type: "remove",
      previousLineNumber,
      currentLineNumber: null,
      text: previousLines[previousIndex] ?? "",
    })
    previousIndex += 1
    previousLineNumber += 1
    deletions += 1
  }

  while (currentIndex < currentLines.length) {
    rows.push({
      type: "add",
      previousLineNumber: null,
      currentLineNumber,
      text: currentLines[currentIndex] ?? "",
    })
    currentIndex += 1
    currentLineNumber += 1
    additions += 1
  }

  return {
    rows,
    summary: {
      additions,
      deletions,
      changes: additions + deletions,
    },
  }
}

export function buildSplitDiffRows(rows: WorkflowSourceDiffRow[]): WorkflowSplitDiffRow[] {
  return rows.map((row) => ({
    type: row.type,
    left:
      row.previousLineNumber === null ? null : {
        lineNumber: row.previousLineNumber,
        text: row.text,
      },
    right:
      row.currentLineNumber === null ? null : {
        lineNumber: row.currentLineNumber,
        text: row.text,
      },
  }))
}

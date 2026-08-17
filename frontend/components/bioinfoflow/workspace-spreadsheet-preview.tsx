"use client"

import { useEffect, useMemo, useState } from "react"
import { useTranslations } from "next-intl"

import {
  loadSpreadsheetWorkbook,
  type SpreadsheetWorkbook,
} from "@/lib/agent/spreadsheet-workbook"
import { Loader2 } from "@/lib/icons"

type WorkbookState =
  | { blob: Blob; status: "loading" }
  | { blob: Blob; status: "ready"; workbook: SpreadsheetWorkbook }
  | { blob: Blob; status: "error" }

export function WorkspaceSpreadsheetPreview({
  blob,
  filename,
}: {
  blob: Blob
  filename: string
}) {
  const t = useTranslations("workspace.artifacts")
  const [state, setState] = useState<WorkbookState>({ blob, status: "loading" })
  const [sheetSelection, setSheetSelection] = useState({ blob, index: 0 })

  useEffect(() => {
    let cancelled = false
    void loadSpreadsheetWorkbook(blob)
      .then((workbook) => {
        if (!cancelled) setState({ blob, status: "ready", workbook })
      })
      .catch(() => {
        if (!cancelled) setState({ blob, status: "error" })
      })
    return () => {
      cancelled = true
    }
  }, [blob])

  const visibleState: WorkbookState =
    state.blob === blob ? state : { blob, status: "loading" }
  const activeSheetIndex = sheetSelection.blob === blob ? sheetSelection.index : 0

  if (visibleState.status === "loading") {
    return (
      <div
        data-testid="workspace-spreadsheet-preview"
        className="flex min-h-0 flex-1 items-center justify-center"
        role="status"
        aria-label={t("loadingPreview")}
      >
        <Loader2 className="size-4 animate-spin text-muted-foreground motion-reduce:animate-none" />
      </div>
    )
  }

  if (visibleState.status === "error") {
    return (
      <div
        data-testid="workspace-spreadsheet-preview"
        className="flex min-h-0 flex-1 items-center justify-center px-6 text-center text-xs text-muted-foreground"
      >
        {t("spreadsheetFailed")}
      </div>
    )
  }

  const sheets = visibleState.workbook.sheets
  const activeSheet = sheets[activeSheetIndex] ?? sheets[0]

  return (
    <section
      data-testid="workspace-spreadsheet-preview"
      className="flex min-h-0 min-w-0 flex-1 flex-col bg-background"
      aria-label={filename}
    >
      {sheets.length > 0 ? (
        <div
          role="tablist"
          aria-label={t("worksheetTabs")}
          className="flex h-10 shrink-0 items-end gap-0 overflow-x-auto border-b border-border/55 px-2"
        >
          {sheets.map((sheet, index) => {
            const active = index === activeSheetIndex
            return (
              <button
                key={`${sheet.name}:${index}`}
                type="button"
                role="tab"
                aria-selected={active}
                tabIndex={active ? 0 : -1}
                className="h-10 shrink-0 border-b-2 border-transparent px-3 text-xs text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/40 aria-selected:border-foreground aria-selected:font-medium aria-selected:text-foreground"
                onClick={() => setSheetSelection({ blob, index })}
              >
                {sheet.name}
              </button>
            )
          })}
        </div>
      ) : null}
      {activeSheet && activeSheet.rows.length > 0 ? (
        <SpreadsheetGrid sheet={activeSheet} />
      ) : (
        <div className="flex min-h-0 flex-1 items-center justify-center px-6 text-center text-xs text-muted-foreground">
          {t("spreadsheetEmpty")}
        </div>
      )}
    </section>
  )
}

function SpreadsheetGrid({
  sheet,
}: {
  sheet: SpreadsheetWorkbook["sheets"][number]
}) {
  const columnCount = useMemo(
    () => Math.max(0, ...sheet.rows.map((row) => row.length)),
    [sheet.rows],
  )

  return (
    <div className="min-h-0 min-w-0 flex-1 overflow-auto bg-background">
      <table className="min-w-full border-separate border-spacing-0 font-mono text-[11px] leading-4">
        <thead>
          <tr>
            <th className="sticky left-0 top-0 z-30 h-7 min-w-10 border-b border-r border-border/55 bg-muted/65 px-2 font-normal text-muted-foreground backdrop-blur" />
            {Array.from({ length: columnCount }, (_, index) => (
              <th
                key={index}
                scope="col"
                className="sticky top-0 z-20 h-7 min-w-28 border-b border-r border-border/55 bg-muted/65 px-2 font-medium text-muted-foreground backdrop-blur"
              >
                {columnLabel(index)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sheet.rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="hover:bg-muted/15">
              <th
                scope="row"
                className="sticky left-0 z-10 h-7 min-w-10 border-b border-r border-border/50 bg-muted/45 px-2 text-right font-normal tabular-nums text-muted-foreground"
              >
                {rowIndex + 1}
              </th>
              {Array.from({ length: columnCount }, (_, cellIndex) => {
                const cell = row[cellIndex] ?? ""
                return (
                  <td
                    key={cellIndex}
                    className="h-7 max-w-72 min-w-28 whitespace-nowrap border-b border-r border-border/40 px-2.5 py-1 text-foreground/85"
                    title={cell}
                  >
                    <span className="block max-w-72 overflow-hidden text-ellipsis">
                      {cell}
                    </span>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function columnLabel(index: number) {
  let value = index + 1
  let label = ""
  while (value > 0) {
    value -= 1
    label = String.fromCharCode(65 + (value % 26)) + label
    value = Math.floor(value / 26)
  }
  return label
}

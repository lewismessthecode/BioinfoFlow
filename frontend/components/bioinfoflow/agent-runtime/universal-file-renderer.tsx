"use client"

import { useEffect, useMemo, useState, type ReactNode } from "react"
import {
  AlertCircle,
  FileArchive,
  FileCode,
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
  Loader2,
} from "lucide-react"
import { useTranslations } from "next-intl"

import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { cn } from "@/lib/utils"
import {
  WORKBOOK_SIZE_LIMIT_BYTES,
  columnLabel,
  delimiterForPath,
  filePreviewKind,
  isDelimitedPath,
  isWorkbookPath,
  normalizeSpreadsheetRows,
  parseDelimitedRows,
  truncateRowsAndColumns,
  type SpreadsheetRows,
  type UniversalFileKind,
} from "./file-renderer-utils"

export type UniversalFileResource = {
  path: string
  title?: string | null
  type?: string | null
  content?: string | null
  rows?: unknown
  size?: number | null
  language?: string | null
  mimeType?: string | null
  binary?: boolean | null
  inlineUrl?: string | null
  downloadUrl?: string | null
  resourceUrl?: string | null
}

type WorkbookSheet = {
  name: string
  rows: SpreadsheetRows
}

type WorkbookState =
  | { status: "idle" | "loading" }
  | { status: "ready"; sheets: WorkbookSheet[] }
  | { status: "error"; message: string }

export function UniversalFileRenderer({
  file,
  className,
}: {
  file: UniversalFileResource
  className?: string
}) {
  const t = useTranslations("agentRuntime")
  const kind = filePreviewKind({
    path: file.path,
    type: file.type,
    language: file.language,
    mimeType: file.mimeType,
    binary: file.binary,
  })
  const displayName = file.title || file.path.split("/").pop() || file.path
  const inlineUrl = file.inlineUrl || file.resourceUrl || null

  return (
    <div
      className={cn("min-h-0 min-w-0 flex-1 overflow-hidden bg-background", className)}
      data-file-preview-kind={kind}
      data-testid="universal-file-renderer"
    >
      {kind === "markdown" ? (
        <div className="h-full overflow-auto bg-[#fbfbfa] p-4">
          <MarkdownRenderer
            content={file.content || t("renderer.previewUnavailable")}
            className="mx-auto w-full max-w-3xl px-1 py-2 text-sm leading-6"
          />
        </div>
      ) : null}

      {kind === "html" ? (
        file.content || inlineUrl ? (
          <iframe
            title={displayName}
            srcDoc={file.content || undefined}
            src={file.content ? undefined : inlineUrl || undefined}
            sandbox=""
            className="h-full min-h-0 w-full border-0 bg-background"
          />
        ) : (
          <RendererState
            kind="empty"
            icon={<FileCode className="h-8 w-8" />}
            title={t("renderer.previewUnavailable")}
            description={t("renderer.noRenderableSource")}
          />
        )
      ) : null}

      {kind === "pdf" ? (
        inlineUrl ? (
          <iframe
            title={displayName}
            src={inlineUrl}
            className="h-full min-h-0 w-full border-0 bg-[#f7f6f3]"
          />
        ) : (
          <RendererState
            kind="empty"
            icon={<FileText className="h-8 w-8" />}
            title={t("renderer.previewUnavailable")}
            description={t("renderer.noRenderableSource")}
          />
        )
      ) : null}

      {kind === "image" ? (
        inlineUrl ? (
          <div className="flex h-full min-h-0 items-center justify-center overflow-auto bg-[#fbfbfa] p-4">
            {/* Agent artifacts can be local API URLs, so Next Image optimization is not applicable. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={inlineUrl}
              alt={displayName}
              className="max-h-full max-w-full rounded-lg border border-border/70 bg-background object-contain"
            />
          </div>
        ) : (
          <RendererState
            kind="empty"
            icon={<ImageIcon className="h-8 w-8" />}
            title={t("renderer.previewUnavailable")}
            description={t("renderer.noRenderableSource")}
          />
        )
      ) : null}

      {kind === "spreadsheet" ? <SpreadsheetPreview file={file} /> : null}

      {kind === "json" ? (
        <CodePreview content={formatJsonContent(file.content)} iconKind={kind} />
      ) : null}

      {kind === "text" ? (
        <CodePreview content={file.content || t("renderer.previewUnavailable")} iconKind={kind} />
      ) : null}

      {kind === "unsupported" ? (
        <RendererState
          kind="empty"
          icon={<FileArchive className="h-8 w-8" />}
          title={t("renderer.previewUnsupported")}
          description={t("renderer.openDefaultDescription")}
        />
      ) : null}
    </div>
  )
}

export function fileKindLabel(t: ReturnType<typeof useTranslations>, kind: UniversalFileKind) {
  return t(`renderer.kinds.${kind}`)
}

function SpreadsheetPreview({ file }: { file: UniversalFileResource }) {
  const t = useTranslations("agentRuntime")
  const directRows = useMemo(() => {
    const payloadRows = normalizeSpreadsheetRows(file.rows)
    if (payloadRows) return payloadRows
    if (!file.content?.trim()) return null
    if (!isDelimitedPath(file.path, file.language, file.mimeType) && !file.type) return null
    return parseDelimitedRows(
      file.content,
      delimiterForPath(file.path, file.mimeType),
    )
  }, [file.content, file.language, file.mimeType, file.path, file.rows, file.type])

  if (directRows?.length) {
    return (
      <SpreadsheetWorkbookView
        sheets={[{ name: t("renderer.defaultSheetName"), rows: directRows }]}
      />
    )
  }

  if (isWorkbookPath(file.path)) {
    return <WorkbookPreview file={file} />
  }

  return (
    <RendererState
      kind="empty"
      icon={<FileSpreadsheet className="h-8 w-8" />}
      title={t("renderer.previewUnavailable")}
      description={t("renderer.noRenderableSource")}
    />
  )
}

function WorkbookPreview({ file }: { file: UniversalFileResource }) {
  const t = useTranslations("agentRuntime")
  const [state, setState] = useState<WorkbookState>({ status: "idle" })
  const sourceUrl = file.inlineUrl || file.resourceUrl || file.downloadUrl || null
  const emptyMessage = t("renderer.workbookEmpty")
  const failedMessage = t("renderer.workbookFailed")
  const fetchFailedMessage = t("renderer.workbookFetchFailed")
  const noSourceMessage = t("renderer.noRenderableSource")
  const tooLargeMessage = t("renderer.workbookTooLarge")

  useEffect(() => {
    if (!sourceUrl) {
      setState({ status: "error", message: noSourceMessage })
      return
    }

    if (typeof file.size === "number" && file.size > WORKBOOK_SIZE_LIMIT_BYTES) {
      setState({
        status: "error",
        message: tooLargeMessage,
      })
      return
    }

    const controller = new AbortController()
    setState({ status: "loading" })

    async function loadWorkbook() {
      try {
        const response = await fetch(sourceUrl, { signal: controller.signal })
        if (!response.ok) throw new Error(fetchFailedMessage)
        const buffer = await response.arrayBuffer()
        const XLSX = await import("xlsx")
        const workbook = XLSX.read(buffer, { type: "array", cellDates: true })
        const sheets = workbook.SheetNames.map((name) => {
          const sheet = workbook.Sheets[name]
          const rows = XLSX.utils.sheet_to_json(sheet, {
            header: 1,
            raw: false,
            blankrows: false,
            defval: "",
          })
          return {
            name,
            rows: normalizeSpreadsheetRows(rows) ?? [],
          }
        }).filter((sheet) => sheet.rows.length > 0)

        if (!sheets.length) throw new Error(emptyMessage)
        setState({ status: "ready", sheets })
      } catch (err) {
        if (controller.signal.aborted) return
        setState({
          status: "error",
          message: err instanceof Error ? err.message : failedMessage,
        })
      }
    }

    void loadWorkbook()
    return () => controller.abort()
  }, [
    emptyMessage,
    failedMessage,
    fetchFailedMessage,
    file.size,
    noSourceMessage,
    sourceUrl,
    tooLargeMessage,
  ])

  if (state.status === "ready") return <SpreadsheetWorkbookView sheets={state.sheets} />
  if (state.status === "error") {
    return (
      <RendererState
        kind="error"
        icon={<AlertCircle className="h-8 w-8" />}
        title={t("renderer.workbookFailed")}
        description={state.message}
      />
    )
  }
  return (
    <RendererState
      kind="loading"
      icon={<Loader2 className="h-8 w-8 animate-spin" />}
      title={t("renderer.workbookLoading")}
      description={t("renderer.workbookLoadingDescription")}
    />
  )
}

function SpreadsheetWorkbookView({ sheets }: { sheets: WorkbookSheet[] }) {
  const [activeSheetIndex, setActiveSheetIndex] = useState(0)
  const t = useTranslations("agentRuntime")
  const safeActiveSheetIndex = Math.min(activeSheetIndex, Math.max(0, sheets.length - 1))
  const activeSheet = sheets[safeActiveSheetIndex]
  const rows = truncateRowsAndColumns(activeSheet?.rows ?? [])
  const columnCount = Math.max(1, ...rows.map((row) => row.length))

  if (!rows.length) {
    return (
      <RendererState
        kind="empty"
        icon={<FileSpreadsheet className="h-8 w-8" />}
        title={t("renderer.workbookEmpty")}
        description={t("renderer.workbookEmptyDescription")}
      />
    )
  }

  return (
    <div className="grid h-full min-h-0 grid-rows-[1fr_auto] bg-[#fbfbfa]">
      <div className="min-h-0 overflow-auto">
        <table className="min-w-max border-separate border-spacing-0 text-left text-sm tabular-nums">
          <thead className="sticky top-0 z-20 bg-[#f7f6f3] text-[11px] font-medium text-muted-foreground">
            <tr>
              <th className="sticky left-0 z-30 h-8 w-12 border-b border-r border-border/70 bg-[#f7f6f3]" />
              {Array.from({ length: columnCount }).map((_, index) => (
                <th
                  key={index}
                  className="h-8 min-w-[8rem] border-b border-r border-border/70 px-3 text-center font-medium"
                >
                  {columnLabel(index)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                <th className="sticky left-0 z-10 h-8 w-12 border-b border-r border-border/70 bg-[#f7f6f3] text-center text-[11px] font-medium text-muted-foreground">
                  {rowIndex + 1}
                </th>
                {Array.from({ length: columnCount }).map((_, cellIndex) => (
                  <td
                    key={cellIndex}
                    className={cn(
                      "h-8 min-w-[8rem] max-w-[20rem] border-b border-r border-border/55 bg-background px-3 align-middle text-foreground",
                      rowIndex === 0 && "bg-[#fbfbfa] font-medium",
                    )}
                  >
                    <span className="block truncate" title={row[cellIndex] ?? ""}>
                      {row[cellIndex] ?? ""}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex min-h-11 items-center gap-1 overflow-x-auto border-t border-border/70 bg-[#f7f6f3] px-3 py-2">
        {sheets.map((sheet, index) => (
          <button
            key={`${sheet.name}-${index}`}
            type="button"
            className={cn(
              "h-7 shrink-0 rounded-md border px-3 text-xs font-medium transition-colors",
              index === safeActiveSheetIndex
                ? "border-foreground/20 bg-background text-foreground"
                : "border-transparent text-muted-foreground hover:bg-background/80 hover:text-foreground",
            )}
            onClick={() => setActiveSheetIndex(index)}
          >
            {sheet.name}
          </button>
        ))}
        <span className="ml-auto shrink-0 pl-3 text-[11px] text-muted-foreground">
          {t("renderer.previewLimit", { rows: rows.length, columns: columnCount })}
        </span>
      </div>
    </div>
  )
}

function CodePreview({
  content,
  iconKind,
}: {
  content: string
  iconKind: "json" | "text"
}) {
  const lines = content.split(/\r?\n/)
  return (
    <div className="h-full min-h-0 overflow-auto bg-[#fbfbfa]">
      <pre className="min-w-max p-3 font-mono text-xs leading-5 text-foreground tabular-nums">
        <code>
          {lines.map((line, index) => (
            <span key={index} className="table-row">
              <span className="sticky left-0 table-cell select-none border-r border-border/60 bg-[#f7f6f3] pr-3 text-right text-muted-foreground">
                {index + 1}
              </span>
              <span className="table-cell whitespace-pre pl-3">
                {line || (iconKind === "json" ? "" : " ")}
              </span>
            </span>
          ))}
        </code>
      </pre>
    </div>
  )
}

function RendererState({
  kind,
  icon,
  title,
  description,
}: {
  kind: "empty" | "loading" | "error"
  icon: ReactNode
  title: string
  description: string
}) {
  return (
    <div
      className="flex h-full min-h-[220px] min-w-0 items-center justify-center bg-[#fbfbfa] p-6 text-center"
      data-renderer-state={kind}
    >
      <div className="max-w-sm">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg border border-border/70 bg-background text-muted-foreground">
          {icon}
        </div>
        <p className="mt-3 text-sm font-medium text-foreground">{title}</p>
        <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{description}</p>
      </div>
    </div>
  )
}

function formatJsonContent(content?: string | null) {
  if (!content?.trim()) return ""
  try {
    return JSON.stringify(JSON.parse(content), null, 2)
  } catch {
    return content
  }
}

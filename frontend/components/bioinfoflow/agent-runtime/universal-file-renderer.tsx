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
  PREVIEW_COLUMN_LIMIT,
  PREVIEW_ROW_LIMIT,
  TEXT_PREVIEW_SIZE_LIMIT_BYTES,
  TEXT_PREVIEW_LINE_LIMIT,
  WORKBOOK_SHEET_LIMIT,
  WORKBOOK_SIZE_LIMIT_BYTES,
  columnLabel,
  delimiterForPath,
  filePreviewKind,
  isDelimitedPath,
  isWorkbookPath,
  normalizeSpreadsheetRows,
  parseDelimitedRows,
  prepareTextPreviewContent,
  truncateRowsAndColumns,
  workbookPreviewReadOptions,
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
  | { requestKey: string; status: "ready"; sheets: WorkbookSheet[] }
  | { requestKey: string; status: "error"; message: string }

type TextLoadState =
  | { requestKey: string; status: "ready"; content: string | null; error: null }
  | { requestKey: string; status: "error"; content: null; error: string }

type XlsxModule = typeof import("@e965/xlsx")

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
  const textFetchFailedMessage = t("renderer.textFetchFailed")
  const textTooLargeMessage = t("renderer.textTooLarge")
  const textPreviewLimitedMessage = t("renderer.textPreviewLimited", {
    lines: TEXT_PREVIEW_LINE_LIMIT,
  })
  const shouldFetchText =
    !file.content &&
    Boolean(inlineUrl) &&
    (kind === "markdown" ||
      kind === "json" ||
      kind === "text")
  const textRequestKey = shouldFetchText ? `${kind}:${inlineUrl}` : ""
  const [textLoadState, setTextLoadState] = useState<TextLoadState>({
    requestKey: "",
    status: "ready",
    content: null,
    error: null,
  })

  useEffect(() => {
    if (!shouldFetchText || !inlineUrl) return
    const controller = new AbortController()
    let cancelled = false
    async function loadTextPreview() {
      try {
        const response = await fetch(inlineUrl, {
          credentials: "include",
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(textFetchFailedMessage)
        const content = await readResponseTextWithLimit(
          response,
          TEXT_PREVIEW_SIZE_LIMIT_BYTES,
          textTooLargeMessage,
        )
        if (!cancelled) {
          setTextLoadState({
            requestKey: textRequestKey,
            status: "ready",
            content,
            error: null,
          })
        }
      } catch (err) {
        if (controller.signal.aborted || cancelled) return
        if (!cancelled) {
          setTextLoadState({
            requestKey: textRequestKey,
            status: "error",
            content: null,
            error: err instanceof Error ? err.message : textFetchFailedMessage,
          })
        }
      }
    }
    void loadTextPreview()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [
    inlineUrl,
    shouldFetchText,
    textFetchFailedMessage,
    textRequestKey,
    textTooLargeMessage,
  ])

  const textStateMatchesRequest = textLoadState.requestKey === textRequestKey
  const textLoading = shouldFetchText && !textStateMatchesRequest
  const textError =
    shouldFetchText && textStateMatchesRequest && textLoadState.status === "error"
      ? textLoadState.error
      : null
  const rawPreviewContent =
    file.content ??
    (shouldFetchText && textStateMatchesRequest && textLoadState.status === "ready"
      ? textLoadState.content ?? ""
      : "")
  const preparedPreview = useMemo(
    () => prepareTextPreviewContent(rawPreviewContent),
    [rawPreviewContent],
  )
  const previewContent = preparedPreview.content
  const previewTooLarge = preparedPreview.tooLarge
  const previewLimitedMessage = preparedPreview.truncated ? textPreviewLimitedMessage : null

  return (
    <div
      className={cn("min-h-0 min-w-0 flex-1 overflow-hidden bg-background", className)}
      data-file-preview-kind={kind}
      data-testid="universal-file-renderer"
    >
      {kind === "markdown" ? (
        textLoading ? (
          <RendererState
            kind="loading"
            icon={<Loader2 className="h-8 w-8 animate-spin" />}
            title={t("renderer.textLoading")}
            description={t("renderer.textLoadingDescription")}
          />
        ) : textError || previewTooLarge ? (
          <RendererState
            kind="error"
            icon={<AlertCircle className="h-8 w-8" />}
            title={t("renderer.textFetchFailed")}
            description={textError || textTooLargeMessage}
          />
        ) : (
          <div className="h-full overflow-auto bg-muted/20 p-4">
            <MarkdownRenderer
              content={
                markdownPreviewContent(
                  previewContent || t("renderer.previewUnavailable"),
                  previewLimitedMessage,
                )
              }
              className="mx-auto w-full max-w-3xl px-1 py-2 text-sm leading-6"
            />
          </div>
        )
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
            className="h-full min-h-0 w-full border-0 bg-muted/30"
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
          <div className="flex h-full min-h-0 items-center justify-center overflow-auto bg-muted/20 p-4">
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
        textLoading ? (
          <RendererState
            kind="loading"
            icon={<Loader2 className="h-8 w-8 animate-spin" />}
            title={t("renderer.textLoading")}
            description={t("renderer.textLoadingDescription")}
          />
        ) : textError || previewTooLarge ? (
          <RendererState
            kind="error"
            icon={<AlertCircle className="h-8 w-8" />}
            title={t("renderer.textFetchFailed")}
            description={textError || textTooLargeMessage}
          />
        ) : (
          <CodePreview
            content={formatJsonContent(previewContent)}
            iconKind={kind}
            truncatedNotice={previewLimitedMessage}
          />
        )
      ) : null}

      {kind === "text" ? (
        textLoading ? (
          <RendererState
            kind="loading"
            icon={<Loader2 className="h-8 w-8 animate-spin" />}
            title={t("renderer.textLoading")}
            description={t("renderer.textLoadingDescription")}
          />
        ) : textError || previewTooLarge ? (
          <RendererState
            kind="error"
            icon={<AlertCircle className="h-8 w-8" />}
            title={t("renderer.textFetchFailed")}
            description={textError || textTooLargeMessage}
          />
        ) : (
          <CodePreview
            content={previewContent || t("renderer.previewUnavailable")}
            iconKind={kind}
            truncatedNotice={previewLimitedMessage}
          />
        )
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
  const directContentPreview = useMemo(
    () => (file.content ? prepareTextPreviewContent(file.content) : null),
    [file.content],
  )
  const directRows = useMemo(() => {
    const payloadRows = normalizeSpreadsheetRows(file.rows)
    if (payloadRows) return payloadRows
    if (!directContentPreview?.content.trim()) return null
    if (!isDelimitedPath(file.path, file.language, file.mimeType) && !file.type) return null
    return parseDelimitedRows(
      directContentPreview.content,
      delimiterForPath(file.path, file.mimeType),
    )
  }, [
    directContentPreview,
    file.language,
    file.mimeType,
    file.path,
    file.rows,
    file.type,
  ])

  if (directContentPreview?.tooLarge) {
    return (
      <RendererState
        kind="error"
        icon={<AlertCircle className="h-8 w-8" />}
        title={t("renderer.textFetchFailed")}
        description={t("renderer.textTooLarge")}
      />
    )
  }

  if (directRows?.length) {
    return (
      <SpreadsheetWorkbookView
        sheets={[{ name: t("renderer.defaultSheetName"), rows: directRows }]}
      />
    )
  }

  if (
    !file.content &&
    file.inlineUrl &&
    isDelimitedPath(file.path, file.language, file.mimeType)
  ) {
    return (
      <DelimitedUrlSpreadsheetPreview
        file={file}
        sourceUrl={file.inlineUrl}
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

function DelimitedUrlSpreadsheetPreview({
  file,
  sourceUrl,
}: {
  file: UniversalFileResource
  sourceUrl: string
}) {
  const t = useTranslations("agentRuntime")
  const textFetchFailedMessage = t("renderer.textFetchFailed")
  const textTooLargeMessage = t("renderer.textTooLarge")
  const [state, setState] = useState<TextLoadState>({
    requestKey: "",
    status: "ready",
    content: null,
    error: null,
  })
  const requestKey = `${file.path}:${sourceUrl}`

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    async function loadRows() {
      try {
        const response = await fetch(sourceUrl, {
          credentials: "include",
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(textFetchFailedMessage)
        const content = await readResponseTextWithLimit(
          response,
          TEXT_PREVIEW_SIZE_LIMIT_BYTES,
          textTooLargeMessage,
        )
        if (!cancelled) {
          setState({ requestKey, status: "ready", content, error: null })
        }
      } catch (err) {
        if (controller.signal.aborted || cancelled) return
        if (!cancelled) {
          setState({
            requestKey,
            status: "error",
            content: null,
            error: err instanceof Error ? err.message : textFetchFailedMessage,
          })
        }
      }
    }
    void loadRows()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [requestKey, sourceUrl, textFetchFailedMessage, textTooLargeMessage])

  if (state.requestKey !== requestKey) {
    return (
      <RendererState
        kind="loading"
        icon={<Loader2 className="h-8 w-8 animate-spin" />}
        title={t("renderer.textLoading")}
        description={t("renderer.textLoadingDescription")}
      />
    )
  }
  if (state.status === "error") {
    return (
      <RendererState
        kind="error"
        icon={<AlertCircle className="h-8 w-8" />}
        title={t("renderer.textFetchFailed")}
        description={state.error}
      />
    )
  }

  const rows = parseDelimitedRows(
    state.content ?? "",
    delimiterForPath(file.path, file.mimeType),
  )
  return rows.length ? (
    <SpreadsheetWorkbookView
      sheets={[{ name: t("renderer.defaultSheetName"), rows }]}
    />
  ) : (
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
  const sourceUrl = file.inlineUrl || file.resourceUrl || file.downloadUrl || null
  const requestKey = `${file.path}:${sourceUrl ?? ""}:${file.size ?? ""}`
  const [state, setState] = useState<WorkbookState>({
    requestKey: "",
    status: "ready",
    sheets: [],
  })
  const emptyMessage = t("renderer.workbookEmpty")
  const failedMessage = t("renderer.workbookFailed")
  const fetchFailedMessage = t("renderer.workbookFetchFailed")
  const noSourceMessage = t("renderer.noRenderableSource")
  const tooLargeMessage = t("renderer.workbookTooLarge")

  useEffect(() => {
    if (!sourceUrl) return
    if (typeof file.size === "number" && file.size > WORKBOOK_SIZE_LIMIT_BYTES) return

    const controller = new AbortController()
    let cancelled = false

    async function loadWorkbook() {
      try {
        const response = await fetch(sourceUrl, {
          credentials: "include",
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(fetchFailedMessage)
        const buffer = await readResponseArrayBufferWithLimit(
          response,
          WORKBOOK_SIZE_LIMIT_BYTES,
          tooLargeMessage,
        )
        if (cancelled) return
        const XLSX = await import("@e965/xlsx")
        if (cancelled) return
        const workbook = XLSX.read(buffer, {
          type: "array",
          cellDates: true,
          ...workbookPreviewReadOptions(),
        })
        const sheets = workbook.SheetNames.slice(0, WORKBOOK_SHEET_LIMIT).map((name) => {
          const sheet = workbook.Sheets[name]
          if (!sheet) return { name, rows: [] }
          const range = previewWorksheetRange(
            XLSX,
            typeof sheet?.["!ref"] === "string" ? sheet["!ref"] : undefined,
          )
          const rows = XLSX.utils.sheet_to_json(sheet, {
            header: 1,
            raw: false,
            blankrows: false,
            defval: "",
            ...(range ? { range } : {}),
          })
          return {
            name,
            rows: normalizeSpreadsheetRows(rows) ?? [],
          }
        }).filter((sheet) => sheet.rows.length > 0)

        if (!sheets.length) throw new Error(emptyMessage)
        if (!cancelled) setState({ requestKey, status: "ready", sheets })
      } catch (err) {
        if (controller.signal.aborted || cancelled) return
        setState({
          requestKey,
          status: "error",
          message: err instanceof Error ? err.message : failedMessage,
        })
      }
    }

    void loadWorkbook()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [
    emptyMessage,
    failedMessage,
    fetchFailedMessage,
    file.size,
    requestKey,
    sourceUrl,
    tooLargeMessage,
  ])

  if (!sourceUrl) {
    return (
      <RendererState
        kind="error"
        icon={<AlertCircle className="h-8 w-8" />}
        title={t("renderer.workbookFailed")}
        description={noSourceMessage}
      />
    )
  }
  if (typeof file.size === "number" && file.size > WORKBOOK_SIZE_LIMIT_BYTES) {
    return (
      <RendererState
        kind="error"
        icon={<AlertCircle className="h-8 w-8" />}
        title={t("renderer.workbookFailed")}
        description={tooLargeMessage}
      />
    )
  }

  if (state.requestKey !== requestKey) {
    return (
      <RendererState
        kind="loading"
        icon={<Loader2 className="h-8 w-8 animate-spin" />}
        title={t("renderer.workbookLoading")}
        description={t("renderer.workbookLoadingDescription")}
      />
    )
  }
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
  return null
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
    <div className="grid h-full min-h-0 grid-rows-[1fr_auto] bg-muted/20">
      <div className="min-h-0 overflow-auto">
        <table className="min-w-max border-separate border-spacing-0 text-left text-sm tabular-nums">
          <thead className="sticky top-0 z-20 bg-muted text-[11px] font-medium text-muted-foreground">
            <tr>
              <th className="sticky left-0 z-30 h-8 w-12 border-b border-r border-border/70 bg-muted" />
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
                <th className="sticky left-0 z-10 h-8 w-12 border-b border-r border-border/70 bg-muted text-center text-[11px] font-medium text-muted-foreground">
                  {rowIndex + 1}
                </th>
                {Array.from({ length: columnCount }).map((_, cellIndex) => (
                  <td
                    key={cellIndex}
                    className={cn(
                      "h-8 min-w-[8rem] max-w-[20rem] border-b border-r border-border/55 bg-background px-3 align-middle text-foreground",
                      rowIndex === 0 && "bg-muted/20 font-medium",
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
      <div className="flex min-h-11 items-center gap-1 overflow-x-auto border-t border-border/70 bg-muted px-3 py-2">
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

function previewWorksheetRange(XLSX: XlsxModule, ref?: string) {
  if (!ref) return undefined
  try {
    const range = XLSX.utils.decode_range(ref)
    range.e.r = Math.min(range.e.r, PREVIEW_ROW_LIMIT - 1)
    range.e.c = Math.min(range.e.c, PREVIEW_COLUMN_LIMIT - 1)
    return XLSX.utils.encode_range(range)
  } catch {
    return undefined
  }
}

function CodePreview({
  content,
  iconKind,
  truncatedNotice,
}: {
  content: string
  iconKind: "json" | "text"
  truncatedNotice?: string | null
}) {
  const lines = content.split(/\r?\n/)
  return (
    <div className="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] bg-muted/20">
      <div className="min-h-0 overflow-auto">
        <pre className="min-w-max p-3 font-mono text-xs leading-5 text-foreground tabular-nums">
          <code>
            {lines.map((line, index) => (
              <span key={index} className="table-row">
                <span className="sticky left-0 table-cell select-none border-r border-border/60 bg-muted pr-3 text-right text-muted-foreground">
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
      {truncatedNotice ? (
        <div className="border-t border-border/70 bg-background px-3 py-2 text-[11px] text-muted-foreground">
          {truncatedNotice}
        </div>
      ) : null}
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
      className="flex h-full min-h-[220px] min-w-0 items-center justify-center bg-muted/20 p-6 text-center"
      data-renderer-state={kind}
      role={kind === "loading" ? "status" : kind === "error" ? "alert" : undefined}
      aria-live={kind === "loading" ? "polite" : undefined}
      aria-label={kind === "loading" || kind === "error" ? title : undefined}
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

function markdownPreviewContent(content: string, truncatedNotice?: string | null) {
  if (!truncatedNotice) return content
  return `${content}\n\n---\n_${truncatedNotice}_`
}

async function readResponseTextWithLimit(
  response: Response,
  limitBytes: number,
  tooLargeMessage: string,
) {
  const buffer = await readResponseArrayBufferWithLimit(response, limitBytes, tooLargeMessage)
  return new TextDecoder().decode(buffer)
}

async function readResponseArrayBufferWithLimit(
  response: Response,
  limitBytes: number,
  tooLargeMessage: string,
) {
  const contentLength = response.headers?.get("content-length")
  if (contentLength && Number(contentLength) > limitBytes) {
    throw new Error(tooLargeMessage)
  }

  if (!response.body) {
    const buffer = await response.arrayBuffer()
    if (buffer.byteLength > limitBytes) throw new Error(tooLargeMessage)
    return buffer
  }

  const reader = response.body.getReader()
  const chunks: Uint8Array[] = []
  let total = 0
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    if (!value) continue
    total += value.byteLength
    if (total > limitBytes) {
      await reader.cancel()
      throw new Error(tooLargeMessage)
    }
    chunks.push(value)
  }

  const combined = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    combined.set(chunk, offset)
    offset += chunk.byteLength
  }
  return combined.buffer
}

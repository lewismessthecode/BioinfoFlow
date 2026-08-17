"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useLocale, useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  ArrowLeft,
  Box,
  Download,
  FileCode,
  FileJson,
  FileSpreadsheet,
  FileText,
  Loader2,
  RefreshCw,
} from "@/lib/icons"
import {
  bioinfoFlowAgentWorkspaceAdapter,
  type AgentWorkspaceAdapter,
  type WorkspaceArtifact,
  type WorkspaceArtifactContent,
  workspaceArtifactSelectionId,
} from "@/lib/agent/workspace-adapter"
import { WorkspaceCodePreview } from "./workspace-code-preview"

const MAX_INLINE_PREVIEW_BYTES = 8 * 1024 * 1024
const NON_DELIVERABLE_TYPES = new Set(["command", "log_summary", "todo_list"])

type ArtifactPreview =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "content"; value: WorkspaceArtifactContent; url: string | null }
  | { kind: "metadata" }
  | { kind: "error" }

export function AgentArtifactsPanel({
  sessionId,
  projectId,
  selectedArtifactId,
  onSelectedArtifactIdChange,
  adapter = bioinfoFlowAgentWorkspaceAdapter,
}: {
  sessionId?: string | null
  projectId?: string | null
  selectedArtifactId?: string | null
  onSelectedArtifactIdChange?: (artifactId: string | null) => void
  adapter?: AgentWorkspaceAdapter
}) {
  const t = useTranslations("workspace.artifacts")
  const locale = useLocale()
  const [reloadNonce, setReloadNonce] = useState(0)
  const [artifactState, setArtifactState] = useState<{
    requestKey: string
    status: "ready" | "error"
    artifacts: WorkspaceArtifact[]
  }>({ requestKey: "", status: "ready", artifacts: [] })
  const [selected, setSelected] = useState<WorkspaceArtifact | null>(null)
  const [preview, setPreview] = useState<ArtifactPreview>({ kind: "idle" })
  const objectUrlRef = useRef<string | null>(null)
  const requestKey =
    sessionId || projectId
      ? `${sessionId ?? ""}:${projectId ?? ""}:${reloadNonce}`
      : ""

  const releaseObjectUrl = useCallback(() => {
    if (!objectUrlRef.current) return
    URL.revokeObjectURL(objectUrlRef.current)
    objectUrlRef.current = null
  }, [])

  useEffect(() => {
    releaseObjectUrl()
    if (!sessionId && !projectId) return releaseObjectUrl
    const controller = new AbortController()
    void adapter
      .listArtifacts({ sessionId, projectId, signal: controller.signal })
      .then((next) => {
        setArtifactState({
          requestKey,
          status: "ready",
          artifacts: next
            .filter(isDeliverable)
            .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt)),
        })
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setArtifactState({ requestKey, status: "error", artifacts: [] })
        }
      })
    return () => {
      controller.abort()
      releaseObjectUrl()
    }
  }, [adapter, projectId, releaseObjectUrl, requestKey, sessionId])

  const stateMatchesRequest = artifactState.requestKey === requestKey
  const status = !sessionId && !projectId
    ? "idle"
    : stateMatchesRequest
      ? artifactState.status
      : "loading"
  const artifacts = stateMatchesRequest ? artifactState.artifacts : []

  const activeSelection = artifacts.some((artifact) => artifact.id === selected?.id)
    ? selected
    : null

  const openArtifact = useCallback(
    async (artifact: WorkspaceArtifact) => {
      releaseObjectUrl()
      setSelected(artifact)
      onSelectedArtifactIdChange?.(workspaceArtifactSelectionId(artifact))
      if (!artifact.resource) {
        setPreview({ kind: "metadata" })
        return
      }
      if (
        artifact.sizeBytes !== null &&
        artifact.sizeBytes > MAX_INLINE_PREVIEW_BYTES
      ) {
        setPreview({ kind: "metadata" })
        return
      }
      setPreview({ kind: "loading" })
      try {
        const value = await adapter.fetchArtifactContent({ artifact })
        const url = shouldUseObjectUrl(value.mediaType) ? URL.createObjectURL(value.blob) : null
        objectUrlRef.current = url
        setPreview({ kind: "content", value, url })
      } catch {
        setPreview({ kind: "error" })
      }
    },
    [adapter, onSelectedArtifactIdChange, releaseObjectUrl],
  )

  useEffect(() => {
    if (selectedArtifactId === undefined) return
    if (selectedArtifactId === null) {
      if (selected) {
        releaseObjectUrl()
        setSelected(null)
        setPreview({ kind: "idle" })
      }
      return
    }
    const artifact = artifacts.find(
      (candidate) => workspaceArtifactSelectionId(candidate) === selectedArtifactId,
    )
    if (!artifact || artifact.id === selected?.id) return
    void openArtifact(artifact)
  }, [artifacts, openArtifact, releaseObjectUrl, selected, selectedArtifactId])

  const download = useCallback(async () => {
    if (!selected) return
    try {
      const value =
        preview.kind === "content"
          ? preview.value
          : await adapter.fetchArtifactContent({ artifact: selected })
      saveBlob(value.blob, value.filename || selected.title)
    } catch {
      setPreview({ kind: "error" })
    }
  }, [adapter, preview, selected])

  if (activeSelection) {
    return (
      <section className="flex h-full min-h-0 flex-col bg-background" aria-label={t("preview")}>
        <div className="flex h-11 shrink-0 items-center gap-1.5 border-b border-border/55 px-2.5">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-8 rounded-md"
            onClick={() => {
              releaseObjectUrl()
              setSelected(null)
              setPreview({ kind: "idle" })
              onSelectedArtifactIdChange?.(null)
            }}
            aria-label={t("back")}
          >
            <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          </Button>
          <span className="min-w-0 flex-1 truncate text-sm font-medium" title={activeSelection.title}>
            {activeSelection.title}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-8 rounded-md"
            onClick={() => void download()}
            aria-label={t("download")}
          >
            <Download aria-hidden="true" className="h-4 w-4" />
          </Button>
        </div>
        <ArtifactPreviewSurface artifact={activeSelection} preview={preview} />
      </section>
    )
  }

  return (
    <section className="flex h-full min-h-0 flex-col bg-background" aria-label={t("label")}>
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-border/55 px-3">
        <span className="text-sm font-medium">{t("title")}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 rounded-md"
          onClick={() => setReloadNonce((value) => value + 1)}
          aria-label={t("refresh")}
        >
          <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {!sessionId && !projectId ? (
          <ArtifactState>{t("noSession")}</ArtifactState>
        ) : status === "loading" ? (
          <ArtifactState loading>{t("loading")}</ArtifactState>
        ) : status === "error" ? (
          <ArtifactState>{t("loadFailed")}</ArtifactState>
        ) : artifacts.length === 0 ? (
          <ArtifactState>{t("empty")}</ArtifactState>
        ) : (
          <div className="space-y-3">
            {artifacts.map((artifact) => {
              const Icon = artifactIcon(artifact)
              const size = artifact.sizeBytes
              const titleId = `artifact-title-${artifact.id}`
              return (
                <article
                  key={artifact.id}
                  aria-labelledby={titleId}
                  className="group flex min-h-[100px] w-full min-w-0 items-center gap-4 rounded-[14px] border border-border/70 bg-transparent px-4 py-3.5 shadow-none transition-colors duration-200 hover:border-border dark:border-white/[0.12] dark:hover:border-white/[0.2]"
                >
                  <span className="flex size-14 shrink-0 items-center justify-center text-muted-foreground/75 transition-colors duration-200 group-hover:text-muted-foreground">
                    <Icon aria-hidden="true" className="size-10 stroke-[1.25]" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span id={titleId} className="block truncate text-sm font-medium leading-5 tracking-[-0.01em] text-foreground">
                      {artifact.title}
                    </span>
                    <span className="mt-1.5 flex min-w-0 items-center gap-1.5 text-xs leading-4 text-muted-foreground">
                      <span className="truncate">{artifact.summary || artifactTypeLabel(artifact)}</span>
                      {typeof size === "number" ? (
                        <>
                          <span aria-hidden="true" className="shrink-0 text-muted-foreground/45">·</span>
                          <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/75">
                            {formatBytes(size, locale)}
                          </span>
                        </>
                      ) : null}
                    </span>
                  </span>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-9 shrink-0 rounded-lg border-0 bg-muted/75 px-4 text-xs shadow-none hover:bg-muted dark:bg-white/[0.06] dark:hover:bg-white/[0.1]"
                    onClick={() => void openArtifact(artifact)}
                    aria-label={`${t("open")} ${artifact.title}`}
                  >
                    {t("open")}
                  </Button>
                </article>
              )
            })}
          </div>
        )}
      </div>
    </section>
  )
}

function ArtifactPreviewSurface({
  artifact,
  preview,
}: {
  artifact: WorkspaceArtifact
  preview: ArtifactPreview
}) {
  const t = useTranslations("workspace.artifacts")
  if (preview.kind === "loading" || preview.kind === "idle") {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center" role="status" aria-label={t("loadingPreview")}>
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground motion-reduce:animate-none" />
      </div>
    )
  }
  if (preview.kind === "error") {
    return <ArtifactState>{t("previewFailed")}</ArtifactState>
  }
  if (preview.kind === "metadata") {
    if (artifact.payload) {
      return <WorkspaceCodePreview content={JSON.stringify(artifact.payload, null, 2)} path={`${artifact.title}.json`} />
    }
    return <ArtifactState>{t("previewUnavailable")}</ArtifactState>
  }

  const { value, url } = preview
  if (value.mediaType.startsWith("image/") && url) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-muted/15 p-4">
        {/* Authenticated Blob URLs cannot use the Next image optimizer. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={url} alt={artifact.title} className="max-h-full max-w-full object-contain" />
      </div>
    )
  }
  if (value.mediaType === "application/pdf" && url) {
    return <iframe src={url} title={artifact.title} className="min-h-0 flex-1 border-0 bg-muted/20" />
  }
  if (value.mediaType === "text/html") {
    return <HtmlArtifactPreview content={value.blob} title={artifact.title} />
  }
  if (isTextMediaType(value.mediaType)) {
    return <TextArtifactPreview content={value.blob} filename={value.filename || artifact.title} mediaType={value.mediaType} />
  }
  return <ArtifactState>{t("previewUnavailable")}</ArtifactState>
}

function HtmlArtifactPreview({ content, title }: { content: Blob; title: string }) {
  const t = useTranslations("workspace.artifacts")
  const [html, setHtml] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    void content.text().then((value) => {
      if (!cancelled) setHtml(value)
    })
    return () => {
      cancelled = true
    }
  }, [content])
  if (html === null) return <ArtifactState loading>{t("loadingPreview")}</ArtifactState>
  return (
    <iframe
      data-testid="artifact-html-preview"
      srcDoc={html}
      title={title}
      sandbox=""
      className="min-h-0 flex-1 border-0 bg-background"
    />
  )
}

function TextArtifactPreview({
  content,
  filename,
  mediaType,
}: {
  content: Blob
  filename: string
  mediaType: string
}) {
  const t = useTranslations("workspace.artifacts")
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    void content.text().then((value) => {
      if (!cancelled) setText(value)
    })
    return () => {
      cancelled = true
    }
  }, [content])
  if (text === null) return <ArtifactState loading>{t("loadingPreview")}</ArtifactState>
  if (isDelimited(filename, mediaType)) return <DelimitedPreview text={text} filename={filename} />
  return <WorkspaceCodePreview content={text} path={filename} />
}

function DelimitedPreview({ text, filename }: { text: string; filename: string }) {
  const delimiter = filename.toLowerCase().endsWith(".tsv") ? "\t" : ","
  const rows = useMemo(() => parseDelimited(text, delimiter).slice(0, 200), [delimiter, text])
  return (
    <div className="min-h-0 flex-1 overflow-auto bg-background">
      <table className="min-w-full border-collapse font-mono text-[11px]">
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className={rowIndex === 0 ? "sticky top-0 z-10 bg-muted/75 font-semibold backdrop-blur" : "odd:bg-muted/15"}>
              <th className="sticky left-0 border-b border-r border-border/45 bg-background px-2 py-1 text-right font-normal text-muted-foreground">
                {rowIndex + 1}
              </th>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="max-w-72 truncate border-b border-r border-border/35 px-2 py-1 text-foreground/85" title={cell}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ArtifactState({ children, loading = false }: { children: React.ReactNode; loading?: boolean }) {
  return (
    <div className="flex min-h-40 flex-1 items-center justify-center gap-2 px-6 text-center text-xs text-muted-foreground">
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" /> : null}
      {children}
    </div>
  )
}

function isDeliverable(artifact: WorkspaceArtifact) {
  return Boolean(artifact.resource) || !NON_DELIVERABLE_TYPES.has(artifact.kind)
}

function artifactIcon(artifact: WorkspaceArtifact) {
  const mediaType = artifact.mediaType ?? ""
  const filename = artifact.title
  if (mediaType.startsWith("image/")) return Box
  if (isDelimited(filename, mediaType) || /spreadsheet|excel/u.test(mediaType)) return FileSpreadsheet
  if (mediaType.includes("json") || filename.endsWith(".json")) return FileJson
  if (mediaType.includes("html") || /\.(html|htm)$/iu.test(filename)) return FileCode
  return FileText
}

function artifactTypeLabel(artifact: WorkspaceArtifact) {
  return artifact.mediaType || artifact.kind.replaceAll("_", " ")
}

function shouldUseObjectUrl(mediaType: string) {
  return mediaType.startsWith("image/") || mediaType === "application/pdf"
}

function isTextMediaType(mediaType: string) {
  return mediaType.startsWith("text/") || /json|xml|yaml|javascript|sql/u.test(mediaType)
}

function isDelimited(filename: string, mediaType: string) {
  return /\.(csv|tsv)$/iu.test(filename) || /csv|tab-separated/u.test(mediaType)
}

function parseDelimited(text: string, delimiter: string) {
  return text.split(/\r?\n/u).filter(Boolean).map((line) => line.split(delimiter))
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function formatBytes(bytes: number, locale: string) {
  if (bytes < 1024) return `${new Intl.NumberFormat(locale).format(bytes)} B`
  const units = ["KB", "MB", "GB"]
  let value = bytes / 1024
  let unit = units[0]
  for (let index = 1; index < units.length && value >= 1024; index += 1) {
    value /= 1024
    unit = units[index]
  }
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)} ${unit}`
}

"use client"

import { useEffect, useRef, useState } from "react"
import { useLocale, useTranslations } from "next-intl"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import {
  fetchAgentArtifactContent,
  getAgentArtifact,
  type AgentArtifact,
  type AgentArtifactContent,
} from "@/lib/agent/client"
import type { ArtifactRefPart } from "@/lib/agent/contracts"
import type { ArtifactTranscriptBlock } from "@/lib/agent/conversation-model/types"
import { AlertCircle, Download, Loader2, RefreshCw } from "@/lib/icons"

const MAX_TEXT_PREVIEW_BYTES = 1024 * 1024
const MAX_IMAGE_PREVIEW_BYTES = 4 * 1024 * 1024
const RASTER_IMAGE_TYPES = new Set([
  "image/avif",
  "image/gif",
  "image/jpeg",
  "image/png",
  "image/webp",
])
const TEXT_APPLICATION_TYPES = new Set([
  "application/javascript",
  "application/json",
  "application/sql",
  "application/xml",
  "application/x-yaml",
  "application/yaml",
])

type ArtifactPreview =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "text"; text: string }
  | { kind: "image"; url: string }
  | { kind: "metadata"; text: string }
  | { kind: "unavailable"; reason: "type" | "size" }
  | { kind: "error" }

type AgentArtifactReferenceProps = {
  part?: ArtifactRefPart
  artifact?: ArtifactTranscriptBlock
}

export function AgentArtifactReference({ part, artifact: block }: AgentArtifactReferenceProps) {
  const locale = useLocale()
  const t = useTranslations("agentHistory")
  const [open, setOpen] = useState(false)
  const [artifact, setArtifact] = useState<AgentArtifact | null>(null)
  const [preview, setPreview] = useState<ArtifactPreview>({ kind: "idle" })
  const [downloading, setDownloading] = useState(false)
  const [downloadFailed, setDownloadFailed] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)
  const requestRef = useRef(0)
  const contentRef = useRef<AgentArtifactContent | null>(null)
  const imageUrlRef = useRef<string | null>(null)
  const artifactId = block?.artifactId ?? part?.artifact_id ?? ""
  const title = block?.title ?? part?.title ?? null
  const mediaType = block?.mediaType ?? part?.media_type ?? null
  const label = title ?? artifactId

  useEffect(
    () => () => {
      controllerRef.current?.abort()
      releaseImageUrl(imageUrlRef)
    },
    [],
  )

  const close = () => {
    requestRef.current += 1
    controllerRef.current?.abort()
    controllerRef.current = null
    releaseImageUrl(imageUrlRef)
    contentRef.current = null
    setArtifact(null)
    setPreview({ kind: "idle" })
    setDownloading(false)
    setDownloadFailed(false)
  }

  const load = async () => {
    const requestId = requestRef.current + 1
    requestRef.current = requestId
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    releaseImageUrl(imageUrlRef)
    contentRef.current = null
    setArtifact(null)
    setPreview({ kind: "loading" })
    setDownloadFailed(false)

    try {
      const detail = await getAgentArtifact(artifactId, {
        signal: controller.signal,
      })
      if (requestRef.current !== requestId) return
      setArtifact(detail)

      const resolvedMediaType = artifactMediaType(detail, mediaType)
      const previewLimit = previewSizeLimit(resolvedMediaType)
      const sizeBytes = artifactSize(detail)
      const hasStoredFile = Boolean(
        detail.resource_ref?.kind === "stored_file" ||
          detail.resource_ref?.filename,
      )

      if (!hasStoredFile) {
        setPreview(
          detail.payload
            ? { kind: "metadata", text: formatJson(detail.payload) }
            : { kind: "unavailable", reason: "type" },
        )
        return
      }
      if (previewLimit === null) {
        setPreview({ kind: "unavailable", reason: "type" })
        return
      }
      if (sizeBytes !== null && sizeBytes > previewLimit) {
        setPreview({ kind: "unavailable", reason: "size" })
        return
      }

      const content = await fetchAgentArtifactContent(artifactId, {
        signal: controller.signal,
      })
      if (requestRef.current !== requestId) return
      contentRef.current = content
      const responseMediaType = content.mediaType || resolvedMediaType
      const responseLimit = previewSizeLimit(responseMediaType)
      if (responseLimit === null) {
        setPreview({ kind: "unavailable", reason: "type" })
        return
      }
      if (content.blob.size > responseLimit) {
        setPreview({ kind: "unavailable", reason: "size" })
        return
      }
      if (RASTER_IMAGE_TYPES.has(responseMediaType)) {
        const url = URL.createObjectURL(content.blob)
        imageUrlRef.current = url
        setPreview({ kind: "image", url })
        return
      }
      setPreview({ kind: "text", text: await content.blob.text() })
    } catch (error) {
      if (isAbortError(error) || requestRef.current !== requestId) return
      setPreview({ kind: "error" })
    }
  }

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (nextOpen) {
      void load()
    } else {
      close()
    }
  }

  const download = async () => {
    if (downloading) return
    setDownloading(true)
    setDownloadFailed(false)
    try {
      const content =
        contentRef.current ??
        (await fetchAgentArtifactContent(artifactId, {
          signal: controllerRef.current?.signal,
        }))
      saveBlob(content.blob, content.filename || artifact?.title || label)
    } catch (error) {
      if (!isAbortError(error)) setDownloadFailed(true)
    } finally {
      setDownloading(false)
    }
  }

  const resourceMediaType = artifact
    ? artifactMediaType(artifact, mediaType)
    : mediaType
  const resourceSize = artifact ? artifactSize(artifact) : null
  if (!artifactId) return null

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <Button
        type="button"
        variant="outline"
        className="h-auto min-h-11 w-full min-w-0 justify-start rounded-[8px] bg-transparent px-2.5 py-2 text-xs hover:bg-muted/35 dark:bg-transparent dark:hover:bg-muted/35"
        onClick={() => handleOpenChange(true)}
        aria-label={t("artifact.open", { name: label })}
        data-artifact-id={artifactId}
        data-testid="agent-artifact-card"
      >
        <Badge variant="outline">{t("reference.artifact")}</Badge>
        <span
          className="min-w-0 flex-1 truncate text-left font-medium text-foreground/80"
          translate="no"
        >
          {label}
        </span>
        {mediaType ? (
          <span
            className="max-w-[42%] truncate font-mono text-[11px] text-muted-foreground"
            translate="no"
          >
            {mediaType}
          </span>
        ) : null}
      </Button>

      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-hidden overscroll-contain p-0 sm:max-w-3xl">
        <DialogHeader className="min-w-0 px-5 pt-5 pr-12 text-left">
          <DialogTitle className="truncate" translate="no">
            {artifact?.title ?? label}
          </DialogTitle>
          <DialogDescription>
            {artifact?.summary ?? t("artifact.description")}
          </DialogDescription>
          {resourceMediaType || resourceSize !== null ? (
            <p className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
              {resourceMediaType ? (
                <span translate="no">{resourceMediaType}</span>
              ) : null}
              {resourceSize !== null ? (
                <span>{formatBytes(resourceSize, locale)}</span>
              ) : null}
            </p>
          ) : null}
        </DialogHeader>

        <div className="min-h-64 overflow-auto bg-muted/25 px-5 py-4">
          <ArtifactPreviewContent
            preview={preview}
            label={artifact?.title ?? label}
            load={load}
            t={t}
          />
        </div>

        <DialogFooter className="items-center px-5 pb-5">
          {downloadFailed ? (
            <p role="alert" className="mr-auto text-sm text-destructive">
              {t("artifact.downloadFailed")}
            </p>
          ) : null}
          <Button
            type="button"
            onClick={() => void download()}
            disabled={downloading || preview.kind === "loading"}
          >
            {downloading ? (
              <Loader2
                data-icon="inline-start"
                aria-hidden="true"
                className="animate-spin motion-reduce:animate-none"
              />
            ) : (
              <Download data-icon="inline-start" aria-hidden="true" />
            )}
            {downloading ? t("artifact.downloading") : t("artifact.download")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ArtifactPreviewContent({
  preview,
  label,
  load,
  t,
}: {
  preview: ArtifactPreview
  label: string
  load: () => Promise<void>
  t: ReturnType<typeof useTranslations<"agentHistory">>
}) {
  if (preview.kind === "loading" || preview.kind === "idle") {
    return (
      <div
        className="grid gap-3"
        role="status"
        aria-live="polite"
        aria-label={t("artifact.loading")}
      >
        <Skeleton className="h-4 w-2/5" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-4/5" />
      </div>
    )
  }
  if (preview.kind === "error") {
    return (
      <Alert variant="destructive">
        <AlertCircle aria-hidden="true" />
        <AlertDescription className="flex flex-col items-start gap-3">
          <span>{t("artifact.loadFailed")}</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="dark:bg-transparent dark:hover:bg-muted/35"
            onClick={() => void load()}
          >
            <RefreshCw data-icon="inline-start" aria-hidden="true" />
            {t("artifact.retry")}
          </Button>
        </AlertDescription>
      </Alert>
    )
  }
  if (preview.kind === "unavailable") {
    return (
      <p className="text-sm leading-6 text-muted-foreground">
        {preview.reason === "size"
          ? t("artifact.previewTooLarge")
          : t("artifact.previewUnavailable")}
      </p>
    )
  }
  if (preview.kind === "image") {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- authenticated Blob URL, not an optimizable remote asset
      <img
        src={preview.url}
        alt={label}
        width={1600}
        height={1200}
        className="mx-auto h-auto max-h-[calc(100dvh-16rem)] max-w-full object-contain"
      />
    )
  }
  return (
    <pre className="min-w-0 whitespace-pre-wrap break-words font-mono text-xs leading-5 text-foreground/85">
      {preview.text}
    </pre>
  )
}

function artifactMediaType(artifact: AgentArtifact, fallback: string | null) {
  return String(artifact.resource_ref?.mime_type ?? fallback ?? "")
    .split(";", 1)[0]
    .trim()
    .toLowerCase()
}

function artifactSize(artifact: AgentArtifact) {
  const value = artifact.resource_ref?.size_bytes
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null
}

function previewSizeLimit(mediaType: string) {
  if (RASTER_IMAGE_TYPES.has(mediaType)) return MAX_IMAGE_PREVIEW_BYTES
  if (mediaType.startsWith("text/") || TEXT_APPLICATION_TYPES.has(mediaType)) {
    return MAX_TEXT_PREVIEW_BYTES
  }
  return null
}

function releaseImageUrl(ref: { current: string | null }) {
  if (!ref.current) return
  URL.revokeObjectURL(ref.current)
  ref.current = null
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.rel = "noopener"
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function formatJson(value: Record<string, unknown>) {
  return JSON.stringify(value, null, 2)
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

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError"
}

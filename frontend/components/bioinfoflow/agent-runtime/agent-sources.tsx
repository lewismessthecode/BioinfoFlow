"use client"

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react"
import { ExternalLink, FileText, Github, Globe2, Search } from "@/lib/icons"
import { useTranslations } from "next-intl"

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import type { AgentRuntimeSource } from "@/lib/agent-runtime"
import { sanitizeSourceHref } from "@/lib/agent-runtime/sources"
import { cn } from "@/lib/utils"

type SourceCitationProps = {
  source: AgentRuntimeSource
  index: number
  children: ReactNode
  onOpen: (sourceId: string) => void
}

export function SourceCitation({
  source,
  index,
  children,
  onOpen,
}: SourceCitationProps) {
  const t = useTranslations("agentRuntime")
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewPosition, setPreviewPosition] = useState<{
    left: number
    top: number
    width: number
  } | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const tooltipId = useId()
  const updatePreviewPosition = useCallback(() => {
    const trigger = buttonRef.current
    if (!trigger) return
    const rect = trigger.getBoundingClientRect()
    const width = Math.min(320, window.innerWidth - 32)
    const left = Math.min(
      window.innerWidth - width / 2 - 16,
      Math.max(width / 2 + 16, rect.left + rect.width / 2),
    )
    setPreviewPosition({
      left,
      top: rect.bottom + 8,
      width,
    })
  }, [])

  const openPreview = useCallback(() => {
    updatePreviewPosition()
    setPreviewOpen(true)
  }, [updatePreviewPosition])

  useEffect(() => {
    if (!previewOpen) return
    updatePreviewPosition()
    window.addEventListener("resize", updatePreviewPosition)
    window.addEventListener("scroll", updatePreviewPosition, true)
    return () => {
      window.removeEventListener("resize", updatePreviewPosition)
      window.removeEventListener("scroll", updatePreviewPosition, true)
    }
  }, [previewOpen, updatePreviewPosition])

  return (
    <span
      className="relative inline-flex align-baseline"
      onMouseEnter={openPreview}
      onMouseLeave={() => setPreviewOpen(false)}
      onFocus={openPreview}
      onBlur={() => setPreviewOpen(false)}
    >
      <button
        ref={buttonRef}
        type="button"
        className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-md border border-border/70 bg-muted/30 px-1.5 text-[11px] font-semibold leading-none text-foreground/75 shadow-none transition-colors hover:bg-muted/50 hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={t("sources.citationLabel", {
          index: index + 1,
          title: source.title,
        })}
        aria-describedby={previewOpen ? tooltipId : undefined}
        onKeyDown={(event) => {
          if (event.key === "Escape") setPreviewOpen(false)
        }}
        onClick={() => onOpen(source.id)}
      >
        {children}
      </button>
      {previewOpen ? (
        <SourcePreview
          id={tooltipId}
          source={source}
          className="fixed z-30 -translate-x-1/2"
          heading={t("sources.preview")}
          style={previewPosition ?? undefined}
        />
      ) : null}
    </span>
  )
}

export function SourceEvidenceFooter({
  sources,
  onOpen,
}: {
  sources: AgentRuntimeSource[]
  onOpen: () => void
}) {
  const t = useTranslations("agentRuntime")
  if (!sources.length) return null

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <button
        type="button"
        className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border/70 bg-background px-2.5 font-medium text-foreground/82 shadow-none transition-colors hover:bg-muted/50 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={t("sources.openWithCount", { count: sources.length })}
        onClick={onOpen}
      >
        <SourceIcon sourceType={sources[0]?.sourceType} className="h-3.5 w-3.5" />
        <span>{t("sources.count", { count: sources.length })}</span>
      </button>
      <div className="hidden min-w-0 flex-wrap items-center gap-1.5 sm:flex">
        {sources.slice(0, 5).map((source) => (
          <span
            key={source.id}
            className="inline-flex h-7 min-w-0 max-w-36 items-center gap-1 rounded-md border border-border/50 bg-background px-2 text-muted-foreground"
            title={source.url}
          >
            <SourceIcon sourceType={source.sourceType} className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{source.domain}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

export function SourcesDrawer({
  open,
  sources,
  highlightedSourceId,
  onOpenChange,
}: {
  open: boolean
  sources: AgentRuntimeSource[]
  highlightedSourceId?: string | null
  onOpenChange: (open: boolean) => void
}) {
  const t = useTranslations("agentRuntime")
  const groups = useMemo(() => groupSourcesByQuery(sources), [sources])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full gap-0 overflow-hidden p-0 sm:max-w-md"
        aria-label={t("sources.title")}
        closeLabel={t("sources.close")}
      >
        <SheetHeader className="border-b border-border/60 px-5 py-4">
          <SheetTitle className="text-lg">{t("sources.title")}</SheetTitle>
          <SheetDescription className="sr-only">
            {t("sources.description")}
          </SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {groups.map((group) => (
            <section key={group.key} className="mb-6 last:mb-0">
              <div className="mb-3 flex items-start gap-2">
                <Search className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-foreground">
                    {t("sources.searchedWeb")}
                  </div>
                  <div className="mt-1 break-words font-mono text-sm text-foreground/82">
                    {group.query}
                  </div>
                </div>
                <span className="shrink-0 rounded-md border border-border/60 px-2 py-0.5 text-xs text-muted-foreground">
                  {t("sources.resultCount", {
                    count: group.resultCount ?? group.sources.length,
                  })}
                </span>
              </div>

              <div className="grid gap-2">
                {group.sources.map((source) => (
                  <SourceDrawerLink
                    key={source.id}
                    source={source}
                    highlighted={highlightedSourceId === source.id}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function SourcePreview({
  id,
  source,
  heading,
  className,
  style,
}: {
  id: string
  source: AgentRuntimeSource
  heading: string
  className?: string
  style?: CSSProperties
}) {
  const t = useTranslations("agentRuntime")
  return (
    <span
      id={id}
      className={cn(
        "block rounded-lg border border-border/70 bg-popover p-3 text-left text-popover-foreground shadow-[0_8px_24px_rgba(0,0,0,0.05)]",
        className,
      )}
      style={style}
      role="tooltip"
    >
      <span className="mb-2 block text-[11px] font-medium uppercase text-muted-foreground">
        {heading}
      </span>
      <span className="block text-sm font-semibold leading-5 text-foreground">
        {source.title}
      </span>
      <span className="mt-1 flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
        <SourceIcon sourceType={source.sourceType} className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">{source.domain}</span>
        <span className="rounded bg-muted px-1.5 py-0.5">
          {sourceTypeLabel(t, source.sourceType)}
        </span>
      </span>
      <span className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">
        {source.snippet || t("sources.noSnippet")}
      </span>
    </span>
  )
}

function SourceDrawerLink({
  source,
  highlighted,
}: {
  source: AgentRuntimeSource
  highlighted: boolean
}) {
  const t = useTranslations("agentRuntime")
  const ref = useRef<HTMLElement>(null)
  const href = sanitizeSourceHref(source.url)
  const setRef = useCallback((node: HTMLAnchorElement | HTMLDivElement | null) => {
    ref.current = node
  }, [])

  useEffect(() => {
    if (!highlighted) return
    ref.current?.scrollIntoView({ block: "center" })
  }, [highlighted])

  const content = (
    <>
      <span className="flex min-w-0 items-center gap-2">
        <SourceIcon sourceType={source.sourceType} className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate font-medium text-foreground">
          {source.title}
        </span>
        {href ? (
          <ExternalLink
            aria-hidden="true"
            className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
          />
        ) : null}
      </span>
      <span className="truncate text-xs text-muted-foreground">
        {source.domain}
        {href ? <span className="sr-only"> {t("sources.opensInNewTab")}</span> : null}
      </span>
      <span className="line-clamp-2 text-xs leading-5 text-muted-foreground">
        {source.snippet || t("sources.noSnippet")}
      </span>
    </>
  )

  const className = cn(
    "grid gap-1 rounded-lg border border-border/60 bg-background px-3 py-2.5 text-sm shadow-none transition-colors",
    href
      ? "hover:bg-muted/30 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
      : "cursor-default",
    highlighted && "border-border bg-muted/45",
  )

  if (!href) {
    return (
      <div ref={setRef} className={className}>
        {content}
      </div>
    )
  }

  return (
    <a
      ref={setRef}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
    >
      {content}
    </a>
  )
}

function SourceIcon({
  sourceType,
  className,
}: {
  sourceType?: string | null
  className?: string
}) {
  if (sourceType === "github") return <Github className={className} />
  if (sourceType === "docs" || sourceType === "workflow" || sourceType === "artifact") {
    return <FileText className={className} />
  }
  return <Globe2 className={className} />
}

function sourceTypeLabel(t: (key: string) => string, sourceType: string) {
  const knownTypes = new Set([
    "web",
    "pubmed",
    "ncbi",
    "biorxiv",
    "github",
    "docs",
    "workflow",
    "artifact",
  ])
  return knownTypes.has(sourceType) ? t(`sources.types.${sourceType}`) : sourceType
}

function groupSourcesByQuery(sources: AgentRuntimeSource[]) {
  const groups = new Map<
    string,
    { key: string; query: string; resultCount: number | null; sources: AgentRuntimeSource[] }
  >()
  for (const source of sources) {
    const query = source.query || source.domain || source.url
    const key = `${source.toolRunId ?? "source"}:${query}`
    const group = groups.get(key) ?? {
      key,
      query,
      resultCount: source.resultCount ?? null,
      sources: [],
    }
    group.resultCount = source.resultCount ?? group.resultCount
    group.sources.push(source)
    groups.set(key, group)
  }
  return [...groups.values()]
}

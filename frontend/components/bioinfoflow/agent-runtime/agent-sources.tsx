"use client"

import { useMemo, useState, type ReactNode } from "react"
import { ExternalLink, FileText, Github, Globe2, Search } from "lucide-react"
import { useTranslations } from "next-intl"

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import type { AgentRuntimeSource } from "@/lib/agent-runtime"
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

  return (
    <span
      className="relative inline-flex align-baseline"
      onMouseEnter={() => setPreviewOpen(true)}
      onMouseLeave={() => setPreviewOpen(false)}
      onFocus={() => setPreviewOpen(true)}
      onBlur={() => setPreviewOpen(false)}
    >
      <button
        type="button"
        className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-md border border-primary/25 bg-primary/8 px-1.5 text-[11px] font-semibold leading-none text-primary shadow-none transition-colors hover:border-primary/45 hover:bg-primary/12 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={`Source ${index + 1}: ${source.title}`}
        onClick={() => onOpen(source.id)}
      >
        {children}
      </button>
      {previewOpen ? (
        <SourcePreview
          source={source}
          className="absolute left-0 top-6 z-30 w-80"
          heading={t("sources.preview")}
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
        className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border/70 bg-background px-2.5 font-medium text-foreground/82 shadow-sm transition-colors hover:bg-muted/50 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={t("sources.open")}
        onClick={onOpen}
      >
        <SourceIcon sourceType={sources[0]?.sourceType} className="h-3.5 w-3.5" />
        <span>{t("sources.count", { count: sources.length })}</span>
      </button>
      <div className="hidden min-w-0 flex-wrap items-center gap-1.5 sm:flex">
        {sources.slice(0, 5).map((source) => (
          <span
            key={source.id}
            className="inline-flex h-7 min-w-0 max-w-36 items-center gap-1 rounded-md border border-border/50 bg-muted/25 px-2 text-muted-foreground"
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
                  <a
                    key={source.id}
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={cn(
                      "grid gap-1 rounded-lg border border-border/60 bg-background px-3 py-2.5 text-sm shadow-sm transition-colors hover:bg-muted/30 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
                      highlightedSourceId === source.id && "border-primary/45 bg-primary/5",
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <SourceIcon sourceType={source.sourceType} className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate font-medium text-foreground">
                        {source.title}
                      </span>
                      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {source.domain}
                    </span>
                    <span className="line-clamp-2 text-xs leading-5 text-muted-foreground">
                      {source.snippet || t("sources.noSnippet")}
                    </span>
                  </a>
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
  source,
  heading,
  className,
}: {
  source: AgentRuntimeSource
  heading: string
  className?: string
}) {
  const t = useTranslations("agentRuntime")
  return (
    <span
      className={cn(
        "block rounded-lg border border-border/70 bg-popover p-3 text-left text-popover-foreground shadow-lg",
        className,
      )}
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
  return t(`sources.types.${sourceType}`)
}

function groupSourcesByQuery(sources: AgentRuntimeSource[]) {
  const groups = new Map<
    string,
    { key: string; query: string; resultCount: number | null; sources: AgentRuntimeSource[] }
  >()
  for (const source of sources) {
    const query = source.query || source.domain || source.url
    const key = query
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

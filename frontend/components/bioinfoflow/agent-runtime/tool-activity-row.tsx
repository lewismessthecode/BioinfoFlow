"use client"

import { useId, useState } from "react"
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  ExternalLink,
  Globe2,
  Loader2,
  TerminalSquare,
} from "@/lib/icons"
import { useTranslations } from "next-intl"

import type { AgentRuntimeToolActivity } from "@/lib/agent-runtime"
import { sanitizeSourceHref } from "@/lib/agent-runtime/sources"
import { cn } from "@/lib/utils"

export function ToolActivityRow({ activity }: { activity: AgentRuntimeToolActivity }) {
  const t = useTranslations("agentRuntime")
  const [expanded, setExpanded] = useState(false)
  const detailsId = useId()
  const hasDetails = Boolean(
    activity.arguments ||
      activity.inputPreview ||
      activity.outputPreview ||
      activity.errorMessage ||
      activity.sources.length ||
      activity.exitCode !== undefined ||
      activity.relatedFiles.length,
  )

  return (
    <div
      className="grid gap-1 text-xs text-muted-foreground"
      data-testid="agent-tool-activity-row"
    >
      <div className="group/row flex min-w-0 items-center gap-1.5">
        <ActivityStatusIcon status={activity.status} />
        <span className="min-w-0 truncate rounded-md bg-muted/45 px-1.5 py-0.5 font-mono text-[11px] text-foreground/65">
          {activity.name}
        </span>
        {activity.summary || activity.inputPreview ? (
          <span className="hidden min-w-0 flex-1 truncate text-muted-foreground sm:block">
            {activity.summary || activity.inputPreview}
          </span>
        ) : null}
        {activity.status !== "completed" ? (
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {t(`activity.status.${activity.status}`)}
          </span>
        ) : null}
        {hasDetails ? (
          <button
            type="button"
            className={cn(
              "ml-auto inline-flex shrink-0 items-center rounded-md p-0.5 text-muted-foreground opacity-0 transition-[background-color,color,opacity] hover:bg-muted/50 hover:text-foreground focus-visible:opacity-100 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring group-hover/row:opacity-100 group-focus-within/row:opacity-100",
              expanded && "opacity-100",
            )}
            onClick={() => setExpanded((current) => !current)}
            aria-expanded={expanded}
            aria-controls={detailsId}
            aria-label={expanded ? t("activity.details.hide") : t("activity.details.show")}
          >
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </button>
        ) : null}
      </div>

      {activity.summary || activity.inputPreview ? (
        <p className="truncate text-muted-foreground sm:hidden">
          {activity.summary || activity.inputPreview}
        </p>
      ) : null}

      {hasDetails && expanded ? (
        <div id={detailsId} className="grid gap-1.5 text-muted-foreground">
          {activity.inputPreview ? <Detail label={t("activity.details.input")} value={activity.inputPreview} /> : null}
          {activity.sourceQuery ? <Detail label={t("sources.query")} value={activity.sourceQuery} /> : null}
          {activity.sources.length ? (
            <div className="grid gap-1">
              <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                {t("sources.title")}
              </div>
              <div className="grid gap-1.5">
                {activity.sources.map((source) => (
                  <SourceActivityLink
                    key={source.id}
                    source={source}
                    opensInNewTabLabel={t("sources.opensInNewTab")}
                  />
                ))}
              </div>
            </div>
          ) : null}
          {activity.arguments ? (
            <Detail
              label={t("activity.details.arguments")}
              value={JSON.stringify(activity.arguments, null, 2)}
              pre
            />
          ) : null}
          {activity.outputPreview ? <Detail label={t("activity.details.output")} value={activity.outputPreview} pre /> : null}
          {activity.exitCode !== undefined && activity.exitCode !== null ? (
            <Detail label={t("activity.details.exitCode")} value={String(activity.exitCode)} />
          ) : null}
          {activity.errorMessage ? <Detail label={t("activity.details.error")} value={activity.errorMessage} /> : null}
          {activity.relatedFiles.length ? (
            <Detail
              label={t("activity.details.files")}
              value={activity.relatedFiles.join("\n")}
              pre
            />
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function SourceActivityLink({
  source,
  opensInNewTabLabel,
}: {
  source: AgentRuntimeToolActivity["sources"][number]
  opensInNewTabLabel: string
}) {
  const href = sanitizeSourceHref(source.url)
  const className = cn(
    "flex min-w-0 items-center gap-2 rounded-md bg-muted/25 px-2 py-1.5 text-[11px] leading-5 text-foreground/75 transition-colors",
    href
      ? "hover:bg-muted/45 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
      : "cursor-default",
  )
  const content = (
    <>
      <Globe2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="min-w-0 flex-1 truncate">{source.title}</span>
      {href ? <span className="sr-only">{opensInNewTabLabel}</span> : null}
      <span className="hidden shrink-0 text-muted-foreground sm:inline">
        {source.domain}
      </span>
      {href ? (
        <ExternalLink
          aria-hidden="true"
          className="h-3 w-3 shrink-0 text-muted-foreground"
        />
      ) : null}
    </>
  )

  if (!href) {
    return <div className={className}>{content}</div>
  }

  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
      {content}
    </a>
  )
}

function Detail({ label, value, pre = false }: { label: string; value: string; pre?: boolean }) {
  return (
    <div className="grid gap-1">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      {pre ? (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-muted/25 px-2 py-1.5 text-[11px] leading-5 text-foreground/75">
          {value}
        </pre>
      ) : (
        <div className="break-words rounded-md bg-muted/25 px-2 py-1.5 text-[11px] leading-5 text-foreground/75">
          {value}
        </div>
      )}
    </div>
  )
}

function ActivityStatusIcon({ status }: { status: AgentRuntimeToolActivity["status"] }) {
  if (status === "failed" || status === "cancelled" || status === "rejected") {
    return <TerminalSquare className="h-3.5 w-3.5 text-muted-foreground/75" />
  }
  if (status === "completed") {
    return <CheckCircle2 className="h-3.5 w-3.5 text-muted-foreground/70" />
  }
  if (status === "running" || status === "building") {
    return <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
  }
  return <Clock3 className={cn("h-3.5 w-3.5 text-muted-foreground")} />
}

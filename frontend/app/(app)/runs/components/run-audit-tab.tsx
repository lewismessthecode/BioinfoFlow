"use client"

import { useEffect, useState } from "react"
import { useTranslations } from "next-intl"
import { ChevronRight, Info, ScrollText } from "@/lib/icons"
import { toast } from "sonner"
import { apiRequest, ApiError } from "@/lib/api"
import { formatDateTime } from "@/lib/format-utils"
import { cn } from "@/lib/utils"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/ui/empty-state"
import {
  auditAccentClass,
  auditActionConfig,
  auditActionIcon,
  DEFAULT_AUDIT_CONFIG,
} from "@/constants/audit-config"
import type { AuditLogEntry } from "@/lib/types"

interface RunAuditTabProps {
  runId: string
}

const SHORT_VALUE_MAX = 48

function startCase(value: string): string {
  return value
    .replace(/[_.-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function isShortValue(value: unknown): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === "string") return value.length <= SHORT_VALUE_MAX
  if (typeof value === "number" || typeof value === "boolean") return true
  return false
}

function formatScalar(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "string") return value
  return JSON.stringify(value)
}

export function RunAuditTab({ runId }: RunAuditTabProps) {
  const t = useTranslations("runs.detail.audit")
  const [entries, setEntries] = useState<AuditLogEntry[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [openIds, setOpenIds] = useState<Record<string, boolean>>({})

  useEffect(() => {
    const controller = new AbortController()

    const load = async () => {
      setIsLoading(true)
      try {
        const { data } = await apiRequest<AuditLogEntry[]>(
          `/runs/${runId}/audit`,
          { signal: controller.signal },
        )
        setEntries(data)
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return
        }
        const message =
          error instanceof ApiError ? error.message : t("errors.loadFailed")
        toast.error(message)
      } finally {
        setIsLoading(false)
      }
    }

    load()
    return () => controller.abort()
  }, [runId, t])

  if (isLoading) {
    return (
      <div className="p-4 space-y-4">
        <Skeleton className="h-8 w-2/3" />
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-start gap-3">
            <Skeleton className="h-7 w-7 rounded-full shrink-0" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <EmptyState
        icon={ScrollText}
        title={t("empty")}
        description={t("emptyDescription")}
        className="py-12"
      />
    )
  }

  return (
    <div className="p-4 space-y-4">
      {/* Intro strip */}
      <div className="flex items-start gap-2 rounded-md border border-border/50 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
        <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" aria-hidden />
        <p>{t("intro")}</p>
      </div>

      {/* Timeline */}
      <ol className="relative border-l border-border/60 pl-5 space-y-1">
        {entries.map((entry) => {
          const config = auditActionConfig[entry.action] ?? DEFAULT_AUDIT_CONFIG
          const Icon = auditActionIcon(entry.action)
          const accent = auditAccentClass(config.variant)
          const friendlyLabel =
            config === DEFAULT_AUDIT_CONFIG
              ? startCase(entry.action.replace(/^run\./, ""))
              : t(`actions.${config.labelKey}`)
          const detailEntries = entry.details
            ? Object.entries(entry.details)
            : []
          const hasDetails = detailEntries.length > 0
          const isOpen = openIds[entry.id] ?? false
          const actor = entry.actor || t("system")

          return (
            <li key={entry.id} className="relative py-3 first:pt-1 last:pb-1">
              {/* Icon node sitting on the timeline */}
              <span
                className={cn(
                  "absolute -left-[30px] top-3 flex h-6 w-6 items-center justify-center rounded-full border",
                  accent,
                )}
                aria-hidden
              >
                <Icon className="h-3 w-3" />
              </span>

              <div className="flex flex-col gap-1">
                <p className="text-sm font-medium text-foreground">
                  {friendlyLabel}
                </p>
                <p className="text-xs text-muted-foreground">
                  <span>{t("by", { actor })}</span>
                  <span className="mx-1.5 text-border">·</span>
                  <time dateTime={entry.created_at}>
                    {formatDateTime(entry.created_at)}
                  </time>
                </p>

                {hasDetails && (
                  <div className="mt-1.5">
                    <button
                      type="button"
                      onClick={() =>
                        setOpenIds((prev) => ({
                          ...prev,
                          [entry.id]: !isOpen,
                        }))
                      }
                      aria-expanded={isOpen}
                      className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <ChevronRight
                        className={cn(
                          "h-3 w-3 transition-transform",
                          isOpen && "rotate-90",
                        )}
                        aria-hidden
                      />
                      <span>
                        {isOpen ? t("hideDetails") : t("showDetails")}
                      </span>
                    </button>

                    {isOpen && (
                      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 rounded-md border border-border/50 bg-muted/20 px-3 py-2 text-xs">
                        {detailEntries.map(([key, value]) => {
                          const short = isShortValue(value)
                          return (
                            <div
                              key={key}
                              className="contents"
                            >
                              <dt className="text-muted-foreground font-mono">
                                {key}
                              </dt>
                              <dd className="min-w-0">
                                {short ? (
                                  <span className="inline-flex items-center rounded border border-border/60 bg-background/60 px-1.5 py-0.5 font-mono text-foreground/90">
                                    {formatScalar(value)}
                                  </span>
                                ) : (
                                  <pre className="overflow-x-auto rounded border border-border/60 bg-background/60 p-2 font-mono text-foreground/90 whitespace-pre-wrap break-all">
                                    {typeof value === "string"
                                      ? value
                                      : JSON.stringify(value, null, 2)}
                                  </pre>
                                )}
                              </dd>
                            </div>
                          )
                        })}
                      </dl>
                    )}
                  </div>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

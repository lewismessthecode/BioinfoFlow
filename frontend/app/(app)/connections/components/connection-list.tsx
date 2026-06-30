"use client"

import { Clock3, Pencil, Search, Server } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { RemoteConnection, RemoteConnectionStatus } from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

import { StatusDot, statusBorderClassNames } from "./connection-ui"

export type ConnectionStatusFilter = "all" | RemoteConnectionStatus

type ConnectionListProps = {
  connections: RemoteConnection[]
  filteredConnections: RemoteConnection[]
  selectedConnection: RemoteConnection | null
  search: string
  statusFilter: ConnectionStatusFilter
  isLoading: boolean
  loadError: boolean
  onSearchChange: (value: string) => void
  onStatusFilterChange: (filter: ConnectionStatusFilter) => void
  onSelectConnection: (id: string) => void
  onEdit: (connection: RemoteConnection) => void
}

const statusFilters: ConnectionStatusFilter[] = ["all", "online", "error", "offline", "unknown"]

export function ConnectionList({
  connections,
  filteredConnections,
  selectedConnection,
  search,
  statusFilter,
  isLoading,
  loadError,
  onSearchChange,
  onStatusFilterChange,
  onSelectConnection,
  onEdit,
}: ConnectionListProps) {
  const t = useTranslations("connections")

  const onlineCount = connections.filter((connection) => connection.status === "online").length
  const attentionCount = connections.filter((connection) => connection.status === "error" || connection.status === "offline").length
  const agentOrConfigCount = connections.filter((connection) => connection.auth_method !== "key_file").length

  return (
    <section className="flex min-h-0 flex-col overflow-hidden">
      <div className="mb-4 shrink-0">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="relative min-w-0 flex-1 xl:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="connection-search"
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder={t("searchPlaceholder")}
              className="pl-9"
            />
            <Label htmlFor="connection-search" className="sr-only">
              {t("searchPlaceholder")}
            </Label>
          </div>

          <div className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
            <SummaryPill value={connections.length} label={t("summary.total")} />
            <SummaryPill value={onlineCount} label={t("summary.online")} tone="online" />
            <SummaryPill value={attentionCount} label={t("summary.attention")} tone="attention" />
            <SummaryPill value={agentOrConfigCount} label={t("summary.runtimeManaged")} />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5" aria-label={t("filters.label")}>
          {statusFilters.map((filter) => (
            <button
              key={filter}
              type="button"
              onClick={() => onStatusFilterChange(filter)}
              aria-pressed={statusFilter === filter}
              className={cn(
                "inline-flex h-8 items-center gap-2 rounded-full px-2.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground",
                statusFilter === filter && "bg-muted text-foreground ring-1 ring-border/60",
              )}
            >
              {filter === "all" ? <span className="h-1.5 w-1.5 rounded-full bg-foreground" /> : <StatusDot status={filter} className="h-1.5 w-1.5 shadow-none" />}
              {t(`filters.${filter}`)}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto [scrollbar-gutter:stable]">
        {isLoading ? (
          <CommandState title={t("list.loading")} />
        ) : loadError ? (
          <CommandState title={t("list.error")} tone="warning" />
        ) : filteredConnections.length > 0 ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-3">
            {filteredConnections.map((connection) => {
              const selected = selectedConnection ? connection.id === selectedConnection.id : false

              return (
                <article
                  key={connection.id}
                  className={cn(
                    "group relative min-h-[96px] rounded-2xl border bg-background px-3 py-3 transition-colors hover:bg-muted/35",
                    selected
                      ? "border-primary/50 bg-primary/[0.04] ring-1 ring-primary/25"
                      : "border-border/60",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelectConnection(connection.id)}
                    aria-current={selected ? "true" : undefined}
                    className="grid h-full w-full grid-cols-[40px_minmax(0,1fr)_auto] items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border/60 bg-background text-foreground", selected && "border-primary/30 bg-primary/10 text-primary")}>
                      <Server className="h-4 w-4" />
                    </div>

                    <div className="min-w-0">
                      <div className="flex min-w-0 items-center gap-2">
                        <h2 className="truncate text-sm font-semibold tracking-tight text-foreground">{connection.name}</h2>
                        <StatusDot status={connection.status} className="h-1.5 w-1.5 shrink-0 shadow-none sm:hidden" />
                      </div>
                      <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
                        {connection.username}@{connection.host}:{connection.port}
                      </p>
                      <div className="mt-1 flex min-w-0 items-center gap-1.5 text-[11px] leading-none text-muted-foreground">
                        <span className="truncate">{t(`auth.${connection.auth_method}`)}</span>
                        {connection.ssh_alias ? (
                          <>
                            <span className="text-border">/</span>
                            <span className="truncate font-mono">{connection.ssh_alias}</span>
                          </>
                        ) : null}
                        {connection.last_checked_at ? (
                          <>
                            <span className="text-border">/</span>
                            <span className="inline-flex shrink-0 items-center gap-1">
                              <Clock3 className="h-3 w-3" />
                              {formatCheckedAt(connection.last_checked_at)}
                            </span>
                          </>
                        ) : null}
                      </div>
                    </div>

                    <span
                      className={cn(
                        "hidden h-6 shrink-0 items-center gap-1.5 rounded-full border px-2 text-[11px] font-medium transition-opacity group-hover:opacity-0 group-focus-within:opacity-0 sm:inline-flex",
                        statusBorderClassNames[connection.status],
                      )}
                    >
                      <StatusDot status={connection.status} className="h-1.5 w-1.5 shadow-none" />
                      {t(`status.${connection.status}`)}
                    </span>
                  </button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="icon"
                    aria-label={`${t("actions.editConnection")}: ${connection.name}`}
                    className="absolute right-3 top-1/2 z-10 h-9 w-9 -translate-y-1/2 rounded-xl opacity-0 shadow-sm shadow-foreground/10 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                    onClick={() => onEdit(connection)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                </article>
              )
            })}
          </div>
        ) : (
          <CommandState
            title={connections.length === 0 ? t("list.empty") : t("list.noResults")}
            actionLabel={connections.length === 0 ? undefined : t("actions.clearFilters")}
            onAction={connections.length === 0 ? undefined : () => {
              onSearchChange("")
              onStatusFilterChange("all")
            }}
          />
        )}
      </div>
    </section>
  )
}

function SummaryPill({
  value,
  label,
  tone = "default",
}: {
  value: number
  label: string
  tone?: "default" | "online" | "attention"
}) {
  return (
    <span
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-full border border-border/50 bg-muted/30 px-2.5 font-medium",
        tone === "online" && "border-emerald-500/20 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300",
        tone === "attention" && "border-amber-500/20 bg-amber-500/5 text-amber-700 dark:text-amber-300",
      )}
    >
      <strong className="font-mono text-sm font-semibold text-foreground">{value}</strong>
      {label}
    </span>
  )
}

function CommandState({
  title,
  actionLabel,
  onAction,
  tone = "default",
}: {
  title: string
  actionLabel?: string
  onAction?: () => void
  tone?: "default" | "warning"
}) {
  return (
    <div
      className={cn(
        "flex min-h-[220px] flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-background/45 px-6 py-10 text-center text-sm leading-6 text-muted-foreground",
        tone === "warning" && "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
      )}
    >
      <p>{title}</p>
      {actionLabel && onAction ? (
        <Button type="button" variant="outline" className="mt-4" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </div>
  )
}

function formatCheckedAt(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

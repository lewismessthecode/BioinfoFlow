"use client"

import { Clock3, Pencil, Play, RefreshCw, Search, Server, Trash2 } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
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
  testingConnectionId: string | null
  probeConnectionId: string | null
  onSearchChange: (value: string) => void
  onStatusFilterChange: (filter: ConnectionStatusFilter) => void
  onSelectConnection: (id: string) => void
  onEdit: (connection: RemoteConnection) => void
  onTest: (connection: RemoteConnection) => void
  onRunProbe: (connection: RemoteConnection) => void
  onDelete: (connection: RemoteConnection) => void
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
  testingConnectionId,
  probeConnectionId,
  onSearchChange,
  onStatusFilterChange,
  onSelectConnection,
  onEdit,
  onTest,
  onRunProbe,
  onDelete,
}: ConnectionListProps) {
  const t = useTranslations("connections")

  const onlineCount = connections.filter((connection) => connection.status === "online").length
  const attentionCount = connections.filter((connection) => connection.status === "error" || connection.status === "offline").length
  const agentOrConfigCount = connections.filter((connection) => connection.auth_method !== "key_file").length

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background/30">
      <div className="shrink-0 border-b border-border/60 bg-background/55 p-3 sm:p-4">
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
          <div className="relative min-w-0">
            <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label={t("searchPlaceholder")}
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder={t("searchPlaceholder")}
              className="h-11 rounded-2xl border-border/70 bg-background/85 pl-10 pr-4 text-sm shadow-sm shadow-foreground/5"
            />
          </div>

          <div className="flex flex-wrap gap-1.5 text-xs">
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
                "inline-flex h-8 items-center gap-2 rounded-full px-2.5 text-xs font-medium text-muted-foreground transition hover:bg-background/70 hover:text-foreground",
                statusFilter === filter && "bg-background text-foreground shadow-sm shadow-foreground/5 ring-1 ring-border/70",
              )}
            >
              {filter === "all" ? <span className="h-1.5 w-1.5 rounded-full bg-foreground" /> : <StatusDot status={filter} className="h-1.5 w-1.5 shadow-none" />}
              {t(`filters.${filter}`)}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3 [scrollbar-gutter:stable] sm:p-4">
        {isLoading ? (
          <CommandState title={t("list.loading")} />
        ) : loadError ? (
          <CommandState title={t("list.error")} tone="warning" />
        ) : filteredConnections.length > 0 ? (
          <div className="grid gap-2 xl:grid-cols-2 2xl:grid-cols-3">
            {filteredConnections.map((connection) => {
              const selected = selectedConnection ? connection.id === selectedConnection.id : false
              const testing = testingConnectionId === connection.id
              const probing = probeConnectionId === connection.id

              return (
                <article
                  key={connection.id}
                  className={cn(
                    "group rounded-2xl border bg-background/70 px-2.5 py-2 shadow-sm shadow-foreground/5 transition hover:bg-background hover:shadow-md hover:shadow-foreground/10",
                    selected ? "border-primary/45 bg-primary/5 ring-2 ring-primary/10" : "border-border/60",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelectConnection(connection.id)}
                    aria-current={selected ? "true" : undefined}
                    className="grid w-full grid-cols-[38px_minmax(0,1fr)_auto] items-center gap-3 rounded-xl p-1 text-left focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border bg-card text-foreground shadow-sm shadow-foreground/5", selected && "border-primary/30 bg-primary/10 text-primary")}>
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
                        "hidden h-6 shrink-0 items-center gap-1.5 rounded-full border px-2 text-[11px] font-medium sm:inline-flex",
                        statusBorderClassNames[connection.status],
                      )}
                    >
                      <StatusDot status={connection.status} className="h-1.5 w-1.5 shadow-none" />
                      {t(`status.${connection.status}`)}
                    </span>
                  </button>

                  {connection.status_message ? (
                    <p className="mt-1.5 line-clamp-1 rounded-xl bg-destructive/10 px-2.5 py-1.5 font-mono text-[11px] leading-4 text-destructive" title={connection.status_message}>
                      {connection.status_message}
                    </p>
                  ) : null}

                  {selected ? (
                    <div className="mt-2 flex flex-wrap gap-1.5 border-t border-border/50 pt-2">
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        className="h-7 rounded-full px-2.5 text-xs"
                        onClick={() => onTest(connection)}
                        disabled={testing}
                      >
                        <RefreshCw className={cn("h-3.5 w-3.5", testing && "animate-spin")} />
                        {testing ? t("actions.testing") : t("actions.testConnection")}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 rounded-full px-2.5 text-xs"
                        onClick={() => onRunProbe(connection)}
                        disabled={probing}
                      >
                        <Play className="h-3.5 w-3.5" />
                        {probing ? t("actions.runningProbe") : t("actions.runProbe")}
                      </Button>
                      <Button type="button" variant="outline" size="sm" className="h-7 rounded-full px-2.5 text-xs" onClick={() => onEdit(connection)}>
                        <Pencil className="h-3.5 w-3.5" />
                        {t("actions.editConnection")}
                      </Button>
                      <Button type="button" variant="ghost" size="sm" className="h-7 rounded-full px-2.5 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={() => onDelete(connection)}>
                        <Trash2 className="h-3.5 w-3.5" />
                        {t("actions.deleteConnection")}
                      </Button>
                    </div>
                  ) : null}
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
        "inline-flex h-8 items-center gap-1.5 rounded-full border border-border/60 bg-background/70 px-2.5 font-medium text-muted-foreground shadow-sm shadow-foreground/5",
        tone === "online" && "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
        tone === "attention" && "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300",
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
        <Button type="button" variant="outline" className="mt-4 rounded-full" onClick={onAction}>
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

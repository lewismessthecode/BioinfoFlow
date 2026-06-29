"use client"

import type { ReactNode } from "react"
import { Activity, AlertTriangle, CheckCircle2, Clock3, Pencil, Play, RefreshCw, Search, Server, Trash2 } from "lucide-react"
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
    <section className="overflow-hidden rounded-[34px] border border-border/60 bg-card/85 shadow-sm shadow-foreground/5">
      <div className="border-b border-border/60 bg-background/45 p-4 sm:p-5">
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label={t("searchPlaceholder")}
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder={t("searchPlaceholder")}
              className="h-12 rounded-2xl border-border/70 bg-background/85 pl-11 pr-4 text-base shadow-sm shadow-foreground/5"
            />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-1.5" aria-label={t("filters.label")}>
          {statusFilters.map((filter) => (
            <button
              key={filter}
              type="button"
              onClick={() => onStatusFilterChange(filter)}
              aria-pressed={statusFilter === filter}
              className={cn(
                "inline-flex h-9 items-center gap-2 rounded-full px-3 text-sm font-medium text-muted-foreground transition hover:bg-background/70 hover:text-foreground",
                statusFilter === filter && "bg-background text-foreground shadow-sm shadow-foreground/5 ring-1 ring-border/70",
              )}
            >
              {filter === "all" ? <span className="h-2 w-2 rounded-full bg-foreground" /> : <StatusDot status={filter} />}
              {t(`filters.${filter}`)}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 p-4 sm:p-5">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <SummaryTile value={connections.length} label={t("summary.total")} icon={<Server className="h-4 w-4" />} />
          <SummaryTile value={onlineCount} label={t("summary.online")} icon={<CheckCircle2 className="h-4 w-4" />} tone="online" />
          <SummaryTile value={attentionCount} label={t("summary.attention")} icon={<AlertTriangle className="h-4 w-4" />} tone="attention" />
          <SummaryTile value={agentOrConfigCount} label={t("summary.runtimeManaged")} icon={<Activity className="h-4 w-4" />} />
        </div>

        {isLoading ? (
          <CommandState title={t("list.loading")} />
        ) : loadError ? (
          <CommandState title={t("list.error")} tone="warning" />
        ) : filteredConnections.length > 0 ? (
          <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
            {filteredConnections.map((connection) => {
              const selected = selectedConnection ? connection.id === selectedConnection.id : false
              const testing = testingConnectionId === connection.id
              const probing = probeConnectionId === connection.id

              return (
                <article
                  key={connection.id}
                  className={cn(
                    "group rounded-[26px] border bg-background/70 p-3 shadow-sm shadow-foreground/5 transition hover:-translate-y-0.5 hover:bg-background hover:shadow-md hover:shadow-foreground/10",
                    selected
                      ? "border-primary/45 ring-4 ring-primary/10"
                      : "border-border/60",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelectConnection(connection.id)}
                    aria-current={selected ? "true" : undefined}
                    className="block w-full rounded-[20px] p-1 text-left focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    <div className="flex min-w-0 items-start gap-3">
                      <div className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border bg-card text-foreground shadow-sm shadow-foreground/5", selected && "border-primary/30 bg-primary/10 text-primary")}>
                        <Server className="h-5 w-5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <h2 className="truncate text-base font-semibold tracking-tight text-foreground">{connection.name}</h2>
                            <p className="mt-1 truncate font-mono text-sm text-muted-foreground">
                              {connection.username}@{connection.host}:{connection.port}
                            </p>
                          </div>
                          <span
                            className={cn(
                              "inline-flex shrink-0 items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium",
                              statusBorderClassNames[connection.status],
                            )}
                          >
                            <StatusDot status={connection.status} className="h-2 w-2 shadow-none" />
                            {t(`status.${connection.status}`)}
                          </span>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
                          <span className="rounded-full bg-muted/55 px-2.5 py-1 font-medium text-muted-foreground">
                            {t(`auth.${connection.auth_method}`)}
                          </span>
                          {connection.ssh_alias ? (
                            <span className="max-w-full truncate rounded-full bg-muted/55 px-2.5 py-1 font-mono text-muted-foreground">
                              {connection.ssh_alias}
                            </span>
                          ) : null}
                          {connection.last_checked_at ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-muted/55 px-2.5 py-1 text-muted-foreground">
                              <Clock3 className="h-3 w-3" />
                              {formatCheckedAt(connection.last_checked_at)}
                            </span>
                          ) : null}
                        </div>
                        {connection.status_message ? (
                          <p className="mt-3 line-clamp-2 rounded-2xl bg-destructive/10 px-3 py-2 font-mono text-xs leading-5 text-destructive">
                            {connection.status_message}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </button>

                  {selected ? (
                    <div className="mt-3 flex flex-wrap gap-1.5 border-t border-border/50 pt-3">
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        className="h-8 rounded-full"
                        onClick={() => onTest(connection)}
                        disabled={testing}
                      >
                        <RefreshCw className={cn("h-4 w-4", testing && "animate-spin")} />
                        {testing ? t("actions.testing") : t("actions.testConnection")}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-8 rounded-full"
                        onClick={() => onRunProbe(connection)}
                        disabled={probing}
                      >
                        <Play className="h-4 w-4" />
                        {probing ? t("actions.runningProbe") : t("actions.runProbe")}
                      </Button>
                      <Button type="button" variant="outline" size="sm" className="h-8 rounded-full" onClick={() => onEdit(connection)}>
                        <Pencil className="h-4 w-4" />
                        {t("actions.editConnection")}
                      </Button>
                      <Button type="button" variant="ghost" size="sm" className="h-8 rounded-full text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={() => onDelete(connection)}>
                        <Trash2 className="h-4 w-4" />
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

function SummaryTile({
  value,
  label,
  icon,
  tone = "default",
}: {
  value: number
  label: string
  icon: ReactNode
  tone?: "default" | "online" | "attention"
}) {
  return (
    <div
      className={cn(
        "rounded-[24px] border border-border/60 bg-background/70 p-4 shadow-sm shadow-foreground/5",
        tone === "online" && "border-emerald-500/20 bg-emerald-500/10",
        tone === "attention" && "border-amber-500/20 bg-amber-500/10",
      )}
    >
      <div className="flex items-center justify-between gap-3 text-muted-foreground">
        {icon}
        <span className="font-mono text-xs">Bioflow</span>
      </div>
      <strong className="mt-4 block text-3xl font-semibold tracking-tight text-foreground">{value}</strong>
      <span className="mt-1 block text-sm text-muted-foreground">{label}</span>
    </div>
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
        "flex min-h-[220px] flex-col items-center justify-center rounded-[26px] border border-dashed border-border bg-background/45 px-6 py-10 text-center text-sm leading-6 text-muted-foreground",
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

"use client"

import { Pencil, RefreshCw, Search, Server } from "@/lib/icons"
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
  testingConnectionId: string | null
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
  testingConnectionId,
  onSearchChange,
  onStatusFilterChange,
  onSelectConnection,
  onEdit,
}: ConnectionListProps) {
  const t = useTranslations("connections")

  const onlineCount = connections.filter((connection) => connection.status === "online").length
  const attentionCount = connections.filter((connection) => connection.status === "error" || connection.status === "offline").length
  const agentOrConfigCount = connections.filter((connection) => connection.auth_method !== "key_file").length
  const connectionNamesById = new Map(
    connections.map((connection) => [connection.id, connection.name]),
  )

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
          <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-3">
            {filteredConnections.map((connection) => {
              const selected = selectedConnection ? connection.id === selectedConnection.id : false
              const testing = connection.id === testingConnectionId
              const jumpConnectionName = connection.jump_connection_id
                ? connectionNamesById.get(connection.jump_connection_id)
                : undefined

              return (
                <article
                  key={connection.id}
                  className={cn(
                    "group relative box-border h-[108px] rounded-2xl border bg-background px-4 py-3.5 transition-colors hover:bg-muted/35",
                    selected
                      ? "border-primary/30 bg-primary/[0.025] ring-1 ring-inset ring-primary/15"
                      : "border-border/60",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelectConnection(connection.id)}
                    aria-current={selected ? "true" : undefined}
                    className="grid h-full w-full grid-cols-[44px_minmax(0,1fr)_6rem] items-center gap-3.5 pr-11 text-left focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    <div className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border/60 bg-background text-foreground", selected && "border-primary/25 bg-primary/5 text-primary")}>
                      <Server className="h-4 w-4" />
                    </div>

                    <div className="min-w-0">
                      <h2 title={connection.name} className="truncate text-sm font-semibold tracking-tight text-foreground">{connection.name}</h2>
                      <p
                        title={`${connection.username}@${connection.host}`}
                        className="mt-1 truncate font-mono text-xs text-muted-foreground"
                      >
                        {connection.username}@{connection.host}
                      </p>
                      {jumpConnectionName ? (
                        <p
                          title={t("card.via", { name: jumpConnectionName })}
                          className="mt-0.5 truncate text-[11px] text-muted-foreground"
                        >
                          {t("card.via", { name: jumpConnectionName })}
                        </p>
                      ) : null}
                    </div>

                    <span
                      className={cn(
                        "inline-flex h-6 w-24 shrink-0 items-center justify-center gap-1.5 rounded-full border px-2 text-[11px] font-medium",
                        testing
                          ? "border-primary/20 bg-primary/5 text-primary"
                          : statusBorderClassNames[connection.status],
                      )}
                    >
                      {testing ? (
                        <RefreshCw className="h-3 w-3 animate-spin motion-reduce:animate-none" />
                      ) : (
                        <StatusDot status={connection.status} className="h-1.5 w-1.5 shadow-none" />
                      )}
                      {testing ? t("status.connecting") : t(`status.${connection.status}`)}
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
        tone === "online" && "border-success-border bg-success-muted text-success-foreground",
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

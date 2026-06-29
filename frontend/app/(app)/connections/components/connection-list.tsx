"use client"

import { Search, Server } from "lucide-react"
import { useTranslations } from "next-intl"

import { Input } from "@/components/ui/input"
import type { RemoteConnection } from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

import { StatusDot } from "./connection-ui"

type ConnectionListProps = {
  connections: RemoteConnection[]
  filteredConnections: RemoteConnection[]
  selectedConnection: RemoteConnection | null
  search: string
  isLoading: boolean
  loadError: boolean
  onSearchChange: (value: string) => void
  onSelectConnection: (id: string) => void
}

export function ConnectionList({
  connections,
  filteredConnections,
  selectedConnection,
  search,
  isLoading,
  loadError,
  onSearchChange,
  onSelectConnection,
}: ConnectionListProps) {
  const t = useTranslations("connections")

  return (
    <aside className="min-w-0 bg-muted/10 lg:border-r lg:border-border/60">
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-foreground">{t("list.title")}</h2>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">{t("list.description")}</p>
          </div>
          <Server className="mt-0.5 h-4 w-4 text-muted-foreground" />
        </div>
        <div className="relative mt-3">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label={t("searchPlaceholder")}
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder={t("searchPlaceholder")}
            className="h-9 rounded-full border-border/70 bg-background/80 pl-9"
          />
        </div>
      </div>
      <div className="border-t border-border/60 p-2">
        {isLoading ? (
          <div className="rounded-2xl border border-dashed border-border px-3 py-4 text-center text-xs leading-5 text-muted-foreground">
            {t("list.loading")}
          </div>
        ) : loadError ? (
          <div className="rounded-2xl border border-dashed border-amber-500/30 bg-amber-500/10 px-3 py-4 text-center text-xs leading-5 text-amber-700 dark:text-amber-300">
            {t("list.error")}
          </div>
        ) : filteredConnections.length > 0 ? (
          <div className="grid gap-1.5">
            {filteredConnections.map((connection) => {
              const selected = selectedConnection ? connection.id === selectedConnection.id : false

              return (
                <button
                  key={connection.id}
                  type="button"
                  onClick={() => onSelectConnection(connection.id)}
                  aria-current={selected ? "true" : undefined}
                  className={cn(
                    "group rounded-2xl border px-3 py-3 text-left transition hover:border-border hover:bg-background/65",
                    selected
                      ? "border-border bg-background shadow-sm shadow-foreground/5 ring-1 ring-foreground/5"
                      : "border-transparent bg-transparent",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-border/60 bg-background/80 text-muted-foreground group-hover:text-foreground">
                      <Server className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-foreground">{connection.name}</p>
                          <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
                            {connection.username}@{connection.host}:{connection.port}
                          </p>
                        </div>
                        <span className="inline-flex shrink-0 items-center gap-2 pt-0.5 text-xs text-muted-foreground">
                          <StatusDot status={connection.status} />
                          {t(`status.${connection.status}`)}
                        </span>
                      </div>
                      {connection.ssh_alias ? (
                        <p className="mt-2 truncate text-xs text-muted-foreground">
                          {t("detail.aliasPrefix")} {" "}
                          <span className="font-mono text-foreground">{connection.ssh_alias}</span>
                        </p>
                      ) : null}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-border px-3 py-4 text-center text-xs leading-5 text-muted-foreground">
            {connections.length === 0 ? t("list.empty") : t("list.noResults")}
          </div>
        )}
      </div>
    </aside>
  )
}

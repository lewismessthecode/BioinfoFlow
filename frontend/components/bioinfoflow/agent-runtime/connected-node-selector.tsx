"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { Check, ChevronDown, Monitor, Server } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import { RemoteConnectionStatusDot } from "@/components/bioinfoflow/remote-connection-status"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  fetchRemoteConnections,
  type RemoteConnection,
} from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

type ConnectedNodeSelectorProps = {
  disabled?: boolean
  compact?: boolean
  selectedConnectionId?: string
  onSelectedConnectionChange?: (connectionId: string) => void
}

export function ConnectedNodeSelector({
  disabled = false,
  compact = false,
  selectedConnectionId,
  onSelectedConnectionChange,
}: ConnectedNodeSelectorProps) {
  const t = useTranslations("agentRuntime.runtimeLocation")
  const isControlled = selectedConnectionId !== undefined
  const [internalSelectedConnectionId, setInternalSelectedConnectionId] = useState("")
  const [connections, setConnections] = useState<RemoteConnection[]>([])
  const [hasLoadedRemoteConnections, setHasLoadedRemoteConnections] = useState(false)
  const [remoteConnectionsLoadFailed, setRemoteConnectionsLoadFailed] = useState(false)
  const requestedSelectedConnectionId = selectedConnectionId ?? internalSelectedConnectionId
  const currentSelectedConnectionId = connections.some(
    (connection) => connection.id === requestedSelectedConnectionId,
  )
    ? requestedSelectedConnectionId
    : ""
  const selectedConnectionIdRef = useRef(requestedSelectedConnectionId)
  const onSelectedConnectionChangeRef = useRef(onSelectedConnectionChange)
  const updateSelectedConnection = useCallback((connectionId: string) => {
    setInternalSelectedConnectionId(connectionId)
    onSelectedConnectionChange?.(connectionId)
  }, [onSelectedConnectionChange])

  useEffect(() => {
    selectedConnectionIdRef.current = requestedSelectedConnectionId
  }, [requestedSelectedConnectionId])

  useEffect(() => {
    onSelectedConnectionChangeRef.current = onSelectedConnectionChange
  }, [onSelectedConnectionChange])

  useEffect(() => {
    let disposed = false

    fetchRemoteConnections()
      .then((remoteConnections) => {
        if (disposed) return
        setConnections(remoteConnections)
        setHasLoadedRemoteConnections(true)
        setRemoteConnectionsLoadFailed(false)
        const currentSelected = selectedConnectionIdRef.current
        const hasCurrentSelected = remoteConnections.some(
          (connection) => connection.id === currentSelected,
        )
        const nextSelected = hasCurrentSelected ? currentSelected : ""
        if (!isControlled) {
          setInternalSelectedConnectionId(nextSelected)
        }
      })
      .catch(() => {
        if (disposed) return
        setConnections([])
        setHasLoadedRemoteConnections(true)
        setRemoteConnectionsLoadFailed(true)
      })

    return () => {
      disposed = true
    }
  }, [isControlled])
  const selectedConnection = useMemo(
    () => connections.find((connection) => connection.id === currentSelectedConnectionId) ?? null,
    [connections, currentSelectedConnectionId],
  )
  const hasPendingSelectedConnection = Boolean(
    requestedSelectedConnectionId && !selectedConnection,
  )
  const selectedStatus = selectedConnection ? t(`status.${selectedConnection.status}`) : ""
  const selectedConnectionLabel = selectedConnection
    ? connectionDisplayName(selectedConnection)
    : ""
  const pendingSelectedStatus = remoteConnectionsLoadFailed ? t("loadFailed") : ""
  const hasRemoteLoadFailed =
    hasLoadedRemoteConnections && remoteConnectionsLoadFailed && connections.length === 0

  useEffect(() => {
    if (
      hasLoadedRemoteConnections &&
      !remoteConnectionsLoadFailed &&
      requestedSelectedConnectionId &&
      !currentSelectedConnectionId
    ) {
      onSelectedConnectionChange?.("")
    }
  }, [
    currentSelectedConnectionId,
    hasLoadedRemoteConnections,
    onSelectedConnectionChange,
    remoteConnectionsLoadFailed,
    requestedSelectedConnectionId,
  ])

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          className={cn(
            "h-9 min-w-0 max-w-[13rem] rounded-[8px] border border-border/70 bg-card px-2.5 text-xs font-medium text-muted-foreground shadow-none hover:bg-muted/70 hover:text-foreground",
            compact && "max-w-[10rem]",
          )}
          disabled={disabled}
          aria-label={
            selectedConnection
              ? t("selectedRemoteAria", {
                  host: selectedConnection.host,
                  name: selectedConnectionLabel,
                  status: selectedStatus,
                })
              : hasPendingSelectedConnection
                ? t("selectedRemoteAria", {
                    host: requestedSelectedConnectionId,
                    name: t("remote.label"),
                    status: pendingSelectedStatus,
                  })
              : t("selectedLocalAria")
          }
        >
          {selectedConnection || hasPendingSelectedConnection ? (
            <Server className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <Monitor className="h-3.5 w-3.5 shrink-0" />
          )}
          {selectedConnection ? <RemoteConnectionStatusDot status={selectedConnection.status} className="shadow-[0_0_0_3px]" /> : null}
          <span className="min-w-0 truncate">
            {selectedConnection
              ? selectedConnectionLabel
              : hasPendingSelectedConnection
                ? t("remote.label")
                : t("local.label")}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        side="top"
        sideOffset={10}
        className="w-80 rounded-xl border-border/70 bg-popover p-1.5 shadow-[0_14px_34px_rgba(36,35,33,0.08)]"
      >
        <DropdownMenuLabel className="px-2.5 py-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
          {t("menuTitle")}
        </DropdownMenuLabel>
        <DropdownMenuItem
          className="items-start gap-3 rounded-[8px] px-2.5 py-2.5 text-sm"
          role="menuitemradio"
          aria-checked={!currentSelectedConnectionId && !hasPendingSelectedConnection}
          onSelect={() => updateSelectedConnection("")}
        >
          <Monitor className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block font-medium text-foreground">{t("local.label")}</span>
            <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
              {t("local.description")}
            </span>
          </span>
          {!currentSelectedConnectionId && !hasPendingSelectedConnection ? (
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          ) : null}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {connections.length ? (
          <DropdownMenuLabel className="px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            {t("remote.label")}
          </DropdownMenuLabel>
        ) : null}
        {connections.map((connection) => {
          const selected = connection.id === currentSelectedConnectionId
          const connectionLabel = connectionDisplayName(connection)
          const sshTarget = `${connection.username}@${connection.host}:${connection.port}`
          const summary = [sshTarget, connection.ssh_alias].filter(Boolean).join(" · ")

          return (
            <DropdownMenuItem
              key={connection.id}
              className="items-start gap-3 rounded-[8px] px-2.5 py-2.5 text-sm"
              role="menuitemradio"
              aria-checked={selected}
              onSelect={() => updateSelectedConnection(connection.id)}
            >
              <RemoteConnectionStatusDot status={connection.status} className="shadow-[0_0_0_3px]" />
              <span className="min-w-0 flex-1">
                <span className="block font-medium text-foreground">{connectionLabel}</span>
                <span className="mt-0.5 block truncate font-mono text-xs leading-5 text-muted-foreground">
                  {summary}
                </span>
              </span>
              {selected ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> : null}
            </DropdownMenuItem>
          )
        })}
        {hasPendingSelectedConnection ? (
          <DropdownMenuItem
            disabled
            className="items-start gap-3 rounded-[8px] px-2.5 py-2.5 text-sm text-muted-foreground"
            role="menuitemradio"
            aria-checked
          >
            <Server className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1">
              <span className="block font-medium text-foreground">{t("remote.label")}</span>
              <span className="mt-0.5 block truncate font-mono text-xs leading-5 text-muted-foreground">
                {pendingSelectedStatus || requestedSelectedConnectionId}
              </span>
            </span>
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          </DropdownMenuItem>
        ) : hasRemoteLoadFailed ? (
          <DropdownMenuItem
            disabled
            className="items-start gap-3 rounded-[8px] px-2.5 py-2.5 text-sm text-muted-foreground"
          >
            <Server className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{t("loadFailed")}</span>
          </DropdownMenuItem>
        ) : !connections.length ? (
          <DropdownMenuItem
            disabled
            className="items-start gap-3 rounded-[8px] px-2.5 py-2.5 text-sm text-muted-foreground"
          >
            <Server className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{t("emptyRemoteHosts")}</span>
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild className="rounded-[8px] px-2.5 py-2 text-sm">
          <Link href="/connections">
            <Server className="h-4 w-4" />
            <span>{t("manage")}</span>
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function connectionDisplayName(connection: RemoteConnection) {
  return connection.name.trim() || connection.host
}

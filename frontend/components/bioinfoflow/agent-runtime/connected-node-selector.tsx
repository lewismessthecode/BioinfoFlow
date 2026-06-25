"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { Check, ChevronDown, Server } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  demoConnectionNodes,
  fetchRemoteConnections,
  type RemoteConnection,
  type RemoteConnectionStatus,
} from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

type ConnectedNodeSelectorProps = {
  disabled?: boolean
  compact?: boolean
  selectedConnectionId?: string
  onSelectedConnectionChange?: (connectionId: string) => void
}

const statusDotClassNames: Record<RemoteConnectionStatus, string> = {
  online: "bg-emerald-500 shadow-emerald-500/40",
  offline: "bg-rose-500 shadow-rose-500/40",
  error: "bg-amber-500 shadow-amber-500/40",
  unknown: "bg-slate-400 shadow-slate-400/30",
}

function StatusDot({ status }: { status: RemoteConnectionStatus }) {
  return (
    <span
      className={cn("h-2.5 w-2.5 rounded-full shadow-[0_0_0_3px]", statusDotClassNames[status])}
      aria-hidden="true"
    />
  )
}

export function ConnectedNodeSelector({
  disabled = false,
  compact = false,
  selectedConnectionId,
  onSelectedConnectionChange,
}: ConnectedNodeSelectorProps) {
  const t = useTranslations("agentRuntime.connectedNode")
  const isControlled = selectedConnectionId !== undefined
  const [internalSelectedConnectionId, setInternalSelectedConnectionId] = useState("")
  const [connections, setConnections] = useState<RemoteConnection[]>(demoConnectionNodes)
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
        const currentSelected = selectedConnectionIdRef.current
        const hasCurrentSelected = remoteConnections.some(
          (connection) => connection.id === currentSelected,
        )
        const nextSelected = hasCurrentSelected ? currentSelected : ""
        if (!isControlled) {
          setInternalSelectedConnectionId(nextSelected)
        }
        if (currentSelected && nextSelected !== currentSelected) {
          onSelectedConnectionChangeRef.current?.("")
        }
      })
      .catch(() => {
        // Keep demo fallback data when the live backend is unavailable.
      })

    return () => {
      disposed = true
    }
  }, [isControlled])
  const selectedConnection = useMemo(
    () => connections.find((connection) => connection.id === currentSelectedConnectionId) ?? null,
    [connections, currentSelectedConnectionId],
  )
  const selectedStatus = selectedConnection ? t(`status.${selectedConnection.status}`) : ""

  useEffect(() => {
    if (requestedSelectedConnectionId && !currentSelectedConnectionId) {
      onSelectedConnectionChange?.("")
    }
  }, [
    currentSelectedConnectionId,
    onSelectedConnectionChange,
    requestedSelectedConnectionId,
  ])

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          className={cn(
            "h-9 min-w-0 max-w-[13rem] rounded-full border border-border/70 bg-card px-2.5 text-xs font-medium text-muted-foreground shadow-xs hover:bg-muted/70 hover:text-foreground",
            compact && "max-w-[10rem]",
          )}
          disabled={disabled}
          aria-label={
            selectedConnection
              ? t("selectedAria", {
                  host: selectedConnection.host,
                  name: selectedConnection.name,
                  status: selectedStatus,
                })
              : t("placeholder")
          }
        >
          <Server className="h-3.5 w-3.5 shrink-0" />
          {selectedConnection ? <StatusDot status={selectedConnection.status} /> : null}
          <span className="min-w-0 truncate">
            {selectedConnection ? selectedConnection.name : t("placeholder")}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        side="top"
        sideOffset={10}
        className="w-80 rounded-2xl border-border/70 bg-popover p-1.5 shadow-2xl shadow-foreground/10"
      >
        <DropdownMenuLabel className="px-2.5 py-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
          {t("menuTitle")}
        </DropdownMenuLabel>
        {connections.map((connection) => {
          const selected = connection.id === currentSelectedConnectionId
          const sshTarget = `${connection.username}@${connection.host}:${connection.port}`
          const summary = [sshTarget, connection.ssh_alias].filter(Boolean).join(" · ")

          return (
            <DropdownMenuItem
              key={connection.id}
              className="items-start gap-3 rounded-xl px-2.5 py-2.5 text-sm"
              onSelect={() => updateSelectedConnection(connection.id)}
            >
              <StatusDot status={connection.status} />
              <span className="min-w-0 flex-1">
                <span className="block font-medium text-foreground">{connection.name}</span>
                <span className="mt-0.5 block truncate font-mono text-xs leading-5 text-muted-foreground">
                  {summary}
                </span>
              </span>
              {selected ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> : null}
            </DropdownMenuItem>
          )
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild className="rounded-xl px-2.5 py-2 text-sm">
          <Link href="/connections">
            <Server className="h-4 w-4" />
            <span>{t("manage")}</span>
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

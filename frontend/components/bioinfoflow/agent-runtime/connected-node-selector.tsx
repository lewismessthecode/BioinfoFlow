"use client"

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import Link from "next/link"
import { ChevronDown, Monitor, Server } from "@/lib/icons"
import { useTranslations } from "next-intl"

import {
  composerSelectorChevronClassName,
  composerSelectorChipClassName,
  composerSelectorIconClassName,
  composerSelectorMenuClassName,
} from "@/components/bioinfoflow/composer-selector-chip"
import { Button } from "@/components/ui/button"
import { RemoteConnectionStatusDot } from "@/components/bioinfoflow/remote-connection-status"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  fetchRemoteConnections,
  type RemoteConnection,
} from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

export const LOCAL_TARGET_ID = "local"

export type ExecutionTargetSelection =
  | { mode: "auto" }
  | { mode: "manual"; targetIds: string[] }

type ConnectedNodeSelectorProps = {
  disabled?: boolean
  compact?: boolean
  value?: ExecutionTargetSelection
  onChange?: (value: ExecutionTargetSelection) => void
  currentTargetLabel?: string | null
  selectedConnectionId?: string
  onSelectedConnectionChange?: (connectionId: string) => void
}

export function ConnectedNodeSelector({
  disabled = false,
  compact = false,
  value,
  onChange,
  currentTargetLabel,
  selectedConnectionId,
  onSelectedConnectionChange,
}: ConnectedNodeSelectorProps) {
  const t = useTranslations("agentRuntime.runtimeLocation")
  const isControlled = value !== undefined || selectedConnectionId !== undefined
  const [internalSelection, setInternalSelection] = useState<ExecutionTargetSelection>(
    { mode: "auto" },
  )
  const [connections, setConnections] = useState<RemoteConnection[]>([])
  const [hasLoadedRemoteConnections, setHasLoadedRemoteConnections] = useState(false)
  const [remoteConnectionsLoadFailed, setRemoteConnectionsLoadFailed] = useState(false)
  const requestedSelection = value ?? legacySelection(selectedConnectionId) ?? internalSelection
  const normalizedSelection = normalizeSelection(requestedSelection)
  const TriggerIcon =
    normalizedSelection.mode === "manual" &&
    normalizedSelection.targetIds.every((targetId) => targetId === LOCAL_TARGET_ID)
      ? Monitor
      : Server

  useEffect(() => {
    let disposed = false

    fetchRemoteConnections()
      .then((remoteConnections) => {
        if (disposed) return
        setConnections(remoteConnections)
        setHasLoadedRemoteConnections(true)
        setRemoteConnectionsLoadFailed(false)
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
  }, [])

  const connectionById = useMemo(
    () => new Map(connections.map((connection) => [connection.id, connection])),
    [connections],
  )
  const hasRemoteLoadFailed =
    hasLoadedRemoteConnections && remoteConnectionsLoadFailed && connections.length === 0
  const triggerModeLabel =
    normalizedSelection.mode === "auto" ? t("auto") : t("manual")
  const pillLabel =
    currentTargetLabel || targetSummaryLabel(normalizedSelection, connectionById, t)
  const triggerAria =
    normalizedSelection.mode === "auto"
      ? t("selectedAutoAria", { target: pillLabel })
      : t("selectedManualAria", { target: pillLabel })

  const commitSelection = useCallback(
    (nextSelection: ExecutionTargetSelection) => {
      const normalized = normalizeSelection(nextSelection)
      if (!isControlled) setInternalSelection(normalized)
      onChange?.(normalized)
      onSelectedConnectionChange?.(legacyConnectionId(normalized))
    },
    [isControlled, onChange, onSelectedConnectionChange],
  )

  useEffect(() => {
    if (!hasLoadedRemoteConnections || remoteConnectionsLoadFailed) return
    if (normalizedSelection.mode !== "manual") return
    const knownRemoteIds = new Set(connections.map((connection) => connection.id))
    const prunedSelection = normalizeSelection({
      mode: "manual",
      targetIds: normalizedSelection.targetIds.filter(
        (targetId) => targetId === LOCAL_TARGET_ID || knownRemoteIds.has(targetId),
      ),
    })
    if (!selectionEquals(prunedSelection, normalizedSelection)) {
      const timer = window.setTimeout(() => commitSelection(prunedSelection), 0)
      return () => window.clearTimeout(timer)
    }
  }, [
    commitSelection,
    connections,
    hasLoadedRemoteConnections,
    normalizedSelection,
    remoteConnectionsLoadFailed,
  ])

  const switchMode = useCallback(
    (mode: "auto" | "manual") => {
      if (mode === "auto") {
        commitSelection({ mode: "auto" })
        return
      }
      const current =
        normalizedSelection.mode === "manual"
          ? normalizedSelection.targetIds
          : [LOCAL_TARGET_ID]
      commitSelection({ mode: "manual", targetIds: ensureManualTargets(current) })
    },
    [commitSelection, normalizedSelection],
  )

  const toggleManualTarget = useCallback(
    (targetId: string, checked: boolean) => {
      const current =
        normalizedSelection.mode === "manual"
          ? normalizedSelection.targetIds
          : [LOCAL_TARGET_ID]
      const next = checked
        ? [...current, targetId]
        : current.filter((candidate) => candidate !== targetId)
      commitSelection({ mode: "manual", targetIds: ensureManualTargets(next) })
    },
    [commitSelection, normalizedSelection],
  )

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={cn(
            composerSelectorChipClassName,
            "max-w-[13rem] gap-1.5 border-border/70 bg-background text-foreground/80 shadow-none",
            compact && "max-w-9 px-2",
          )}
          data-composer-chip="true"
          disabled={disabled}
          aria-label={triggerAria}
        >
          <TriggerIcon className={composerSelectorIconClassName} />
          {compact ? null : (
            <>
              <span className="min-w-0 shrink-0">{triggerModeLabel}</span>
              <span
                key={pillLabel}
                className="inline-flex max-w-[5.75rem] items-center gap-1 overflow-hidden rounded-full bg-[#EDF3EC] px-1.5 py-0.5 text-[11px] font-medium leading-none text-[#346538] animate-in fade-in-0 slide-in-from-bottom-1 duration-200"
                data-testid="execution-current-target-pill"
              >
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#346538]" />
                <span className="truncate">{pillLabel}</span>
              </span>
            </>
          )}
          <ChevronDown className={composerSelectorChevronClassName} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        side="top"
        sideOffset={10}
        className={cn("w-[286px]", composerSelectorMenuClassName)}
      >
        <DropdownMenuRadioGroup
          value={normalizedSelection.mode}
          onValueChange={(mode) => switchMode(mode === "manual" ? "manual" : "auto")}
        >
          <DropdownMenuRadioItem
            value="auto"
            className="rounded-[7px] py-2 pl-8 pr-2 text-xs"
            onSelect={(event) => event.preventDefault()}
          >
            <span className="min-w-0 flex-1">
              <span className="block font-medium text-foreground">{t("auto")}</span>
            </span>
            <span className="rounded-full bg-[#E1F3FE] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.05em] text-[#1F6C9F]">
              {connections.length ? connections.length + 1 : 1}
            </span>
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem
            value="manual"
            className="rounded-[7px] py-2 pl-8 pr-2 text-xs"
            onSelect={(event) => event.preventDefault()}
          >
            <span className="min-w-0 flex-1">
              <span className="block font-medium text-foreground">{t("manual")}</span>
            </span>
            <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.05em] text-muted-foreground">
              {manualCountLabel(normalizedSelection, t)}
            </span>
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        {normalizedSelection.mode === "manual" ? (
          <>
            <DropdownMenuSeparator />
            <ManualTargetItem
              checked={normalizedSelection.targetIds.includes(LOCAL_TARGET_ID)}
              onCheckedChange={(checked) =>
                toggleManualTarget(LOCAL_TARGET_ID, checked)
              }
              label={t("local.label")}
              statusLabel={t("localBadge")}
              icon={<Monitor className="h-3.5 w-3.5 text-muted-foreground" />}
            />
            {connections.map((connection) => {
              const connectionLabel = connectionDisplayName(connection)
              const sshTarget = `${connection.username}@${connection.host}:${connection.port}`
              const summary = [sshTarget, connection.ssh_alias]
                .filter(Boolean)
                .join(" · ")
              return (
                <ManualTargetItem
                  key={connection.id}
                  checked={normalizedSelection.targetIds.includes(connection.id)}
                  onCheckedChange={(checked) =>
                    toggleManualTarget(connection.id, checked)
                  }
                  label={connectionLabel}
                  summary={summary}
                  statusLabel={t(`status.${connection.status}`)}
                  icon={
                    <RemoteConnectionStatusDot
                      status={connection.status}
                      className="shadow-[0_0_0_3px]"
                    />
                  }
                />
              )
            })}
            {hasRemoteLoadFailed ? (
              <DropdownMenuItem
                disabled
                className="items-start gap-2 rounded-[7px] px-2 py-1.5 text-xs text-muted-foreground"
              >
                <Server className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{t("loadFailed")}</span>
              </DropdownMenuItem>
            ) : hasLoadedRemoteConnections && !connections.length ? (
              <DropdownMenuItem
                disabled
                className="items-start gap-2 rounded-[7px] px-2 py-1.5 text-xs text-muted-foreground"
              >
                <Server className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{t("emptyRemoteHosts")}</span>
              </DropdownMenuItem>
            ) : null}
          </>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild className="rounded-[7px] px-2 py-1.5 text-xs">
          <Link href="/connections">
            <Server className="h-3.5 w-3.5" />
            <span>{t("manage")}</span>
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function ManualTargetItem({
  checked,
  onCheckedChange,
  label,
  summary,
  statusLabel,
  icon,
}: {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  label: string
  summary?: string
  statusLabel: string
  icon: ReactNode
}) {
  return (
    <DropdownMenuCheckboxItem
      checked={checked}
      onCheckedChange={(value) => onCheckedChange(Boolean(value))}
      onSelect={(event) => event.preventDefault()}
      className="items-start gap-2 rounded-[7px] px-2 py-2 pl-8 text-xs"
    >
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block font-medium text-foreground">{label}</span>
        {summary ? (
          <span className="mt-0.5 block truncate font-mono text-[11px] leading-4 text-muted-foreground">
            {summary}
          </span>
        ) : null}
      </span>
      <span className="mt-0.5 shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.05em] text-muted-foreground">
        {statusLabel}
      </span>
    </DropdownMenuCheckboxItem>
  )
}

function normalizeSelection(selection: ExecutionTargetSelection): ExecutionTargetSelection {
  if (selection.mode === "auto") return { mode: "auto" }
  return { mode: "manual", targetIds: ensureManualTargets(selection.targetIds) }
}

function ensureManualTargets(targetIds: string[]) {
  const deduped = Array.from(
    new Set(targetIds.filter((targetId) => targetId.trim())),
  )
  return deduped.length ? deduped : [LOCAL_TARGET_ID]
}

function selectionEquals(
  left: ExecutionTargetSelection,
  right: ExecutionTargetSelection,
) {
  if (left.mode !== right.mode) return false
  if (left.mode === "auto" || right.mode === "auto") return true
  if (left.targetIds.length !== right.targetIds.length) return false
  return left.targetIds.every((targetId, index) => targetId === right.targetIds[index])
}

function legacySelection(
  selectedConnectionId: string | undefined,
): ExecutionTargetSelection | null {
  if (selectedConnectionId === undefined) return null
  return {
    mode: "manual",
    targetIds: selectedConnectionId ? [selectedConnectionId] : [LOCAL_TARGET_ID],
  }
}

function legacyConnectionId(selection: ExecutionTargetSelection) {
  if (selection.mode === "auto") return ""
  const remoteTarget = selection.targetIds.find((targetId) => targetId !== LOCAL_TARGET_ID)
  return remoteTarget ?? ""
}

function targetSummaryLabel(
  selection: ExecutionTargetSelection,
  connectionById: Map<string, RemoteConnection>,
  t: ReturnType<typeof useTranslations>,
) {
  if (selection.mode === "auto") return t("allTargets")
  if (selection.targetIds.length > 1) {
    return t("targetCount", { count: String(selection.targetIds.length) })
  }
  const targetId = selection.targetIds[0]
  if (targetId === LOCAL_TARGET_ID) return t("local.label")
  const connection = connectionById.get(targetId)
  return connection ? connectionDisplayName(connection) : t("remote.label")
}

function manualCountLabel(
  selection: ExecutionTargetSelection,
  t: ReturnType<typeof useTranslations>,
) {
  if (selection.mode === "auto") return t("allTargets")
  return t("targetCount", { count: String(selection.targetIds.length) })
}

function connectionDisplayName(connection: RemoteConnection) {
  return connection.name.trim() || connection.host
}

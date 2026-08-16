"use client"

import { useMemo, useState } from "react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  composerSelectorChevronClassName,
  composerSelectorIconClassName,
} from "@/components/bioinfoflow/composer-selector-chip"
import {
  ComposerSelectorMenuSurface,
  ComposerSelectorTrigger,
} from "@/components/bioinfoflow/composer-selector"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ChevronDown, Loader2, Monitor, Server } from "@/lib/icons"
import { cn } from "@/lib/utils"

export type AgentEnvironmentSelection =
  { mode: "auto" } | { mode: "manual"; targetIds: string[] }

export type AgentEnvironmentTarget = {
  id: string
  label: string
  description?: string
  kind: "local" | "ssh"
  status?: "online" | "offline" | "error" | "unknown"
}

type EnvironmentSelectorProps = {
  targets: readonly AgentEnvironmentTarget[]
  requested: AgentEnvironmentSelection
  effective?: AgentEnvironmentSelection
  pending?: boolean
  disabled?: boolean
  onChange: (selection: AgentEnvironmentSelection) => Promise<void>
}

export function EnvironmentSelector({
  targets,
  requested,
  effective,
  pending = false,
  disabled = false,
  onChange,
}: EnvironmentSelectorProps) {
  const t = useTranslations("agentComposer.environment")
  const visibleTargets = useMemo<readonly AgentEnvironmentTarget[]>(
    () =>
      targets.length
        ? targets
        : [{ id: "local", label: t("local"), kind: "local", status: "online" }],
    [t, targets],
  )
  const [errorSelection, setErrorSelection] =
    useState<AgentEnvironmentSelection | null>(null)
  const requestedSelection = normalizeSelection(requested, visibleTargets)
  const effectiveSelection = effective
    ? normalizeSelection(effective, visibleTargets)
    : requestedSelection
  const isPending =
    pending || !selectionEquals(requestedSelection, effectiveSelection)
  const controlsDisabled = disabled || isPending
  const targetById = useMemo(
    () => new Map(visibleTargets.map((target) => [target.id, target])),
    [visibleTargets],
  )
  const modeLabel = t(`${requestedSelection.mode}.name`)
  const targetSummary = summaryLabel(requestedSelection, targetById, t)
  const triggerLabel =
    requestedSelection.mode === "auto"
      ? modeLabel
      : `${modeLabel}, ${targetSummary}`

  const requestChange = async (selection: AgentEnvironmentSelection) => {
    if (controlsDisabled) return
    const normalized = normalizeSelection(selection, visibleTargets)
    setErrorSelection(null)
    try {
      await onChange(normalized)
    } catch {
      setErrorSelection(normalized)
    }
  }

  const switchMode = (mode: "auto" | "manual") => {
    if (mode === "auto") {
      void requestChange({ mode: "auto" })
      return
    }
    const currentIds =
      requestedSelection.mode === "manual"
        ? requestedSelection.targetIds
        : defaultManualTargets(visibleTargets)
    void requestChange({ mode: "manual", targetIds: currentIds })
  }

  const toggleTarget = (targetId: string, checked: boolean) => {
    const currentIds =
      requestedSelection.mode === "manual"
        ? requestedSelection.targetIds
        : defaultManualTargets(visibleTargets)
    const nextIds = checked
      ? [...currentIds, targetId]
      : currentIds.filter((id) => id !== targetId)
    void requestChange({
      mode: "manual",
      targetIds: ensureTargets(nextIds, visibleTargets),
    })
  }

  return (
    <div className="flex min-w-0 flex-col items-start gap-1.5">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <ComposerSelectorTrigger
            type="button"
            variant="ghost"
            size="sm"
            disabled={controlsDisabled}
            aria-label={`${t("label")}: ${triggerLabel}`}
            className="max-w-[12rem]"
          >
            {isPending ? (
              <Loader2
                className="size-3.5 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
            ) : requestedSelection.mode === "manual" &&
              requestedSelection.targetIds.every(
                (targetId) => targetById.get(targetId)?.kind === "local",
              ) ? (
              <Monitor
                className={composerSelectorIconClassName}
                aria-hidden="true"
              />
            ) : (
              <Server
                className={composerSelectorIconClassName}
                aria-hidden="true"
              />
            )}
            <span className="shrink-0">{modeLabel}</span>
            {requestedSelection.mode === "manual" ? (
              <span className="truncate text-foreground/65">
                · {targetSummary}
              </span>
            ) : null}
            <ChevronDown
              className={composerSelectorChevronClassName}
              aria-hidden="true"
            />
          </ComposerSelectorTrigger>
        </DropdownMenuTrigger>
        <ComposerSelectorMenuSurface
          kind="dropdown"
          align="start"
          side="top"
          className="w-[19rem]"
        >
          <div className="px-2 pb-1.5 pt-1 text-xs font-medium text-muted-foreground">
            {t("title")}
          </div>
          <DropdownMenuRadioGroup
            value={requestedSelection.mode}
            onValueChange={(mode) =>
              switchMode(mode === "manual" ? "manual" : "auto")
            }
          >
            {(["auto", "manual"] as const).map((mode) => (
              <DropdownMenuRadioItem
                key={mode}
                value={mode}
                disabled={controlsDisabled}
                onSelect={(event) => event.preventDefault()}
                className="items-start rounded-lg py-2 pl-8 pr-2 text-xs"
              >
                <span className="grid gap-0.5">
                  <span className="font-medium text-foreground">
                    {t(`${mode}.name`)}
                  </span>
                  <span className="whitespace-normal leading-4 text-muted-foreground">
                    {t(`${mode}.description`)}
                  </span>
                </span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
          {requestedSelection.mode === "manual" ? (
            <>
              <DropdownMenuSeparator />
              {visibleTargets.map((target) => (
                <DropdownMenuCheckboxItem
                  key={target.id}
                  checked={requestedSelection.targetIds.includes(target.id)}
                  disabled={controlsDisabled}
                  onCheckedChange={(checked) =>
                    toggleTarget(target.id, Boolean(checked))
                  }
                  onSelect={(event) => event.preventDefault()}
                  className="items-start gap-2 rounded-lg py-2 pl-8 pr-2 text-xs"
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "mt-1 size-1.5 shrink-0 rounded-full bg-muted-foreground/45",
                      target.status === "online" && "bg-emerald-500",
                      target.status === "error" && "bg-destructive",
                      target.status === "offline" && "bg-muted-foreground/30",
                    )}
                  />
                  <span className="grid min-w-0 flex-1 gap-0.5">
                    <span className="font-medium text-foreground">
                      {target.label}
                    </span>
                    {target.description ? (
                      <span className="truncate font-mono text-[11px] text-muted-foreground">
                        {target.description}
                      </span>
                    ) : null}
                  </span>
                  {target.status ? (
                    <span className="text-[10px] text-muted-foreground">
                      {t(`status.${target.status}`)}
                    </span>
                  ) : null}
                </DropdownMenuCheckboxItem>
              ))}
            </>
          ) : null}
        </ComposerSelectorMenuSurface>
      </DropdownMenu>
      {isPending ? (
        <p role="status" className="px-2 text-[11px] text-muted-foreground">
          {t("updating")}
        </p>
      ) : null}
      {errorSelection ? (
        <div
          role="alert"
          className="flex items-center gap-1 px-2 text-[11px] text-destructive"
        >
          <span>{t("updateError")}</span>
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto px-1 text-[11px]"
            onClick={() => void requestChange(errorSelection)}
          >
            {t("retry")}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function normalizeSelection(
  selection: AgentEnvironmentSelection,
  targets: readonly AgentEnvironmentTarget[],
): AgentEnvironmentSelection {
  if (selection.mode === "auto") return { mode: "auto" }
  return {
    mode: "manual",
    targetIds: ensureTargets(selection.targetIds, targets),
  }
}

function ensureTargets(
  targetIds: readonly string[],
  targets: readonly AgentEnvironmentTarget[],
) {
  const knownIds = new Set(targets.map((target) => target.id))
  const uniqueIds = Array.from(
    new Set(targetIds.filter((targetId) => knownIds.has(targetId))),
  )
  return uniqueIds.length ? uniqueIds : defaultManualTargets(targets)
}

function defaultManualTargets(targets: readonly AgentEnvironmentTarget[]) {
  const localId = targets.find((target) => target.kind === "local")?.id
  return localId ? [localId] : targets[0] ? [targets[0].id] : []
}

function selectionEquals(
  left: AgentEnvironmentSelection,
  right: AgentEnvironmentSelection,
) {
  if (left.mode !== right.mode) return false
  if (left.mode === "auto" || right.mode === "auto") return true
  return (
    left.targetIds.length === right.targetIds.length &&
    left.targetIds.every(
      (targetId, index) => targetId === right.targetIds[index],
    )
  )
}

function summaryLabel(
  selection: AgentEnvironmentSelection,
  targetById: Map<string, AgentEnvironmentTarget>,
  t: ReturnType<typeof useTranslations>,
) {
  if (selection.mode === "auto") return t("auto.name")
  if (selection.targetIds.length !== 1) {
    return t("targetCount", { count: selection.targetIds.length })
  }
  return targetById.get(selection.targetIds[0])?.label ?? t("local")
}

"use client"

import { useMemo, useState } from "react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  composerSelectorChevronClassName,
  composerSelectorMenuHeaderClassName,
  composerSelectorMenuItemClassName,
} from "@/components/bioinfoflow/composer-selector-chip"
import {
  ComposerSelectorChevronSlot,
  ComposerSelectorField,
  ComposerSelectorIconSlot,
  ComposerSelectorMenuSurface,
  ComposerSelectorOptionContent,
  ComposerSelectorText,
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
  const triggerLabel = `${modeLabel}, ${targetSummary}`

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

  const feedback = isPending ? (
    <p role="status">{t("updating")}</p>
  ) : errorSelection ? (
    <div role="alert" className="flex items-center gap-1 text-destructive">
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
  ) : null

  return (
    <ComposerSelectorField feedback={feedback}>
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
            <ComposerSelectorIconSlot>
              {isPending ? (
                <Loader2
                  className="animate-spin motion-reduce:animate-none"
                  aria-hidden="true"
                />
              ) : requestedSelection.mode === "manual" &&
                requestedSelection.targetIds.every(
                  (targetId) => targetById.get(targetId)?.kind === "local",
                ) ? (
                <Monitor aria-hidden="true" />
              ) : (
                <Server aria-hidden="true" />
              )}
            </ComposerSelectorIconSlot>
            <ComposerSelectorText>
              <span className="truncate">{targetSummary}</span>
            </ComposerSelectorText>
            <ComposerSelectorChevronSlot>
              <ChevronDown
                className={composerSelectorChevronClassName}
                aria-hidden="true"
              />
            </ComposerSelectorChevronSlot>
          </ComposerSelectorTrigger>
        </DropdownMenuTrigger>
        <ComposerSelectorMenuSurface
          kind="dropdown"
          align="start"
          side="top"
          className="w-80 max-w-[calc(100vw-1.5rem)]"
        >
          <div className={composerSelectorMenuHeaderClassName}>
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
                className={cn(
                  composerSelectorMenuItemClassName,
                  "items-start pl-8 pr-2",
                )}
              >
                <ComposerSelectorOptionContent
                  icon={
                    mode === "auto" ? (
                      <Server aria-hidden="true" />
                    ) : (
                      <Monitor aria-hidden="true" />
                    )
                  }
                  title={t(`${mode}.name`)}
                  description={t(`${mode}.description`)}
                />
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
                  className={cn(
                    composerSelectorMenuItemClassName,
                    "items-stretch pl-8 pr-2",
                  )}
                >
                  <EnvironmentTargetRow target={target} t={t} />
                </DropdownMenuCheckboxItem>
              ))}
            </>
          ) : null}
        </ComposerSelectorMenuSurface>
      </DropdownMenu>
    </ComposerSelectorField>
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
  if (selection.mode === "auto") return t("auto.summary")
  if (selection.targetIds.length !== 1) {
    return t("targetCount", { count: selection.targetIds.length })
  }
  return targetById.get(selection.targetIds[0])?.label ?? t("local")
}

type EnvironmentStatus = NonNullable<AgentEnvironmentTarget["status"]>

const environmentStatusClassNames: Record<EnvironmentStatus, string> = {
  online:
    "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300",
  offline: "border-border/70 bg-muted/80 text-muted-foreground",
  error: "border-destructive/20 bg-destructive/10 text-destructive",
  unknown:
    "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-300",
}

const environmentStatusDotClassNames: Record<EnvironmentStatus, string> = {
  online: "bg-emerald-500 dark:bg-emerald-400",
  offline: "bg-muted-foreground/45",
  error: "bg-destructive",
  unknown: "bg-amber-500 dark:bg-amber-400",
}

function EnvironmentTargetRow({
  target,
  t,
}: {
  target: AgentEnvironmentTarget
  t: ReturnType<typeof useTranslations>
}) {
  const status = target.status ?? "unknown"

  return (
    <span
      data-environment-target-row="true"
      className="grid min-w-0 flex-1 grid-cols-[minmax(0,1fr)_auto] items-center gap-3"
    >
      <span className="grid min-w-0 grid-cols-[1rem_minmax(0,1fr)] items-start gap-2">
        <span
          aria-hidden="true"
          className="inline-flex size-4 items-center justify-center text-muted-foreground [&_svg]:size-3.5"
        >
          {target.kind === "local" ? <Monitor /> : <Server />}
        </span>
        <span className="grid min-w-0 gap-0.5">
          <span className="truncate font-medium leading-4 text-foreground">
            {target.label}
          </span>
          {target.description ? (
            <span className="truncate font-mono text-[10px] leading-4 text-muted-foreground/85">
              {target.description}
            </span>
          ) : null}
        </span>
      </span>
      <span
        data-environment-status={status}
        className={cn(
          "inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-1.5 text-[10px] font-medium leading-none",
          environmentStatusClassNames[status],
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "size-1.5 shrink-0 rounded-full",
            environmentStatusDotClassNames[status],
          )}
        />
        {t(`status.${status}`)}
      </span>
    </span>
  )
}

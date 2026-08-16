"use client"

import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type {
  AgentExecutionScope,
  AgentExecutionTarget,
} from "@/lib/agent/bootstrap"
import { ChevronDown, Cpu, Server } from "@/lib/icons"
import { cn } from "@/lib/utils"

export function ExecutionTargetSelector({
  targets,
  scope,
  activeTarget,
  disabled = false,
  onChange,
}: {
  targets: AgentExecutionTarget[]
  scope: AgentExecutionScope
  activeTarget?: AgentExecutionTarget | null
  disabled?: boolean
  onChange: (scope: AgentExecutionScope) => void
}) {
  const t = useTranslations("agentExecution")
  const available = targets.filter((target) => target.disabledReason === null)
  const localOnly = available.length === 1 && available[0].kind === "local"
  const label = localOnly ? t("localOnly") : t(scope.mode)

  const toggleTarget = (targetId: string, checked: boolean) => {
    const selected =
      scope.mode === "manual" ? scope.targetIds : []
    const next = checked
      ? [...new Set([...selected, targetId])]
      : selected.filter((id) => id !== targetId)
    if (next.length === 0) return
    onChange({ mode: "manual", targetIds: next })
  }

  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled || localOnly}
            aria-label={`${t("label")}: ${label}`}
          >
            {localOnly ? <Cpu aria-hidden="true" /> : <Server aria-hidden="true" />}
            <span>{label}</span>
            {!localOnly ? <ChevronDown aria-hidden="true" /> : null}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" side="top" className="w-64">
          <DropdownMenuLabel>{t("label")}</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={scope.mode}
            onValueChange={(mode) => {
              if (mode === "auto") onChange({ mode: "auto", targetIds: [] })
            }}
          >
            <DropdownMenuRadioItem value="auto">{t("auto")}</DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
          <DropdownMenuSeparator />
          <DropdownMenuLabel>{t("manual")}</DropdownMenuLabel>
          {targets.map((target) => (
            <DropdownMenuCheckboxItem
              key={target.id}
              checked={scope.mode === "manual" && scope.targetIds.includes(target.id)}
              disabled={target.disabledReason !== null}
              onCheckedChange={(checked) => toggleTarget(target.id, checked === true)}
            >
              <span className="grid min-w-0 gap-0.5">
                <span className="truncate">{target.alias}</span>
                {target.disabledReason ? (
                  <span className="text-xs text-muted-foreground">{target.disabledReason}</span>
                ) : null}
              </span>
            </DropdownMenuCheckboxItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      {activeTarget ? (
        <span
          className={cn(
            "inline-flex max-w-36 items-center gap-1.5 truncate rounded-full bg-primary/8 px-2 py-1 text-[11px] font-medium text-foreground/72",
            "motion-safe:animate-pulse motion-reduce:animate-none",
          )}
          title={activeTarget.alias}
          aria-label={t("active", { alias: activeTarget.alias })}
        >
          <span className="size-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" />
          <span className="truncate">{activeTarget.alias}</span>
        </span>
      ) : null}
    </div>
  )
}

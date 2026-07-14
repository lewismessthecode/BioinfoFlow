"use client"

import { ShieldCheck, ShieldQuestion, Unlock } from "@/lib/icons"
import { useTranslations } from "next-intl"

import {
  composerSelectorChipClassName,
  composerSelectorIconClassName,
  composerSelectorMenuClassName,
} from "@/components/bioinfoflow/composer-selector-chip"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { AgentPermissionUpdateState } from "@/hooks/use-agent-runtime"
import type { AgentPermissionMode } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

type PermissionControlProps = {
  mode: AgentPermissionMode
  onModeChange: (mode: AgentPermissionMode) => void
  update?: AgentPermissionUpdateState
  onRetry?: () => void
  remote?: boolean
  disabled?: boolean
  compact?: boolean
}

const permissionOptions: Array<{
  mode: AgentPermissionMode
  Icon: typeof ShieldQuestion
}> = [
  { mode: "ask_each_action", Icon: ShieldQuestion },
  { mode: "guarded_auto", Icon: ShieldCheck },
  { mode: "bypass", Icon: Unlock },
]

const idleUpdate: AgentPermissionUpdateState = {
  status: "idle",
  mode: null,
  pendingStrategy: null,
  reconciliation: null,
  error: null,
}

export function PermissionControl({
  mode,
  onModeChange,
  update = idleUpdate,
  onRetry,
  remote = false,
  disabled = false,
  compact = false,
}: PermissionControlProps) {
  const t = useTranslations("agentRuntime")
  const selected =
    permissionOptions.find((option) => option.mode === mode) ?? permissionOptions[1]
  const PermissionIcon = selected.Icon
  const busy = update.status === "pending"
  const reconciliation = update.reconciliation

  return (
    <div className="relative shrink-0">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={cn(
              composerSelectorChipClassName,
              "inline-flex min-w-9 shrink items-center",
              busy &&
                "cursor-wait opacity-60 hover:border-transparent hover:bg-transparent active:scale-100",
              compact ? "max-w-9 px-2" : "max-w-[10rem] px-2",
            )}
            data-composer-chip="true"
            disabled={disabled}
            aria-disabled={busy || undefined}
            aria-label={t("permission.label")}
            aria-busy={busy}
            onPointerDown={(event) => {
              if (busy) event.preventDefault()
            }}
            onKeyDown={(event) => {
              if (
                busy &&
                (event.key === "Enter" || event.key === " " || event.key === "ArrowDown")
              ) {
                event.preventDefault()
              }
            }}
          >
            <PermissionIcon className={composerSelectorIconClassName} />
            <span className={cn("min-w-0 truncate", compact && "sr-only")}>
              {t(`permission.options.${mode}.label`)}
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          side="top"
          sideOffset={10}
          className={cn("w-72", composerSelectorMenuClassName)}
        >
          <DropdownMenuRadioGroup
            value={mode}
            onValueChange={(value) => onModeChange(value as AgentPermissionMode)}
          >
            {permissionOptions.map(({ mode: optionMode, Icon }) => (
              <DropdownMenuRadioItem
                key={optionMode}
                value={optionMode}
                disabled={busy}
                className="items-start gap-2 rounded-[7px] px-2 py-1.5 pl-7 text-xs"
              >
                <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="grid gap-0.5">
                  <span className="font-medium text-foreground">
                    {t(`permission.options.${optionMode}.label`)}
                  </span>
                  <span className="text-[11px] leading-4 text-muted-foreground">
                    {t(`permission.options.${optionMode}.description`)}
                  </span>
                </span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
          <div className="mx-1 mt-1 grid gap-1 border-t border-border/60 px-1 pt-2 text-[11px] leading-4 text-muted-foreground">
            <p>{t(remote ? "permission.boundary.remote" : "permission.boundary.local")}</p>
            <p>{t("permission.safetyFloor")}</p>
          </div>
        </DropdownMenuContent>
      </DropdownMenu>

      {update.status === "pending" ? (
        <div className="sr-only" role="status" aria-live="polite">
          {t("permission.status.updating")}
        </div>
      ) : null}
      {update.status === "success" ? (
        <div className="sr-only" role="status" aria-live="polite">
          {reconciliation
            ? t("permission.status.reconciled", {
                affected: reconciliation.affected_count,
                excluded: reconciliation.excluded_count,
                resolved: reconciliation.already_resolved_count,
              })
            : t("permission.status.updated")}
        </div>
      ) : null}
      {update.status === "error" ? (
        <div
          className="absolute bottom-full right-0 z-40 mb-2 flex w-72 items-center gap-2 rounded-lg border border-destructive/25 bg-popover px-3 py-2 text-xs text-destructive shadow-md"
          role="alert"
        >
          <span className="min-w-0 flex-1">
            {t("permission.status.failed", { error: update.error ?? "" })}
          </span>
          {onRetry ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 shrink-0 rounded-md px-2 text-xs"
              onClick={onRetry}
              aria-label={t("permission.retry")}
            >
              {t("permission.retry")}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

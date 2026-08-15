"use client"

import { useId, useState } from "react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  ChevronDown,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
} from "@/lib/icons"
import type {
  AgentPermissionMode,
  AgentWorkspaceAccess,
} from "@/lib/agent/contracts"
import { cn } from "@/lib/utils"

type PermissionMenuProps = {
  permissionMode: AgentPermissionMode
  workspaceAccess: AgentWorkspaceAccess
  activeRun: boolean
  onPermissionModeChange: (mode: AgentPermissionMode) => Promise<void>
}

type PermissionUpdate = {
  mode: AgentPermissionMode
  state: "pending" | "error"
} | null

const modes = ["ask_changes", "ask_dangerous", "full_access"] as const

const modeIcons = {
  ask_changes: ShieldQuestion,
  ask_dangerous: ShieldCheck,
  full_access: ShieldAlert,
} satisfies Record<AgentPermissionMode, typeof ShieldQuestion>

export function PermissionMenu({
  permissionMode,
  workspaceAccess,
  activeRun,
  onPermissionModeChange,
}: PermissionMenuProps) {
  const t = useTranslations("agentComposer")
  const descriptionId = useId()
  const [update, setUpdate] = useState<PermissionUpdate>(null)
  const visibleUpdate =
    update?.state === "pending" && update.mode === permissionMode
      ? null
      : update

  const requestChange = async (mode: AgentPermissionMode) => {
    if (
      activeRun ||
      visibleUpdate?.state === "pending" ||
      mode === permissionMode
    ) {
      return
    }
    setUpdate({ mode, state: "pending" })
    try {
      await onPermissionModeChange(mode)
    } catch {
      setUpdate({ mode, state: "error" })
    }
  }

  const CurrentIcon = modeIcons[permissionMode]
  const isUpdating = visibleUpdate?.state === "pending"
  return (
    <div className="flex min-w-0 flex-col items-start gap-1.5">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={activeRun || isUpdating}
            aria-label={`${t("permission.label")}: ${t(`permission.${permissionMode}.name`)}`}
            aria-describedby={descriptionId}
          >
            {isUpdating ? (
              <Loader2 aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
            ) : (
              <CurrentIcon aria-hidden="true" />
            )}
            <span>{t(`permission.${permissionMode}.name`)}</span>
            <ChevronDown aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" side="top" className="w-[min(24rem,calc(100vw-2rem))]">
          <DropdownMenuLabel>{t("permission.title")}</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={permissionMode}
            onValueChange={(value) => {
              if (isPermissionMode(value)) void requestChange(value)
            }}
          >
            {modes.map((mode) => {
              const Icon = modeIcons[mode]
              return (
                <DropdownMenuRadioItem
                  key={mode}
                  value={mode}
                  disabled={isUpdating}
                  className={cn(
                    "items-start py-2.5",
                    mode === "full_access" && "text-warning-foreground",
                  )}
                >
                  <Icon aria-hidden="true" className="mt-0.5" />
                  <span className="grid min-w-0 gap-0.5">
                    <span className="font-medium">{t(`permission.${mode}.name`)}</span>
                    <span className="whitespace-normal text-xs leading-5 text-muted-foreground">
                      {t(`permission.${mode}.description`)}
                    </span>
                  </span>
                </DropdownMenuRadioItem>
              )
            })}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      <div id={descriptionId} className="text-xs leading-5 text-muted-foreground">
        {activeRun ? <p>{t("permission.activeRun")}</p> : null}
        {workspaceAccess === "read_only" ? (
          <p>{t("permission.readOnlyWorkspace")}</p>
        ) : null}
        {isUpdating ? <p role="status">{t("permission.updating")}</p> : null}
        {visibleUpdate?.state === "error" ? (
          <div className="flex flex-wrap items-center gap-2" role="alert">
            <span>{t("permission.updateError")}</span>
            <Button
              type="button"
              variant="link"
              size="sm"
              onClick={() => void requestChange(visibleUpdate.mode)}
            >
              {t("permission.retry")}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function isPermissionMode(value: string): value is AgentPermissionMode {
  return modes.some((mode) => mode === value)
}

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
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { useIsMobile } from "@/hooks/use-media-query"
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
  disabled?: boolean
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
  disabled = false,
  onPermissionModeChange,
}: PermissionMenuProps) {
  const t = useTranslations("agentComposer")
  const tCommon = useTranslations("common")
  const descriptionId = useId()
  const [update, setUpdate] = useState<PermissionUpdate>(null)
  const [mobileOpen, setMobileOpen] = useState(false)
  const isMobile = useIsMobile()
  const readOnlyWorkspace = workspaceAccess === "read_only"
  const visibleUpdate =
    update?.state === "pending" && update.mode === permissionMode
      ? null
      : update

  const requestChange = async (mode: AgentPermissionMode) => {
    if (
      activeRun ||
      disabled ||
      readOnlyWorkspace ||
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
  const controlsDisabled =
    disabled || activeRun || readOnlyWorkspace || isUpdating
  const trigger = (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      disabled={controlsDisabled}
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
  )

  const selectMode = (mode: AgentPermissionMode) => {
    setMobileOpen(false)
    void requestChange(mode)
  }

  return (
    <div className="flex min-w-0 flex-col items-start gap-1.5">
      {isMobile ? (
        <Sheet
          open={mobileOpen}
          onOpenChange={(open) => {
            if (!open || !controlsDisabled) setMobileOpen(open)
          }}
        >
          <SheetTrigger asChild>{trigger}</SheetTrigger>
          <SheetContent
            side="bottom"
            closeLabel={tCommon("close")}
            className="max-h-[85svh] rounded-t-2xl"
          >
            <SheetHeader className="border-b pr-12">
              <SheetTitle>{t("permission.title")}</SheetTitle>
              <SheetDescription>
                {t(`permission.${permissionMode}.description`)}
              </SheetDescription>
            </SheetHeader>
            <div
              role="group"
              aria-label={t("permission.title")}
              className="grid gap-2 overflow-y-auto overscroll-contain px-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
            >
              {modes.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  aria-pressed={mode === permissionMode}
                  disabled={controlsDisabled}
                  onClick={() => selectMode(mode)}
                  className={cn(
                    "flex min-h-16 w-full items-start gap-3 rounded-xl border px-4 py-3 text-left transition-colors",
                    "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] focus-visible:outline-none",
                    mode === permissionMode && "border-primary/40 bg-accent",
                    mode === "full_access" && "text-warning-foreground",
                    controlsDisabled && "cursor-not-allowed opacity-50",
                  )}
                >
                  <PermissionOptionContent mode={mode} />
                </button>
              ))}
            </div>
          </SheetContent>
        </Sheet>
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            side="top"
            className="w-[min(24rem,calc(100vw-2rem))]"
          >
            <DropdownMenuLabel>{t("permission.title")}</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              value={permissionMode}
              onValueChange={(value) => {
                if (isPermissionMode(value)) selectMode(value)
              }}
            >
              {modes.map((mode) => (
                <DropdownMenuRadioItem
                  key={mode}
                  value={mode}
                  disabled={controlsDisabled}
                  className={cn(
                    "items-start py-2.5",
                    mode === "full_access" && "text-warning-foreground",
                  )}
                >
                  <PermissionOptionContent mode={mode} />
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      <div id={descriptionId} className="text-xs leading-5 text-muted-foreground">
        {activeRun ? <p>{t("permission.activeRun")}</p> : null}
        {readOnlyWorkspace ? (
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

function PermissionOptionContent({ mode }: { mode: AgentPermissionMode }) {
  const t = useTranslations("agentComposer")
  const Icon = modeIcons[mode]

  return (
    <>
      <Icon aria-hidden="true" className="mt-0.5" />
      <span className="grid min-w-0 gap-0.5">
        <span className="font-medium">{t(`permission.${mode}.name`)}</span>
        <span className="whitespace-normal text-xs leading-5 text-muted-foreground">
          {t(`permission.${mode}.description`)}
        </span>
      </span>
    </>
  )
}

function isPermissionMode(value: string): value is AgentPermissionMode {
  return modes.some((mode) => mode === value)
}

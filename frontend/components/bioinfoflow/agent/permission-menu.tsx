"use client"

import { useId, useState } from "react"
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
  ConversationPermissionMode,
  ConversationWorkspaceAccess,
} from "@/lib/agent/conversation-model/types"
import { cn } from "@/lib/utils"

type PermissionMenuProps = {
  permissionMode: ConversationPermissionMode
  workspaceAccess: ConversationWorkspaceAccess
  disabled?: boolean
  onPermissionModeChange: (mode: ConversationPermissionMode) => Promise<void>
}

type PermissionUpdate = {
  mode: ConversationPermissionMode
  state: "pending" | "error"
} | null

const modes = ["ask_changes", "ask_dangerous", "full_access"] as const

const modeIcons = {
  ask_changes: ShieldQuestion,
  ask_dangerous: ShieldCheck,
  full_access: ShieldAlert,
} satisfies Record<ConversationPermissionMode, typeof ShieldQuestion>

export function PermissionMenu({
  permissionMode,
  workspaceAccess,
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
  const displayedMode =
    visibleUpdate?.state === "pending" ? visibleUpdate.mode : permissionMode

  const requestChange = async (mode: ConversationPermissionMode) => {
    if (
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

  const CurrentIcon = modeIcons[displayedMode]
  const isUpdating = visibleUpdate?.state === "pending"
  const controlsDisabled = disabled || readOnlyWorkspace || isUpdating
  const feedback = readOnlyWorkspace ? (
    <p>{t("permission.readOnlyWorkspace")}</p>
  ) : isUpdating ? (
    <p role="status">{t("permission.updating")}</p>
  ) : visibleUpdate?.state === "error" ? (
    <div className="flex flex-wrap items-center gap-2" role="alert">
      <span>{t("permission.updateError")}</span>
      <Button
        type="button"
        variant="link"
        size="sm"
        className="h-auto px-1 text-[11px]"
        onClick={() => void requestChange(visibleUpdate.mode)}
      >
        {t("permission.retry")}
      </Button>
    </div>
  ) : null
  const trigger = (
    <ComposerSelectorTrigger
      type="button"
      variant="ghost"
      size="sm"
      disabled={controlsDisabled}
      aria-label={`${t("permission.label")}: ${t(`permission.${displayedMode}.name`)}`}
      aria-describedby={feedback ? descriptionId : undefined}
      className="max-w-[12rem]"
    >
      <ComposerSelectorIconSlot>
        {isUpdating ? (
          <Loader2
            aria-hidden="true"
            className="animate-spin motion-reduce:animate-none"
          />
        ) : (
          <CurrentIcon aria-hidden="true" />
        )}
      </ComposerSelectorIconSlot>
      <ComposerSelectorText>
        {t(`permission.${displayedMode}.name`)}
      </ComposerSelectorText>
      <ComposerSelectorChevronSlot>
        <ChevronDown
          aria-hidden="true"
          className={composerSelectorChevronClassName}
        />
      </ComposerSelectorChevronSlot>
    </ComposerSelectorTrigger>
  )

  const selectMode = (mode: ConversationPermissionMode) => {
    setMobileOpen(false)
    void requestChange(mode)
  }

  return (
    <ComposerSelectorField feedback={feedback} feedbackId={descriptionId}>
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
                {t(`permission.${displayedMode}.description`)}
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
                  aria-pressed={mode === displayedMode}
                  disabled={controlsDisabled}
                  onClick={() => selectMode(mode)}
                  className={cn(
                    "flex min-h-16 w-full items-start gap-3 rounded-xl border px-4 py-3 text-left transition-colors",
                    "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] focus-visible:outline-none",
                    mode === displayedMode && "border-primary/40 bg-accent",
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
          <ComposerSelectorMenuSurface
            kind="dropdown"
            align="start"
            side="top"
            className="w-[244px]"
          >
            <div className={composerSelectorMenuHeaderClassName}>
              {t("permission.title")}
            </div>
            <DropdownMenuRadioGroup
              value={displayedMode}
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
                    composerSelectorMenuItemClassName,
                    "items-start pl-8 pr-2",
                    mode === "full_access" && "text-warning-foreground",
                  )}
                >
                  <PermissionOptionContent mode={mode} />
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </ComposerSelectorMenuSurface>
        </DropdownMenu>
      )}

    </ComposerSelectorField>
  )
}

function PermissionOptionContent({
  mode,
}: {
  mode: ConversationPermissionMode
}) {
  const t = useTranslations("agentComposer")
  const Icon = modeIcons[mode]

  return (
    <ComposerSelectorOptionContent
      icon={<Icon aria-hidden="true" />}
      title={t(`permission.${mode}.name`)}
      description={t(`permission.${mode}.description`)}
    />
  )
}

function isPermissionMode(value: string): value is ConversationPermissionMode {
  return modes.some((mode) => mode === value)
}

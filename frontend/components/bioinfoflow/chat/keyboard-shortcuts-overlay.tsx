"use client"

import { useTranslations } from "next-intl"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface KeyboardShortcutsOverlayProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const SHORTCUTS = [
  { keys: ["⌘", "K"], labelKey: "focusInput" },
  { keys: ["⌘", "."], labelKey: "stopGeneration" },
  { keys: ["⌘", "⇧", "B"], labelKey: "toggleSidebar" },
  { keys: ["⌘", "⇧", "N"], labelKey: "newConversation" },
  { keys: ["Enter"], labelKey: "sendMessage" },
  { keys: ["⇧", "Enter"], labelKey: "newLine" },
  { keys: ["Esc"], labelKey: "cancelOrClose" },
  { keys: ["?"], labelKey: "showShortcuts" },
] as const

type ShortcutLabelKey = (typeof SHORTCUTS)[number]["labelKey"]

export function KeyboardShortcutsOverlay({
  open,
  onOpenChange,
}: KeyboardShortcutsOverlayProps) {
  const t = useTranslations("chat.shortcuts")

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription className="sr-only">
            {t("showShortcuts")}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {SHORTCUTS.map(({ keys, labelKey }) => (
            <div key={labelKey} className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {t(labelKey satisfies ShortcutLabelKey)}
              </span>
              <div className="flex items-center gap-1">
                {keys.map((key) => (
                  <kbd
                    key={key}
                    className="inline-flex h-5 min-w-[20px] items-center justify-center rounded border border-border bg-muted px-1.5 text-[10px] font-medium text-muted-foreground"
                  >
                    {key}
                  </kbd>
                ))}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[10px] text-muted-foreground/60 text-center">
          {t("toggleHint")}
        </p>
      </DialogContent>
    </Dialog>
  )
}

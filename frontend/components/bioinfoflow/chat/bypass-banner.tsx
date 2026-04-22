"use client"

import { Zap, X } from "lucide-react"
import { useTranslations } from "next-intl"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

interface BypassBannerProps {
  visible: boolean
  onDisable: () => void
  className?: string
}

/**
 * Banner shown at the top of the chat when execution_policy="bypass".
 * Makes the "dangerous" mode visible at all times so the user doesn't
 * forget they've opted out of approval prompts.
 */
export function BypassBanner({ visible, onDisable, className }: BypassBannerProps) {
  const t = useTranslations("executionMode")

  if (!visible) return null

  return (
    <div
      role="status"
      className={cn(
        "flex items-center gap-2.5 border-b border-amber-500/30",
        "bg-amber-500/10 px-4 py-2 text-xs",
        "text-amber-700 dark:text-amber-300",
        className,
      )}
    >
      <Zap className="h-3.5 w-3.5 shrink-0" aria-hidden />
      <div className="flex-1 leading-snug">
        <span className="font-medium">{t("bypassBannerTitle")}</span>
        <span className="ml-1.5 text-amber-700/80 dark:text-amber-300/80">
          {t("bypassBannerDescription")}
        </span>
      </div>
      <Button
        size="sm"
        variant="ghost"
        className="h-6 px-2 text-xs text-amber-800 hover:bg-amber-500/20 dark:text-amber-200"
        onClick={onDisable}
      >
        <X className="h-3 w-3 mr-1" />
        {t("bypassBannerDisable")}
      </Button>
    </div>
  )
}

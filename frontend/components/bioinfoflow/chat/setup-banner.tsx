"use client"

import { useState } from "react"
import { useTranslations } from "next-intl"
import Link from "next/link"
import { ArrowRight, X, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"

interface SetupBannerProps {
  className?: string
}

export function SetupBanner({ className }: SetupBannerProps) {
  const t = useTranslations("settings.setupBanner")
  const [dismissed, setDismissed] = useState(false)

  if (dismissed) return null

  return (
    <div
      className={`mx-auto max-w-3xl w-full ${className || ""}`}
    >
      <div className="flex items-center gap-3 rounded-xl border border-amber-500/20 bg-amber-50/50 dark:bg-amber-950/20 px-4 py-3 text-sm">
        <Zap className="h-4 w-4 text-amber-500 shrink-0" />
        <span className="flex-1 text-foreground/80">{t("title")}</span>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400 hover:bg-amber-100 dark:hover:bg-amber-900/30"
          asChild
        >
          <Link href="/settings">
            {t("action")}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="text-muted-foreground hover:text-foreground transition-colors"
          aria-label={t("dismiss")}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

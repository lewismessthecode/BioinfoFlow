"use client"

import { useState } from "react"
import { X, ArrowRight } from "@/lib/icons"
import { useTranslations } from "next-intl"

export function AnnouncementBar() {
  const [isVisible, setIsVisible] = useState(true)
  const t = useTranslations("landing.announcement")

  if (!isVisible) return null

  return (
    <div className="bg-[var(--announcement-bg)] text-[var(--announcement-fg)] h-10 flex items-center justify-center text-sm relative">
      <a
        href="#"
        className="flex items-center gap-2 hover:opacity-80 transition-opacity"
      >
        <span className="font-medium">{t("text")}</span>
        <ArrowRight className="w-4 h-4" />
      </a>
      <button
        onClick={() => setIsVisible(false)}
        className="absolute right-4 p-1 hover:opacity-80 transition-opacity"
        aria-label={t("dismiss")}
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}

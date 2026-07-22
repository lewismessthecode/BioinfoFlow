"use client"

import { useState } from "react"
import { X, ArrowRight } from "@/lib/icons"
import { useTranslations } from "next-intl"

export function AnnouncementBar() {
  const [isVisible, setIsVisible] = useState(true)
  const t = useTranslations("landing.announcement")

  if (!isVisible) return null

  return (
    <div className="relative flex h-9 items-center justify-center border-b border-white/10 bg-[#191919] px-12 text-white dark:bg-[#09090b] dark:text-[#e4e4e7]">
      <a
        href="https://github.com/lewismessthecode/BioinfoFlow"
        target="_blank"
        rel="noreferrer"
        className="flex items-center gap-2 text-xs transition-opacity hover:opacity-75"
      >
        <span className="size-1.5 rounded-full bg-[var(--brand-accent)]" />
        <span className="font-medium">{t("text")}</span>
        <ArrowRight className="size-3.5" />
      </a>
      <button
        onClick={() => setIsVisible(false)}
        className="absolute right-4 p-1 transition-opacity hover:opacity-70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
        aria-label={t("dismiss")}
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}

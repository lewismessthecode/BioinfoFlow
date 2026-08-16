"use client"

import { useEffect, useState } from "react"
import { useTranslations } from "next-intl"

import { Loader2 } from "@/lib/icons"
import { useReducedMotionPreference } from "@/lib/celebrations"

const SPINNER_VERB_KEYS = [
  "tracing_clues",
  "diving_deeper",
  "connecting_context",
  "checking_details",
  "following_evidence",
  "untangling_problem",
  "fitting_pieces",
  "moving_forward",
] as const

const SPINNER_VERB_ROTATION_MS = 3200

export function AgentLiveStatus() {
  const t = useTranslations("agentRun")
  const reducedMotion = useReducedMotionPreference()
  const [verbIndex, setVerbIndex] = useState(0)

  useEffect(() => {
    if (reducedMotion) return

    const interval = window.setInterval(() => {
      setVerbIndex((index) => (index + 1) % SPINNER_VERB_KEYS.length)
    }, SPINNER_VERB_ROTATION_MS)

    return () => window.clearInterval(interval)
  }, [reducedMotion])

  const visibleVerbIndex = reducedMotion ? 0 : verbIndex

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-9 items-center gap-2 text-sm text-muted-foreground"
      data-testid="agent-live-status"
    >
      <Loader2
        aria-hidden="true"
        className="size-4 shrink-0 animate-spin motion-reduce:animate-none"
      />
      <span
        key={SPINNER_VERB_KEYS[visibleVerbIndex]}
        aria-hidden="true"
        className="animate-in fade-in duration-300 motion-reduce:animate-none"
        data-testid="agent-spinner-verb"
      >
        {t(`spinner.${SPINNER_VERB_KEYS[visibleVerbIndex]}`)}
      </span>
      <span className="sr-only">{t("spinner.announcement")}</span>
    </div>
  )
}

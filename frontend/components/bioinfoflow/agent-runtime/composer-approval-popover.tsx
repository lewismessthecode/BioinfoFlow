"use client"

import { useMemo } from "react"
import { AlertTriangle } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeEvent } from "@/lib/agent-runtime"
import { getActionDecisionCards } from "./pending-actions"

export function ComposerApprovalPopover({
  events,
}: {
  events: AgentRuntimeEvent[]
}) {
  const t = useTranslations("agentRuntime")
  const cards = useMemo(() => getActionDecisionCards(events), [events])
  const pending = cards.find((card) => card.state === "pending") ?? null

  if (!pending) return null

  const jumpToDecision = () => {
    document.getElementById(pending.scrollTargetId)?.scrollIntoView({
      block: "center",
      behavior: "smooth",
    })
  }

  return (
    <div className="mb-2 flex justify-center" data-testid="composer-approval-popover">
      <button
        type="button"
        className="inline-flex items-center gap-2 rounded-[8px] border border-[#FBF3DB] bg-[#FBF3DB]/70 px-3 py-1.5 text-xs font-medium text-[#956400] shadow-none hover:bg-[#FBF3DB] dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-100"
        data-testid="composer-decision-jump"
        onClick={jumpToDecision}
      >
        <AlertTriangle className="h-3.5 w-3.5" />
        {t("approval.jumpToDecision")}
      </button>
    </div>
  )
}

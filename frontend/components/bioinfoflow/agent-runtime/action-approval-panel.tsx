"use client"

import { Check, ShieldAlert, X } from "lucide-react"
import { useMemo } from "react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type { AgentRuntimeEvent } from "@/lib/agent-runtime"

export function ActionApprovalPanel({
  events,
  onDecision,
}: {
  events: AgentRuntimeEvent[]
  onDecision: (actionId: string, decision: "approve" | "reject") => void
}) {
  const t = useTranslations("agentRuntime")
  const pendingActions = useMemo(() => {
    const completed = new Set(
      events
        .filter((event) =>
          ["action.completed", "action.failed", "action.decision_recorded"].includes(
            event.type,
          ),
        )
        .map((event) => String(event.payload.action_id || "")),
    )
    return events
      .filter((event) => event.type === "action.waiting_decision")
      .filter((event) => {
        const actionId = String(event.payload.action_id || "")
        return actionId && !completed.has(actionId)
      })
  }, [events])

  return (
    <section className="border-b border-border px-4 py-4">
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-normal text-muted-foreground">
        <ShieldAlert className="h-3.5 w-3.5" />
        {t("approvals")}
      </div>
      {pendingActions.length === 0 ? (
        <p className="text-xs leading-5 text-muted-foreground">{t("noApprovals")}</p>
      ) : (
        <div className="grid gap-3">
          {pendingActions.map((event) => {
            const actionId = String(event.payload.action_id || "")
            return (
              <div key={event.id} className="border border-amber-500/30 bg-amber-500/5 p-3">
                <div className="mb-3 text-xs leading-5 text-amber-800 dark:text-amber-200">
                  <span className="font-mono">{actionId}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={() => onDecision(actionId, "approve")}>
                    <Check className="h-3.5 w-3.5" />
                    {t("approve")}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onDecision(actionId, "reject")}
                  >
                    <X className="h-3.5 w-3.5" />
                    {t("reject")}
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

"use client"

import { AlertTriangle, CheckCircle2, CircleDashed } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeTurn } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function AgentTranscript({ turns }: { turns: AgentRuntimeTurn[] }) {
  const t = useTranslations("agentRuntime")

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-36 pt-8 sm:px-6">
      <div className="mx-auto grid w-full max-w-3xl gap-8">
        {turns.map((turn) => (
          <article key={turn.id} className="grid gap-4">
            <div className="flex justify-end">
              <div className="max-w-[82%] rounded-[22px] bg-muted px-4 py-3 text-[15px] leading-6 text-foreground">
                {turn.input_text}
              </div>
            </div>
            <div className="flex justify-start">
              <div className="w-full max-w-[88%] px-1">
                <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                  <TurnStatusIcon status={turn.status} />
                  <span>{turnStatusLabel(t, turn.status)}</span>
                </div>
                <p
                  className={cn(
                    "whitespace-pre-wrap break-words text-[15px] leading-7 text-foreground",
                    turn.status === "failed" && "text-destructive",
                  )}
                >
                  {turn.final_text || turn.error_message || t("pendingResponse")}
                </p>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function turnStatusLabel(
  t: (key: string) => string,
  status: AgentRuntimeTurn["status"],
) {
  switch (status) {
    case "queued":
      return t("turnStatus.queued")
    case "running":
      return t("turnStatus.running")
    case "waiting_user":
      return t("turnStatus.waiting_user")
    case "waiting_approval":
      return t("turnStatus.waiting_approval")
    case "completed":
      return t("turnStatus.completed")
    case "failed":
      return t("turnStatus.failed")
    case "cancelled":
      return t("turnStatus.cancelled")
  }
}

function TurnStatusIcon({ status }: { status: AgentRuntimeTurn["status"] }) {
  if (status === "completed") {
    return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
  }
  if (status === "failed" || status === "cancelled") {
    return <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
  }
  return <CircleDashed className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
}

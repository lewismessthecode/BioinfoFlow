"use client"

import { AlertTriangle, CheckCircle2, CircleDashed } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeTurn } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function TurnStream({ turns }: { turns: AgentRuntimeTurn[] }) {
  const t = useTranslations("agentRuntime")
  if (turns.length === 0) {
    return (
      <div className="flex min-h-[280px] items-center justify-center text-center">
        <div className="max-w-sm">
          <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center border border-border bg-background">
            <CircleDashed className="h-5 w-5 text-muted-foreground" />
          </div>
          <h2 className="text-base font-semibold text-foreground">{t("emptyTitle")}</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {t("emptyDescription")}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto grid w-full max-w-4xl gap-6 py-6">
      {turns.map((turn) => (
        <article key={turn.id} className="grid gap-3">
          <div className="flex justify-end">
            <div className="max-w-[82%] border border-border bg-muted/45 px-4 py-3 text-sm leading-6 text-foreground">
              {turn.input_text}
            </div>
          </div>
          <div className="flex justify-start">
            <div className="w-full max-w-[86%] px-1 py-1">
              <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                <TurnStatusIcon status={turn.status} />
                <span className="font-mono">{turn.status}</span>
                {turn.termination_reason ? (
                  <span className="font-mono">{turn.termination_reason}</span>
                ) : null}
              </div>
              <p
                className={cn(
                  "whitespace-pre-wrap break-words text-sm leading-7 text-foreground",
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
  )
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

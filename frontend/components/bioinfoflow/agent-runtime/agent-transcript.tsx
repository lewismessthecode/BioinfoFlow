"use client"

import { AlertTriangle, CheckCircle2, ChevronDown, CircleDashed, Wrench } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeTimelineEntry, AgentRuntimeTurn } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function AgentTranscript({ timeline }: { timeline: AgentRuntimeTimelineEntry[] }) {
  const t = useTranslations("agentRuntime")

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-36 pt-8 sm:px-6">
      <div className="mx-auto grid w-full max-w-3xl gap-8">
        {timeline.map((entry) => (
          <article key={entry.turn.id} className="grid gap-4">
            <div className="flex justify-end">
              <div className="max-w-[82%] rounded-[22px] bg-muted px-4 py-3 text-[15px] leading-6 text-foreground">
                {entry.turn.input_text}
              </div>
            </div>
            <div className="flex justify-start">
              <div className="w-full max-w-[88%] px-1">
                <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                  <TurnStatusIcon status={entry.turn.status} />
                  <span>{turnStatusLabel(t, entry.turn.status)}</span>
                </div>

                {entry.assistant.thinking?.content ? (
                  <details className="mb-3 rounded-2xl border border-border/70 bg-muted/30 px-3 py-2">
                    <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-foreground">
                      <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
                      <span>{t("thinking")}</span>
                    </summary>
                    <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
                      {entry.assistant.thinking.content}
                    </p>
                  </details>
                ) : null}

                {entry.assistant.toolCalls.length > 0 ? (
                  <div className="mb-3 grid gap-2">
                    {entry.assistant.toolCalls.map((toolCall) => (
                      <div
                        key={toolCall.callId}
                        className="rounded-2xl border border-border/70 bg-card px-3 py-3"
                      >
                        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                          <Wrench className="h-4 w-4 text-muted-foreground" />
                          <span>{toolCall.name}</span>
                        </div>
                        {toolCall.arguments ? (
                          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words rounded-xl bg-muted/50 px-3 py-2 text-xs leading-5 text-muted-foreground">
                            {JSON.stringify(toolCall.arguments, null, 2)}
                          </pre>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}

                <p
                  className={cn(
                    "whitespace-pre-wrap break-words text-[15px] leading-7 text-foreground",
                    entry.assistant.status === "failed" && "text-destructive",
                  )}
                >
                  {entry.assistant.text ||
                    entry.assistant.errorMessage ||
                    t("pendingResponse")}
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

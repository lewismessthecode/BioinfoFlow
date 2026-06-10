"use client"

import { useMemo } from "react"
import { Check, FileText, Wrench, X } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type { AgentRuntimeEvent, AgentRuntimeTimelineEntry } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

type RuntimeSidecarProps = {
  events: AgentRuntimeEvent[]
  timeline: AgentRuntimeTimelineEntry[]
  isRunning: boolean
  onClose: () => void
  onDecision: (actionId: string, decision: "approve" | "reject") => void
  className?: string
}

export function RuntimeSidecar({
  events,
  timeline,
  isRunning,
  onClose,
  onDecision,
  className,
}: RuntimeSidecarProps) {
  const t = useTranslations("agentRuntime")
  const pendingActions = usePendingActions(events)
  const currentEntry = timeline.at(-1) ?? null
  const artifactEvents = useMemo(
    () => events.filter((event) => event.type === "artifact.created").slice(-5).reverse(),
    [events],
  )

  return (
    <aside
      className={cn(
        "pointer-events-auto hidden h-[calc(100%-32px)] w-[380px] overflow-hidden rounded-[26px] border border-border/70 bg-card shadow-2xl shadow-foreground/10 lg:flex lg:flex-col",
        className,
      )}
      data-testid="runtime-sidecar"
    >
      <div className="flex h-14 items-center justify-between border-b border-border/60 px-4">
        <div className="text-sm font-medium text-foreground">{t("sidecar.title")}</div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={onClose}
          aria-label={t("sidecar.close")}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {pendingActions.length > 0 ? (
          <div className="mb-4 grid gap-3">
            {pendingActions.map((event) => {
              const actionId = String(event.payload.action_id || "")
              return (
                <div
                  key={event.id}
                  className="rounded-[18px] border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-sm"
                >
                  <div className="mb-2 font-medium text-amber-900 dark:text-amber-200">
                    {t("sidecar.needsDecision")}
                  </div>
                  <div className="mb-3 truncate font-mono text-xs text-amber-800/75 dark:text-amber-100/75">
                    {actionId}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      className="h-8 rounded-full"
                      onClick={() => onDecision(actionId, "approve")}
                    >
                      <Check className="h-3.5 w-3.5" />
                      {t("approve")}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-8 rounded-full bg-card"
                      onClick={() => onDecision(actionId, "reject")}
                    >
                      {t("reject")}
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        ) : null}

        <div className="grid gap-4">
          <section className="rounded-[20px] border border-border/70 bg-muted/25 p-3">
            <div className="mb-2 text-xs font-medium text-muted-foreground">
              {t("sidecar.currentThinking")}
            </div>
            {currentEntry?.assistant.thinking?.content ? (
              <p className="whitespace-pre-wrap break-words text-sm leading-6 text-foreground">
                {currentEntry.assistant.thinking.content}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                {isRunning ? t("pendingResponse") : t("sidecar.noActivity")}
              </p>
            )}
          </section>

          <section className="rounded-[20px] border border-border/70 bg-muted/25 p-3">
            <div className="mb-2 text-xs font-medium text-muted-foreground">
              {t("sidecar.currentToolCalls")}
            </div>
            {currentEntry?.assistant.toolCalls.length ? (
              <div className="grid gap-2">
                {currentEntry.assistant.toolCalls.map((toolCall) => (
                  <div
                    key={toolCall.callId}
                    className="rounded-2xl border border-border/70 bg-card px-3 py-2"
                  >
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <Wrench className="h-4 w-4 text-muted-foreground" />
                      <span>{toolCall.name}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t("sidecar.noActivity")}</p>
            )}
          </section>

          <section className="rounded-[20px] border border-border/70 bg-muted/25 p-3">
            <div className="mb-2 text-xs font-medium text-muted-foreground">
              {t("sidecar.artifacts")}
            </div>
            {artifactEvents.length ? (
              <div className="grid gap-2">
                {artifactEvents.map((event) => (
                  <div
                    key={event.id}
                    className="rounded-2xl border border-border/70 bg-card px-3 py-2"
                  >
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span>{String(event.payload.title || event.payload.type || "Artifact")}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t("sidecar.noActivity")}</p>
            )}
          </section>
        </div>
      </div>
    </aside>
  )
}

export function hasPendingRuntimeAction(events: AgentRuntimeEvent[]) {
  return getPendingActions(events).length > 0
}

export function hasRuntimeActivity(events: AgentRuntimeEvent[]) {
  return events.some((event) =>
    [
      "assistant.text.delta",
      "assistant.text.completed",
      "assistant.thinking.delta",
      "assistant.thinking.completed",
      "assistant.tool_call.started",
      "assistant.tool_call.delta",
      "assistant.tool_call.completed",
      "action.requested",
      "action.waiting_decision",
      "action.started",
      "action.completed",
      "action.failed",
      "artifact.created",
    ].includes(event.type),
  )
}

function usePendingActions(events: AgentRuntimeEvent[]) {
  return useMemo(() => getPendingActions(events), [events])
}

function getPendingActions(events: AgentRuntimeEvent[]) {
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
}

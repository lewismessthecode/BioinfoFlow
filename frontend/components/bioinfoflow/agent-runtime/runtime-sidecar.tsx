"use client"

import { useMemo } from "react"
import {
  Check,
  ChevronRight,
  FileText,
  Folder,
  Play,
  TerminalSquare,
  Wrench,
  X,
} from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type { AgentRuntimeEvent } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

type RuntimeSidecarProps = {
  events: AgentRuntimeEvent[]
  isRunning: boolean
  onClose: () => void
  onDecision: (actionId: string, decision: "approve" | "reject") => void
  className?: string
}

export function RuntimeSidecar({
  events,
  isRunning,
  onClose,
  onDecision,
  className,
}: RuntimeSidecarProps) {
  const t = useTranslations("agentRuntime")
  const pendingActions = usePendingActions(events)
  const toolEvents = useMemo(
    () => events.filter((event) => event.type.startsWith("action.")),
    [events],
  )
  const artifactEvents = useMemo(
    () => events.filter((event) => event.type === "artifact.created"),
    [events],
  )
  const recentEvents = useMemo(
    () => events.filter((event) => event.visibility !== "internal").slice(-6).reverse(),
    [events],
  )

  const cards = [
    {
      label: t("sidecar.files"),
      value: String(countEvents(events, ["file.", "workspace."])),
      icon: Folder,
    },
    {
      label: t("sidecar.runs"),
      value: isRunning ? t("sidecar.active") : String(countEvents(events, ["turn."])),
      icon: Play,
    },
    {
      label: t("sidecar.tools"),
      value: String(toolEvents.length),
      icon: TerminalSquare,
    },
    {
      label: t("sidecar.artifacts"),
      value: String(artifactEvents.length),
      icon: FileText,
    },
  ]

  return (
    <aside
      className={cn(
        "pointer-events-auto hidden h-[calc(100%-32px)] w-[380px] overflow-hidden rounded-[26px] border border-border/70 bg-card shadow-2xl shadow-foreground/10 lg:flex lg:flex-col",
        className,
      )}
      data-testid="runtime-sidecar"
    >
      <div className="flex h-14 items-center justify-between border-b border-border/60 px-4">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-muted">
            <Wrench className="h-3.5 w-3.5" />
          </span>
          {t("sidecar.title")}
        </div>
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

        <div className="grid grid-cols-2 gap-2">
          {cards.map((card) => (
            <div
              key={card.label}
              className="rounded-[18px] border border-border/70 bg-muted/25 p-3"
            >
              <div className="mb-4 flex items-center justify-between">
                <card.icon className="h-4 w-4 text-muted-foreground" />
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60" />
              </div>
              <div className="text-sm font-medium text-foreground">{card.label}</div>
              <div className="mt-1 text-xs text-muted-foreground">{card.value}</div>
            </div>
          ))}
        </div>

        <div className="mt-5">
          <div className="mb-2 text-xs font-medium text-muted-foreground">
            {t("sidecar.progress")}
          </div>
          {recentEvents.length > 0 ? (
            <ol className="grid gap-2">
              {recentEvents.map((event) => (
                <li
                  key={event.id}
                  className="rounded-2xl border border-border/70 bg-background px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-xs font-medium text-foreground">
                      {formatEventTitle(event)}
                    </span>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      #{event.seq}
                    </span>
                  </div>
                  {event.payload.summary || event.payload.name || event.payload.title ? (
                    <p className="mt-1 truncate text-xs text-muted-foreground">
                      {String(
                        event.payload.summary ||
                          event.payload.name ||
                          event.payload.title,
                      )}
                    </p>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : (
            <div className="rounded-2xl border border-dashed border-border/70 px-3 py-5 text-center text-xs text-muted-foreground">
              {t("sidecar.noActivity")}
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}

export function hasPendingRuntimeAction(events: AgentRuntimeEvent[]) {
  return getPendingActions(events).length > 0
}

export function hasRuntimeActivity(events: AgentRuntimeEvent[]) {
  return events.some(
    (event) =>
      event.type.startsWith("action.") ||
      event.type.startsWith("memory.") ||
      event.type === "artifact.created" ||
      event.type.startsWith("turn."),
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

function countEvents(events: AgentRuntimeEvent[], prefixes: string[]) {
  return events.filter((event) =>
    prefixes.some((prefix) => event.type.startsWith(prefix)),
  ).length
}

function formatEventTitle(event: AgentRuntimeEvent) {
  return event.type
    .split(".")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

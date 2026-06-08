"use client"

import { Activity, Wrench } from "lucide-react"
import { useMemo } from "react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeEvent } from "@/lib/agent-runtime"

export function ToolActivityPanel({ events }: { events: AgentRuntimeEvent[] }) {
  const t = useTranslations("agentRuntime")
  const toolEvents = useMemo(
    () => events.filter((event) => event.type.startsWith("action.")),
    [events],
  )

  return (
    <section className="border-b border-border px-4 py-4">
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-normal text-muted-foreground">
        <Activity className="h-3.5 w-3.5" />
        {t("toolActivity")}
      </div>
      {toolEvents.length === 0 ? (
        <p className="text-xs leading-5 text-muted-foreground">{t("noToolActivity")}</p>
      ) : (
        <ol className="grid gap-2">
          {toolEvents.slice(-8).map((event) => (
            <li key={event.id} className="grid gap-1 border-l border-border pl-3">
              <div className="flex items-center gap-2 text-xs">
                <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-mono text-foreground">{event.type}</span>
                <span className="font-mono text-muted-foreground">#{event.seq}</span>
              </div>
              {typeof event.payload.name === "string" ? (
                <p className="text-xs text-muted-foreground">{event.payload.name}</p>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

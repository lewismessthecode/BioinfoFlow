"use client"

import { Brain } from "lucide-react"
import { useMemo } from "react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeEvent } from "@/lib/agent-runtime"

export function MemoryPanel({ events }: { events: AgentRuntimeEvent[] }) {
  const t = useTranslations("agentRuntime")
  const memoryEvents = useMemo(
    () => events.filter((event) => event.type.startsWith("memory.")),
    [events],
  )

  return (
    <section className="px-4 py-4">
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-normal text-muted-foreground">
        <Brain className="h-3.5 w-3.5" />
        {t("memory")}
      </div>
      {memoryEvents.length === 0 ? (
        <p className="text-xs leading-5 text-muted-foreground">{t("noMemory")}</p>
      ) : (
        <ol className="grid gap-2">
          {memoryEvents.slice(-6).map((event) => (
            <li key={event.id} className="text-xs leading-5">
              <span className="font-mono text-foreground">{event.type}</span>
              <span className="ml-2 font-mono text-muted-foreground">#{event.seq}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

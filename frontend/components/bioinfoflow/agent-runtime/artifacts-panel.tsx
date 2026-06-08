"use client"

import { FileText } from "lucide-react"
import { useMemo } from "react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeEvent } from "@/lib/agent-runtime"

export function ArtifactsPanel({ events }: { events: AgentRuntimeEvent[] }) {
  const t = useTranslations("agentRuntime")
  const artifacts = useMemo(
    () => events.filter((event) => event.type === "artifact.created"),
    [events],
  )

  return (
    <section className="border-b border-border px-4 py-4">
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-normal text-muted-foreground">
        <FileText className="h-3.5 w-3.5" />
        {t("artifacts")}
      </div>
      {artifacts.length === 0 ? (
        <p className="text-xs leading-5 text-muted-foreground">{t("noArtifacts")}</p>
      ) : (
        <div className="grid gap-2">
          {artifacts.slice(-6).map((event) => (
            <div key={event.id} className="text-xs leading-5">
              <div className="font-medium text-foreground">
                {String(event.payload.title || event.payload.type || t("artifact"))}
              </div>
              <div className="font-mono text-muted-foreground">
                {String(event.payload.artifact_id || "")}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

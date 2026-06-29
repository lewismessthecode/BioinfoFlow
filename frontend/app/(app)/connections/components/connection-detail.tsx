"use client"

import { TerminalSquare } from "lucide-react"
import { useTranslations } from "next-intl"

import type { RemoteConnection } from "@/lib/demo-connections"

import { TextPanel } from "./connection-ui"

type ConnectionDetailProps = {
  connection: RemoteConnection | null
  probing: boolean
  probeOutput: string
}

export function ConnectionDetail({
  connection,
  probing,
  probeOutput,
}: ConnectionDetailProps) {
  const t = useTranslations("connections")

  if (!connection || (!probeOutput && !probing)) return null

  return (
    <section className="shrink-0 border-t border-border/60 bg-card/70 p-3 sm:p-4">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <TerminalSquare className="h-3.5 w-3.5" />
        <span>{t("probe.description")}</span>
      </div>
      <div className="mt-2">
        <TextPanel
          title={t("probe.titleForConnection", { name: connection.name })}
          value={probeOutput || t("probe.placeholder")}
          empty={t("probe.placeholder")}
        />
      </div>
    </section>
  )
}

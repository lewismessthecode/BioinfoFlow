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
    <section className="rounded-[28px] border border-border/60 bg-card/85 p-4 shadow-sm shadow-foreground/5 sm:p-5">
      <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <TerminalSquare className="h-4 w-4" />
        <span>{t("probe.description")}</span>
      </div>
      <div className="mt-3">
        <TextPanel
          title={t("probe.titleForConnection", { name: connection.name })}
          value={probeOutput || t("probe.placeholder")}
          empty={t("probe.placeholder")}
        />
      </div>
    </section>
  )
}

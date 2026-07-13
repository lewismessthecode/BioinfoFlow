"use client"

import { useTranslations } from "next-intl"

import type { AgentDecisionTarget } from "@/lib/agent-runtime"

export function DecisionTargetBadge({ target }: { target?: AgentDecisionTarget | null }) {
  const t = useTranslations("agentRuntime")
  if (target?.kind !== "remote_ssh") return null
  const authority = [target.identity, target.trustDomain].filter(Boolean).join("@")
  const label = authority || target.connectionId
  if (!label) return null
  return (
    <span className="rounded-md border border-border/60 bg-background/65 px-1.5 py-0.5 text-[10px] text-muted-foreground">
      {t("approval.remoteTarget", { target: label })}
    </span>
  )
}

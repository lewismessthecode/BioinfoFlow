"use client"

import { ClipboardList } from "lucide-react"
import { useTranslations } from "next-intl"

import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import type { AgentRuntimeInlinePlan } from "@/lib/agent-runtime"

export function InlinePlanCard({ plan }: { plan: AgentRuntimeInlinePlan }) {
  const t = useTranslations("agentRuntime")

  return (
    <div
      className="mb-3 rounded-2xl border border-primary/25 bg-primary/5 px-3 py-3 text-sm"
      data-testid="inline-plan-card"
    >
      <div className="mb-2 flex items-center gap-2 font-medium text-foreground">
        <ClipboardList className="h-4 w-4 text-primary" />
        <span className="min-w-0 flex-1">{t("plan.reviewTitle")}</span>
        <span className="rounded-full bg-background/80 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {t(`plan.status.${plan.status}`)}
        </span>
      </div>
      <MarkdownRenderer
        className="max-h-80 overflow-auto rounded-xl border border-border/60 bg-card px-3 py-2 text-xs leading-6"
        content={plan.plan || "—"}
      />
    </div>
  )
}

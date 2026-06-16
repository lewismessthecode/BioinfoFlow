"use client"

import { useMemo } from "react"
import { AlertTriangle, CheckCircle2, ChevronDown, CircleDashed } from "lucide-react"
import { useTranslations } from "next-intl"

import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import type {
  AgentRuntimeArtifact,
  AgentRuntimeEvent,
  AgentRuntimeTimelineEntry,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"
import { ActivityGroup } from "./activity-group"
import { InlineApprovalCard } from "./inline-approval-card"
import { InlinePlanCard } from "./inline-plan-card"
import { InlineTodoCard } from "./inline-todo-card"
import { getActionDecisionCardsByTurn } from "./pending-actions"
import type { AgentDecisionHandler } from "./types"

export function AgentTranscript({
  timeline,
  artifacts = [],
  events = [],
  onDecision,
}: {
  timeline: AgentRuntimeTimelineEntry[]
  artifacts?: AgentRuntimeArtifact[]
  events?: AgentRuntimeEvent[]
  onDecision?: AgentDecisionHandler
}) {
  const t = useTranslations("agentRuntime")
  const todoArtifactByTurn = useMemo(() => latestTodoArtifactByTurn(artifacts), [artifacts])
  const decisionCardsByTurn = useMemo(
    () => getActionDecisionCardsByTurn(events),
    [events],
  )

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
                  <details
                    className="group mb-3 rounded-2xl border border-border/70 bg-muted/30 px-3 py-2"
                    open
                  >
                    <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-foreground">
                      <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
                      <span>{t("thinking")}</span>
                    </summary>
                    <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
                      {entry.assistant.thinking.content}
                    </p>
                  </details>
                ) : null}

                {entry.inlinePlans.map((plan) => (
                  <InlinePlanCard key={plan.actionId} plan={plan} />
                ))}

                {(decisionCardsByTurn.get(entry.turn.id) ?? []).map((decision) => (
                  <InlineApprovalCard
                    key={decision.actionId}
                    decision={decision}
                    onDecision={onDecision}
                  />
                ))}

                {entry.activityGroups.length > 0 ? (
                  <div className="mb-3 grid gap-2">
                    {entry.activityGroups.map((group) => (
                      <ActivityGroup key={group.id} group={group} />
                    ))}
                  </div>
                ) : null}

                {todoArtifactByTurn.get(entry.turn.id) ? (
                  <InlineTodoCard artifact={todoArtifactByTurn.get(entry.turn.id)!} />
                ) : null}

                {entry.assistant.text ? (
                  <MarkdownRenderer
                    className="text-[15px] leading-7"
                    content={entry.assistant.text}
                  />
                ) : entry.assistant.errorMessage ? (
                  <div className="flex items-start gap-2 rounded-2xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm leading-6 text-destructive">
                    <AlertTriangle className="mt-1 h-4 w-4 shrink-0" />
                    <span className="break-words">{entry.assistant.errorMessage}</span>
                  </div>
                ) : (
                  <MarkdownRenderer
                    className="text-[15px] leading-7"
                    content={t("pendingResponse")}
                  />
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function latestTodoArtifactByTurn(artifacts: AgentRuntimeArtifact[]) {
  const byTurn = new Map<string, AgentRuntimeArtifact>()
  for (const artifact of artifacts) {
    if (artifact.type !== "todo_list") continue
    const current = byTurn.get(artifact.turn_id)
    if (!current || current.created_at < artifact.created_at) {
      byTurn.set(artifact.turn_id, artifact)
    }
  }
  return byTurn
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

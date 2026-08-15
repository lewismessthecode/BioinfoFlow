"use client"

import { useId, useMemo } from "react"
import { useTranslations } from "next-intl"

import {
  AgentActivityGroup,
  AgentToolCard,
} from "@/components/bioinfoflow/agent/agent-activity"
import { AgentThinking } from "@/components/bioinfoflow/agent/agent-thinking"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { buildActiveActivity } from "@/lib/agent/activity"
import type {
  ActiveRunView,
  AssistantDraftPartView,
  ToolProgressView,
} from "@/lib/agent/contracts"

type ActiveRunProps = {
  activeRun: ActiveRunView
  durableToolCallIds?: ReadonlySet<string>
}

const EMPTY_DURABLE_TOOL_CALL_IDS = new Set<string>()

export function ActiveRun({
  activeRun,
  durableToolCallIds = EMPTY_DURABLE_TOOL_CALL_IDS,
}: ActiveRunProps) {
  const t = useTranslations("agentRun")
  const titleId = useId()
  const activity = useMemo(
    () =>
      buildActiveActivity(
        activeRun.assistant_draft?.parts ?? [],
        activeRun.tool_progress,
        durableToolCallIds,
      ),
    [
      activeRun.assistant_draft?.parts,
      activeRun.tool_progress,
      durableToolCallIds,
    ],
  )
  const finishedTools = activeRun.tool_progress.filter((tool) =>
    isFinished(tool.status),
  ).length
  const toolCount = activeRun.tool_progress.length
  const progressValue =
    toolCount === 0 ? 0 : Math.round((finishedTools / toolCount) * 100)

  return (
    <section
      aria-labelledby={titleId}
      className="grid min-w-0 gap-4 rounded-[12px] border border-border/70 bg-muted/15 px-3 py-3 sm:px-4 sm:py-4"
      data-testid="agent-active-run"
    >
      <header className="grid min-w-0 gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 id={titleId} className="text-sm font-medium text-foreground/85">
            {t("title")}
          </h2>
          <Badge variant="outline" role="status" aria-live="polite">
            {t(`status.${activeRun.run.status}`)}
          </Badge>
          {activeRun.run.phase ? (
            <span className="text-xs text-muted-foreground">
              {t(`phase.${activeRun.run.phase}`)}
            </span>
          ) : null}
        </div>

        {toolCount > 0 ? (
          <div className="grid gap-1.5">
            <div className="flex items-center justify-between gap-3 text-[11px] text-muted-foreground">
              <span>
                {t("progress.actions", {
                  completed: finishedTools,
                  total: toolCount,
                })}
              </span>
            </div>
            <Progress
              value={progressValue}
              aria-label={t("progress.label")}
              aria-valuetext={t("progress.actions", {
                completed: finishedTools,
                total: toolCount,
              })}
              className="h-1 bg-border/60"
            />
          </div>
        ) : null}
      </header>

      {activity.length > 0 ? (
        <div className="grid min-w-0 gap-2">
          {activity.map((item) => {
            if (item.kind === "thinking") {
              return (
                <AgentThinking
                  key={item.key}
                  active
                  label={t("reasoning")}
                  part={item.part}
                />
              )
            }

            if (item.kind === "response") {
              return (
                <section
                  key={item.key}
                  aria-label={t("response")}
                  aria-live="polite"
                  aria-atomic="false"
                  className="min-w-0"
                  data-activity-kind="response"
                >
                  <DraftPart part={item.part} />
                </section>
              )
            }

            return item.tools.length === 1 ? (
              <AgentToolCard
                key={item.key}
                tool={item.tools[0]}
                defaultExpanded={toolNeedsAttention(item.tools[0])}
              />
            ) : (
              <AgentActivityGroup
                key={item.key}
                tools={item.tools}
                executionMode={commonExecutionMode(item.tools)}
              />
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

function DraftPart({
  part,
}: {
  part: AssistantDraftPartView
}) {
  return (
    <div
      className="min-w-0"
      data-agent-read-anchor={`part:${part.id}`}
    >
      <MarkdownRenderer
        content={part.text}
      />
    </div>
  )
}

function commonExecutionMode(tools: ToolProgressView[]) {
  const first = tools[0].execution_mode
  return tools.every((tool) => tool.execution_mode === first) ? first : "mixed"
}

function isFinished(status: ToolProgressView["status"]) {
  return ["completed", "failed", "cancelled"].includes(status)
}

function toolNeedsAttention(tool: ToolProgressView) {
  return !["completed", "cancelled"].includes(tool.status)
}

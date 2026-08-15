"use client"

import { useId, useMemo } from "react"
import { useTranslations } from "next-intl"

import {
  AgentActivityGroup,
  AgentToolCard,
} from "@/components/bioinfoflow/agent/agent-activity"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import type {
  ActiveRunView,
  AssistantDraftPartView,
  ToolProgressView,
} from "@/lib/agent/contracts"

type ActiveRunProps = {
  activeRun: ActiveRunView
}

type ActivityBlock = {
  groupId: string
  tools: ToolProgressView[]
}

export function ActiveRun({ activeRun }: ActiveRunProps) {
  const t = useTranslations("agentRun")
  const titleId = useId()
  const reasoningId = useId()
  const responseId = useId()
  const draftParts = activeRun.assistant_draft?.parts ?? []
  const reasoningParts = draftParts.filter(isReasoningPart)
  const responseParts = draftParts.filter(isTextPart)
  const activityBlocks = useMemo(
    () => groupToolActivity(activeRun.tool_progress),
    [activeRun.tool_progress],
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

      {reasoningParts.length > 0 ? (
        <section
          aria-labelledby={reasoningId}
          className="grid min-w-0 gap-2 border-l-2 border-border/70 pl-3"
        >
          <h3
            id={reasoningId}
            className="text-xs font-medium text-muted-foreground"
          >
            {t("reasoning")}
          </h3>
          <DraftParts parts={reasoningParts} tone="muted" />
        </section>
      ) : null}

      {responseParts.length > 0 ? (
        <section
          aria-labelledby={responseId}
          aria-live="polite"
          aria-atomic="false"
          className="grid min-w-0 gap-2"
        >
          <h3 id={responseId} className="sr-only">
            {t("response")}
          </h3>
          <DraftParts parts={responseParts} />
        </section>
      ) : null}

      {activityBlocks.length > 0 ? (
        <div className="grid min-w-0 gap-2">
          {activityBlocks.map((block) =>
            block.tools.length === 1 ? (
              <AgentToolCard
                key={block.groupId}
                tool={block.tools[0]}
                defaultExpanded={toolNeedsAttention(block.tools[0])}
              />
            ) : (
              <AgentActivityGroup
                key={block.groupId}
                tools={block.tools}
                executionMode={commonExecutionMode(block.tools)}
              />
            ),
          )}
        </div>
      ) : null}
    </section>
  )
}

function DraftParts({
  parts,
  tone = "default",
}: {
  parts: AssistantDraftPartView[]
  tone?: "default" | "muted"
}) {
  return (
    <div className="grid min-w-0 gap-2">
      {parts.map((part) => (
        <div
          key={part.id}
          className="min-w-0"
          data-agent-read-anchor={`part:${part.id}`}
        >
          <MarkdownRenderer
            content={part.text}
            className={tone === "muted" ? "text-foreground/70" : undefined}
          />
        </div>
      ))}
    </div>
  )
}

function groupToolActivity(tools: ToolProgressView[]) {
  const blocks: ActivityBlock[] = []
  const byGroupId = new Map<string, ActivityBlock>()

  for (const tool of tools) {
    const existing = byGroupId.get(tool.group_id)
    if (existing) {
      existing.tools.push(tool)
      continue
    }

    const block = { groupId: tool.group_id, tools: [tool] }
    byGroupId.set(tool.group_id, block)
    blocks.push(block)
  }

  return blocks
}

function commonExecutionMode(tools: ToolProgressView[]) {
  const first = tools[0].execution_mode
  return tools.every((tool) => tool.execution_mode === first) ? first : "mixed"
}

function isReasoningPart(part: AssistantDraftPartView) {
  return part.type === "reasoning_summary"
}

function isTextPart(part: AssistantDraftPartView) {
  return part.type === "text"
}

function isFinished(status: ToolProgressView["status"]) {
  return ["completed", "failed", "cancelled"].includes(status)
}

function toolNeedsAttention(tool: ToolProgressView) {
  return !["completed", "cancelled"].includes(tool.status)
}

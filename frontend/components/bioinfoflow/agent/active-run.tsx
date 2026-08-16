"use client"

import { useId, useMemo } from "react"
import { useTranslations } from "next-intl"

import {
  AgentActivityGroup,
  AgentToolCard,
} from "@/components/bioinfoflow/agent/agent-activity"
import { AgentThinking } from "@/components/bioinfoflow/agent/agent-thinking"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { CircleDashed } from "@/lib/icons"
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
  return (
    <section
      aria-labelledby={titleId}
      className="grid min-w-0 gap-3 py-1 [content-visibility:auto] [contain-intrinsic-size:auto_144px]"
      data-testid="agent-active-run"
    >
      <h2 id={titleId} className="sr-only">
        {t("title")}
      </h2>

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

      <div
        role="status"
        aria-live="polite"
        className="flex min-h-7 min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground"
        data-testid="agent-active-run-status"
      >
        <CircleDashed
          aria-hidden="true"
          className="size-3.5 shrink-0 animate-spin text-muted-foreground/70 motion-reduce:animate-none"
        />
        <span>{t(`status.${activeRun.run.status}`)}</span>
        {activeRun.run.phase ? (
          <span className="before:mr-2 before:text-border before:content-['·']">
            {t(`phase.${activeRun.run.phase}`)}
          </span>
        ) : null}
        {toolCount > 0 ? (
          <span className="tabular-nums before:mr-2 before:text-border before:content-['·']">
            {t("progress.actions", {
              completed: finishedTools,
              total: toolCount,
            })}
          </span>
        ) : null}
      </div>
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

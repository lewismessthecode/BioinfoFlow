"use client"

import { useTranslations } from "next-intl"

import type { AgentLifecycleStatus, AgentTreeNode } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function AgentTree({ agents }: { agents: AgentTreeNode[] }) {
  const t = useTranslations("agentRuntime")

  if (!agents.length) {
    return <div className="text-xs text-muted-foreground">{t("agentTree.empty")}</div>
  }

  return (
    <div className="grid gap-1.5" data-testid="agent-tree">
      {agents.map((agent) => (
        <article
          key={agent.childSessionId}
          className="rounded-[8px] border border-border/60 bg-background/55 px-2.5 py-2"
          data-status={agent.status}
        >
          <div className="flex min-w-0 items-center gap-2">
            <span
              className={cn("h-1.5 w-1.5 shrink-0 rounded-full", statusDot(agent.status))}
              aria-hidden="true"
            />
            <code className="min-w-0 flex-1 truncate text-[11px] font-medium text-foreground" title={agent.taskPath}>
              {agent.taskPath}
            </code>
            <span className="shrink-0 text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
              {t(`agentTree.status.${agent.status}`)}
            </span>
          </div>

          {agent.effectiveModel ? (
            <div className="mt-1 truncate pl-3.5 font-mono text-[10px] text-muted-foreground" title={agent.effectiveModel}>
              {agent.effectiveModel}
            </div>
          ) : null}

          {agent.modelFallback ? (
            <div className="mt-1 pl-3.5 text-[11px] text-warning-foreground">
              {agent.requestedModel
                ? t("agentTree.modelFallback", {
                    requested: agent.requestedModel,
                    effective: agent.effectiveModel ?? t("environment.none"),
                  })
                : t("agentTree.modelFallbackGeneric", {
                    effective: agent.effectiveModel ?? t("environment.none"),
                  })}
            </div>
          ) : null}

          {agent.status === "errored" ? (
            <p className="mt-1 pl-3.5 text-xs leading-5 text-error-foreground" role="alert">
              {agent.errorMessage || t("agentTree.unknownError")}
            </p>
          ) : agent.status === "interrupted" ? (
            <p className="mt-1 pl-3.5 text-xs leading-5 text-muted-foreground" role="status">
              {agent.errorMessage || t("agentTree.interrupted")}
            </p>
          ) : agent.status === "completed" ? (
            <p className="mt-1 line-clamp-2 pl-3.5 text-xs leading-5 text-muted-foreground">
              {agent.finalText || t("agentTree.noFinalText")}
            </p>
          ) : null}
        </article>
      ))}
    </div>
  )
}

function statusDot(status: AgentLifecycleStatus) {
  switch (status) {
    case "completed":
      return "bg-success-foreground"
    case "errored":
      return "bg-error-foreground"
    case "interrupted":
      return "bg-muted-foreground"
    case "running":
      return "bg-primary"
    default:
      return "bg-warning-foreground"
  }
}

"use client"

import { useRef, useState, type KeyboardEvent } from "react"
import { AlertCircle, CheckCircle2, ChevronLeft, Circle, CircleDashed } from "@/lib/icons"
import { useTranslations } from "next-intl"

import type { AgentLifecycleStatus, AgentTreeNode } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function AgentWorkspace({
  agents,
  variant = "desktop",
}: {
  agents: AgentTreeNode[]
  variant?: "desktop" | "mobile"
}) {
  const t = useTranslations("agentRuntime")
  const [selectedId, setSelectedId] = useState<string | null>(agents[0]?.childSessionId ?? null)
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false)
  const rowRefs = useRef(new Map<string, HTMLButtonElement>())

  const selected = agents.find((agent) => agent.childSessionId === selectedId) ?? agents[0] ?? null

  if (!agents.length) {
    return (
      <div className="flex h-full min-h-48 items-center justify-center px-6 text-sm text-muted-foreground">
        {t("agentWorkspace.empty")}
      </div>
    )
  }

  const selectAgent = (agent: AgentTreeNode) => {
    setSelectedId(agent.childSessionId)
    if (variant === "mobile") setMobileDetailOpen(true)
  }
  const focusRow = (index: number) => {
    const agent = agents[index]
    if (!agent) return
    rowRefs.current.get(agent.childSessionId)?.focus()
  }
  const onRowKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === "ArrowDown") {
      event.preventDefault()
      focusRow(index === agents.length - 1 ? 0 : index + 1)
    } else if (event.key === "ArrowUp") {
      event.preventDefault()
      focusRow(index === 0 ? agents.length - 1 : index - 1)
    } else if (event.key === "Home") {
      event.preventDefault()
      focusRow(0)
    } else if (event.key === "End") {
      event.preventDefault()
      focusRow(agents.length - 1)
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      selectAgent(agents[index])
    }
  }

  const list = (
    <div
      className={cn(
        "min-h-0 overflow-y-auto",
        variant === "desktop" && "w-[min(42%,19rem)] shrink-0 border-r border-border/60",
      )}
      role="listbox"
      aria-label={t("agentWorkspace.listLabel")}
    >
      <div className="p-2">
        {agents.map((agent, index) => {
          const active = selected?.childSessionId === agent.childSessionId
          return (
            <button
              key={agent.childSessionId}
              ref={(node) => {
                if (node) rowRefs.current.set(agent.childSessionId, node)
                else rowRefs.current.delete(agent.childSessionId)
              }}
              type="button"
              role="option"
              aria-selected={active}
              aria-label={`${agent.taskPath}, ${t(`agentTree.status.${agent.status}`)}`}
              tabIndex={active ? 0 : -1}
              onClick={() => selectAgent(agent)}
              onKeyDown={(event) => onRowKeyDown(event, index)}
              className={cn(
                "mb-0.5 flex w-full min-w-0 items-start gap-2.5 rounded-[8px] px-2.5 py-2.5 text-left outline-none transition-colors hover:bg-muted/45 focus-visible:ring-2 focus-visible:ring-ring/25",
                active && "bg-muted/70 hover:bg-muted/70",
              )}
            >
              <StatusIcon status={agent.status} className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="min-w-0 flex-1">
                <span className="flex min-w-0 items-center justify-between gap-2">
                  <span className="truncate text-[13px] font-medium text-foreground" title={agent.taskPath}>
                    {shortTaskName(agent.taskPath)}
                  </span>
                  <span className="shrink-0 text-[10px] text-muted-foreground">
                    {formatAgentTime(agent.updatedAt) ? `${formatAgentTime(agent.updatedAt)} · ` : ""}
                    {t(`agentTree.status.${agent.status}`)}
                  </span>
                </span>
                <span className="mt-0.5 block truncate text-xs leading-5 text-muted-foreground">
                  {agentPreview(agent, t)}
                </span>
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )

  const detail = selected ? (
    <AgentWorkspaceDetail
      agent={selected}
      mobile={variant === "mobile"}
      onBack={() => {
        setMobileDetailOpen(false)
        window.requestAnimationFrame(() => rowRefs.current.get(selected.childSessionId)?.focus())
      }}
    />
  ) : null

  if (variant === "mobile") {
    return <div className="h-full min-h-0">{mobileDetailOpen ? detail : list}</div>
  }

  return <div className="flex h-full min-h-0">{list}{detail}</div>
}

function AgentWorkspaceDetail({
  agent,
  mobile,
  onBack,
}: {
  agent: AgentTreeNode
  mobile: boolean
  onBack: () => void
}) {
  const t = useTranslations("agentRuntime")
  return (
    <section
      className="min-h-0 min-w-0 flex-1 overflow-y-auto px-5 py-4 sm:px-6 sm:py-5"
      role="region"
      aria-label={t("agentWorkspace.detailLabel")}
    >
      {mobile ? (
        <button
          type="button"
          onClick={onBack}
          className="mb-4 inline-flex h-8 items-center gap-1.5 rounded-[8px] px-2 text-xs font-medium text-muted-foreground hover:bg-muted/45 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25"
          aria-label={t("agentWorkspace.back")}
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          {t("agentWorkspace.back")}
        </button>
      ) : null}

      <div className="flex min-w-0 items-start gap-3 border-b border-border/55 pb-4">
        <StatusIcon status={agent.status} className="mt-0.5 h-5 w-5 shrink-0" />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold text-foreground" title={agent.taskPath}>
            {agent.taskPath}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {t(`agentTree.status.${agent.status}`)}
          </p>
        </div>
      </div>

      <dl className="grid gap-3 border-b border-border/55 py-4 text-xs">
        <DetailRow label={t("agentWorkspace.sessionId")} value={agent.childSessionId} mono />
        <DetailRow label={t("agentWorkspace.turnId")} value={agent.childTurnId} mono />
        <DetailRow label={t("agentWorkspace.model")} value={agent.effectiveModel} mono />
        {agent.requestedModel ? (
          <DetailRow label={t("agentWorkspace.requestedModel")} value={agent.requestedModel} mono />
        ) : null}
        {agent.modelFallback ? (
          <DetailRow
            label={t("agentWorkspace.fallback")}
            value={agent.fallbackReason || `${agent.requestedModel ?? "—"} → ${agent.effectiveModel ?? "—"}`}
          />
        ) : null}
        <DetailRow label={t("agentWorkspace.terminationReason")} value={agent.terminationReason} mono />
        <DetailRow label={t("agentWorkspace.tokenUsage")} value={tokenTotal(agent.tokenUsage)} mono />
      </dl>

      <div className="pt-4">
        <p className={cn(
          "whitespace-pre-wrap text-sm leading-6",
          agent.status === "errored" ? "text-error-foreground" : "text-foreground/85",
        )}>
          {agent.errorMessage || agent.finalText || agentPreview(agent, t)}
        </p>
      </div>
    </section>
  )
}

function DetailRow({ label, value, mono = false }: { label: string; value?: string | null; mono?: boolean }) {
  if (!value) return null
  return (
    <div className="grid min-w-0 grid-cols-[7.5rem_minmax(0,1fr)] gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={cn("min-w-0 break-words text-foreground/80", mono && "font-mono text-[11px]")}>{value}</dd>
    </div>
  )
}

function StatusIcon({ status, className }: { status: AgentLifecycleStatus; className?: string }) {
  if (status === "completed") return <CheckCircle2 className={cn("text-success-foreground", className)} aria-hidden="true" />
  if (status === "errored") return <AlertCircle className={cn("text-error-foreground", className)} aria-hidden="true" />
  if (status === "interrupted") return <Circle className={cn("text-muted-foreground", className)} aria-hidden="true" />
  if (status === "running") return <CircleDashed className={cn("animate-spin text-foreground/65", className)} aria-hidden="true" />
  return <CircleDashed className={cn("text-muted-foreground", className)} aria-hidden="true" />
}

function shortTaskName(path: string) {
  return path.split("/").filter(Boolean).at(-1) ?? path
}

function agentPreview(
  agent: AgentTreeNode,
  t: (key: string, values?: Record<string, string | number>) => string,
) {
  if (agent.errorMessage) return agent.errorMessage
  if (agent.finalText) return agent.finalText.replace(/\s+/g, " ")
  if (agent.status === "running") return t("agentWorkspace.runningPreview")
  if (agent.status === "pending_init") return t("agentWorkspace.pendingPreview")
  if (agent.status === "interrupted") return t("agentWorkspace.interruptedPreview")
  return t("agentWorkspace.noSummary")
}

function tokenTotal(tokenUsage?: Record<string, unknown> | null) {
  const total = tokenUsage?.total_tokens
  return typeof total === "number" ? String(total) : null
}

function formatAgentTime(value?: string | null) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(date)
}

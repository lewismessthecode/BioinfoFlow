"use client"

import { useMemo, useState } from "react"
import {
  Activity,
  Brain,
  Check,
  CircleHelp,
  ClipboardList,
  Copy,
  FileText,
  MoreHorizontal,
  RefreshCw,
  ShieldAlert,
  ThumbsDown,
  ThumbsUp,
  X,
} from "@/lib/icons"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type {
  AgentCoreArtifact,
  AgentCoreEvent,
  AgentCoreMemory,
  AgentCoreTurn,
} from "@/lib/agent-core"

export function AgentCoreTurnBlock({
  turn,
  events,
  artifacts,
  memories,
  onApproveAction,
  onRejectAction,
  onAcceptMemory,
  onRejectMemory,
}: {
  turn: AgentCoreTurn
  events: AgentCoreEvent[]
  artifacts: AgentCoreArtifact[]
  memories: AgentCoreMemory[]
  onApproveAction: (actionId: string) => void
  onRejectAction: (actionId: string) => void
  onAcceptMemory: (memoryId: string) => void
  onRejectMemory: (memoryId: string) => void
}) {
  const t = useTranslations("agentCore")
  const actions = useMemo(() => extractActionTimeline(events), [events])
  const questions = useMemo(() => extractUserQuestions(events), [events])
  return (
    <div className="grid gap-5">
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-[28px] bg-[#f0eeee] px-5 py-3.5 text-[15px] text-foreground shadow-[inset_0_0_0_1px_rgba(60,64,67,0.03)] dark:bg-white/10">
          <p className="whitespace-pre-wrap break-words leading-relaxed">{turn.input_text}</p>
        </div>
      </div>
      <div className="flex justify-start">
        <div className="w-full max-w-[78%] px-1 py-1 text-[15px] text-foreground">
          <p className="whitespace-pre-wrap break-words leading-7">
            {turn.final_text || turn.error_message || t("noFinalText")}
          </p>
          <AssistantTurnActions />
          <UserQuestionsPanel questions={questions} />
          <ActionTimeline
            actions={actions}
            onApproveAction={onApproveAction}
            onRejectAction={onRejectAction}
          />
          <ArtifactsPanel artifacts={artifacts} />
          <MemoryProposalsPanel
            memories={memories}
            onAcceptMemory={onAcceptMemory}
            onRejectMemory={onRejectMemory}
          />
          <EventLedger events={events} />
        </div>
      </div>
    </div>
  )
}

function AssistantTurnActions() {
  const t = useTranslations("agentCore")
  const buttons = [
    { label: t("reactionLike"), icon: ThumbsUp },
    { label: t("reactionDislike"), icon: ThumbsDown },
    { label: t("reactionRegenerate"), icon: RefreshCw },
    { label: t("reactionCopy"), icon: Copy },
    { label: t("reactionMore"), icon: MoreHorizontal },
  ]

  return (
    <div className="mt-3 flex items-center gap-1 text-muted-foreground">
      {buttons.map(({ label, icon: Icon }) => (
        <Button
          key={label}
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded-full text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground"
          aria-label={label}
        >
          <Icon className="h-4 w-4" />
        </Button>
      ))}
    </div>
  )
}

type ActionTimelineItem = {
  key: string
  actionId: string | null
  name: string
  kind: string | null
  riskLevel: string | null
  inputPreview: string | null
  status: string
  waitingDecision: boolean
  seq: number
}

type UserQuestionItem = {
  key: string
  requestId: string | null
  question: string
  reason: string | null
  options: string[]
  answer: string | null
  status: "requested" | "resolved"
  seq: number
}

function UserQuestionsPanel({ questions }: { questions: UserQuestionItem[] }) {
  const t = useTranslations("agentCore")
  if (questions.length === 0) return null

  return (
    <div className="mt-4 border-t border-border/70 pt-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <CircleHelp className="h-3.5 w-3.5" />
        {t("clarificationRequested")}
      </div>
      <div className="grid gap-3">
        {questions.map((question) => (
          <div key={question.key} className="text-xs text-muted-foreground">
            <p className="text-sm font-medium leading-6 text-foreground">
              {question.question}
            </p>
            {question.reason ? (
              <p className="mt-1 leading-5">{question.reason}</p>
            ) : null}
            {question.options.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {question.options.map((option) => (
                  <span
                    key={`${question.key}-${option}`}
                    className="border border-border/70 px-2 py-1 font-mono text-[11px] text-foreground"
                  >
                    {option}
                  </span>
                ))}
              </div>
            ) : null}
            {question.status === "resolved" && question.answer ? (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-foreground">
                <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                <span className="font-medium">{t("clarificationResolved")}</span>
                <span className="font-mono">{question.answer}</span>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

function ActionTimeline({
  actions,
  onApproveAction,
  onRejectAction,
}: {
  actions: ActionTimelineItem[]
  onApproveAction: (actionId: string) => void
  onRejectAction: (actionId: string) => void
}) {
  const t = useTranslations("agentCore")
  if (actions.length === 0) return null

  return (
    <div className="mt-4 border-t border-border/70 pt-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <ClipboardList className="h-3.5 w-3.5" />
        {t("actionTimeline")}
      </div>
      <ol className="grid gap-2">
        {actions.map((action) => (
          <li
            key={action.key}
            className="border-l border-border/80 pl-3 text-xs text-muted-foreground"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono font-medium text-foreground">{action.name}</span>
              {action.kind ? <span>{action.kind}</span> : null}
              {action.riskLevel ? (
                <span className="border border-border/70 px-1.5 py-0.5 font-mono">
                  {action.riskLevel}
                </span>
              ) : null}
              <span className="font-mono">{action.status}</span>
            </div>
            {action.inputPreview ? (
              <p className="mt-1 whitespace-pre-wrap break-words leading-5">
                {action.inputPreview}
              </p>
            ) : null}
            {action.waitingDecision &&
            action.status === "waiting_decision" &&
            action.actionId ? (
              <div className="mt-2 bg-amber-500/5 px-3 py-2 text-amber-700 dark:text-amber-300">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 font-medium">
                    <ShieldAlert className="h-3.5 w-3.5" />
                    {t("actionApproval")}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => onApproveAction(action.actionId)}
                    >
                      <Check className="h-3.5 w-3.5" />
                      {t("approveAction")}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => onRejectAction(action.actionId)}
                    >
                      <X className="h-3.5 w-3.5" />
                      {t("rejectAction")}
                    </Button>
                  </div>
                </div>
              </div>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  )
}

function ArtifactsPanel({ artifacts }: { artifacts: AgentCoreArtifact[] }) {
  const t = useTranslations("agentCore")
  if (artifacts.length === 0) return null

  return (
    <div className="mt-4 border-t border-border/70 pt-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <FileText className="h-3.5 w-3.5" />
        {t("artifactPanel")}
      </div>
      <div className="grid gap-2">
        {artifacts.map((artifact) => (
          <div key={artifact.id} className="text-xs text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-foreground">{artifact.title}</span>
              <span className="font-mono">{artifact.type}</span>
            </div>
            {artifact.summary ? (
              <p className="mt-1 leading-5">{artifact.summary}</p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

function MemoryProposalsPanel({
  memories,
  onAcceptMemory,
  onRejectMemory,
}: {
  memories: AgentCoreMemory[]
  onAcceptMemory: (memoryId: string) => void
  onRejectMemory: (memoryId: string) => void
}) {
  const t = useTranslations("agentCore")
  if (memories.length === 0) return null

  return (
    <div className="mt-4 border-t border-border/70 pt-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Brain className="h-3.5 w-3.5" />
        {t("memoryProposals")}
      </div>
      <div className="grid gap-3">
        {memories.map((memory) => (
          <div key={memory.id} className="text-xs text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono font-medium text-foreground">{memory.type}</span>
              <span>{memory.scope}</span>
              {typeof memory.confidence === "number" ? (
                <span>{memory.confidence}%</span>
              ) : null}
            </div>
            <pre className="mt-2 max-h-36 overflow-auto bg-muted/40 p-2 font-mono text-[11px] leading-5 text-foreground">
              {formatJson(memory.content)}
            </pre>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                onClick={() => onAcceptMemory(memory.id)}
              >
                <Check className="h-3.5 w-3.5" />
                {t("acceptMemory")}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onRejectMemory(memory.id)}
              >
                <X className="h-3.5 w-3.5" />
                {t("rejectMemory")}
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function EventLedger({ events }: { events: AgentCoreEvent[] }) {
  const t = useTranslations("agentCore")
  const [open, setOpen] = useState(false)
  if (events.length === 0) return null
  return (
    <div className="mt-4 border-t border-border/50 pt-3">
      <button
        type="button"
        className="inline-flex items-center gap-2 rounded-full px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
        onClick={() => setOpen((current) => !current)}
      >
        <Activity className="h-3.5 w-3.5" />
        {t("auditToggle")}
      </button>
      {open ? (
        <div className="mt-3 rounded-2xl bg-muted/30 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
            {t("eventLedger")}
          </div>
          <ol className="grid gap-1.5">
            {events.map((event) => (
              <li key={event.id} className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="w-7 shrink-0 tabular-nums">{event.seq}</span>
                <span className="truncate font-mono">{event.type}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  )
}

function extractUserQuestions(events: AgentCoreEvent[]) {
  const questions = new Map<string, UserQuestionItem>()

  for (const event of events) {
    if (
      event.type !== "user_input.requested" &&
      event.type !== "user_input.resolved"
    ) {
      continue
    }

    const requestId = readString(event.payload.request_id)
    const key = requestId ?? `user-input-${event.seq}`
    const existing = questions.get(key)
    const question =
      readString(event.payload.question) ??
      readString(event.payload.prompt) ??
      existing?.question ??
      "User input requested"
    const answer =
      stringifyPayloadValue(event.payload.answer) ??
      stringifyPayloadValue(event.payload.value) ??
      existing?.answer ??
      null

    questions.set(key, {
      key,
      requestId: requestId ?? existing?.requestId ?? null,
      question,
      reason:
        readString(event.payload.reason) ??
        readString(event.payload.context) ??
        existing?.reason ??
        null,
      options: parseQuestionOptions(event.payload.options, existing?.options),
      answer,
      status: event.type === "user_input.resolved" ? "resolved" : existing?.status ?? "requested",
      seq: existing?.seq ?? event.seq,
    })
  }

  return [...questions.values()].sort((a, b) => a.seq - b.seq)
}

function extractActionTimeline(events: AgentCoreEvent[]) {
  const actions = new Map<string, ActionTimelineItem>()

  for (const event of events) {
    if (!event.type.startsWith("action.")) continue

    const actionId = readString(event.payload.action_id)
    const name = readString(event.payload.name) ?? event.type
    const key = actionId ?? `${name}-${event.seq}`
    const existing = actions.get(key)

    actions.set(key, {
      key,
      actionId: actionId ?? existing?.actionId ?? null,
      name,
      kind: readString(event.payload.kind) ?? existing?.kind ?? null,
      riskLevel:
        readString(event.payload.risk_level) ?? existing?.riskLevel ?? null,
      inputPreview:
        readString(event.payload.input_preview) ??
        existing?.inputPreview ??
        null,
      status: event.type.replace("action.", ""),
      waitingDecision:
        Boolean(existing?.waitingDecision) ||
        event.type === "action.waiting_decision",
      seq: existing?.seq ?? event.seq,
    })
  }

  return [...actions.values()].sort((a, b) => a.seq - b.seq)
}

function readString(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null
}

function parseQuestionOptions(value: unknown, fallback: string[] = []) {
  if (!Array.isArray(value)) return fallback
  return value
    .map((option) => {
      if (typeof option === "string") return option
      if (!option || typeof option !== "object") return null
      const record = option as Record<string, unknown>
      return (
        readString(record.label) ??
        readString(record.value) ??
        readString(record.id)
      )
    })
    .filter((option): option is string => Boolean(option))
}

function stringifyPayloadValue(value: unknown) {
  if (value === undefined || value === null) return null
  if (typeof value === "string") return value
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  return JSON.stringify(value)
}

function formatJson(value: Record<string, unknown>) {
  return JSON.stringify(value, null, 2)
}

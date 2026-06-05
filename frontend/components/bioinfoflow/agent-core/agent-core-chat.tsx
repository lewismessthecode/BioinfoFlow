"use client"

import { forwardRef, useImperativeHandle, useMemo, useRef, useState } from "react"
import {
  Activity,
  Bot,
  Brain,
  Check,
  CircleHelp,
  ClipboardList,
  Database,
  FileText,
  MessageSquare,
  ShieldAlert,
  User,
  X,
} from "lucide-react"
import { useTranslations } from "next-intl"

import { ChatInput } from "@/components/bioinfoflow/chat/chat-input"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useAgentCore } from "@/hooks/use-agent-core"
import type {
  AgentCoreArtifact,
  AgentCoreEvent,
  AgentCoreMemory,
  AgentCoreTurn,
} from "@/lib/agent-core"

type AgentCoreChatProps = {
  projectId?: string
  workspaceEnabled?: boolean
  className?: string
}

export type AgentCoreChatHandle = {
  focusInput: () => void
  stop: () => void
  newConversation: () => void
}

export const AgentCoreChat = forwardRef<AgentCoreChatHandle, AgentCoreChatProps>(
  function AgentCoreChat({ projectId, workspaceEnabled = true, className }, ref) {
    const t = useTranslations("agentCore")
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const [input, setInput] = useState("")
    const {
      activeSession,
      turns,
      events,
      artifactsByTurn,
      proposedMemories,
      isLoading,
      status,
      error,
      sendTurn,
      setActiveSessionId,
      approveAction,
      rejectAction,
      acceptMemory,
      rejectMemory,
    } = useAgentCore(projectId)

    useImperativeHandle(
      ref,
      () => ({
        focusInput: () => textareaRef.current?.focus(),
        stop: () => undefined,
        newConversation: () => {
          setActiveSessionId(null)
          setInput("")
        },
      }),
      [setActiveSessionId],
    )

    const eventsByTurn = useMemo(() => groupEventsByTurn(events), [events])
    const disabled = !projectId || !workspaceEnabled || status === "running"

    const handleSend = () => {
      const text = input.trim()
      if (!text) return
      void sendTurn(text)
      setInput("")
    }

    if (!projectId) {
      return (
        <div className={cn("flex h-full items-center justify-center bg-background p-6", className)}>
          <div className="w-full max-w-xl border border-border/70 bg-card px-6 py-7 text-center shadow-sm">
            <Database className="mx-auto h-8 w-8 text-muted-foreground" />
            <h2 className="mt-4 text-xl font-semibold text-foreground">{t("selectProjectTitle")}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{t("selectProjectDescription")}</p>
          </div>
        </div>
      )
    }

    return (
      <div className={cn("flex h-full flex-col bg-background", className)}>
        <div className="border-b border-border/70 px-5 py-3">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Bot className="h-4 w-4 text-primary" />
                <span>{t("title")}</span>
              </div>
              <p className="mt-1 truncate text-xs text-muted-foreground">
                {activeSession ? t("session", { id: shortId(activeSession.id) }) : t("sessionPending")}
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className={cn("h-2 w-2 rounded-full", status === "running" ? "bg-primary" : "bg-muted-foreground/40")} />
              <span>{status === "running" ? t("running") : t("idle")}</span>
            </div>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          {isLoading ? (
            <div className="text-sm text-muted-foreground">{t("loading")}</div>
          ) : turns.length === 0 ? (
            <div className="mx-auto flex min-h-full max-w-2xl flex-col items-center justify-center text-center">
              <MessageSquare className="h-9 w-9 text-muted-foreground" />
              <h2 className="mt-4 text-2xl font-semibold tracking-normal text-foreground">{t("emptyTitle")}</h2>
              <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">{t("emptyDescription")}</p>
            </div>
          ) : (
            <div className="mx-auto flex w-full max-w-4xl flex-col gap-5">
              {turns.map((turn) => (
                <AgentCoreTurnBlock
                  key={turn.id}
                  turn={turn}
                  events={eventsByTurn.get(turn.id) ?? []}
                  artifacts={artifactsByTurn.get(turn.id) ?? []}
                  memories={filterMemoriesForTurn(proposedMemories, turn.id)}
                  onApproveAction={approveAction}
                  onRejectAction={rejectAction}
                  onAcceptMemory={acceptMemory}
                  onRejectMemory={rejectMemory}
                />
              ))}
            </div>
          )}
          {error ? (
            <div className="mx-auto mt-4 max-w-4xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {error.message}
            </div>
          ) : null}
        </div>

        <div className="border-t border-border/70 px-4 py-3">
          <ChatInput
            input={input}
            onInputChange={setInput}
            onSend={handleSend}
            onStop={() => undefined}
            isStreaming={status === "running"}
            disabled={disabled}
            textareaRef={textareaRef}
            variant="thread"
          />
        </div>
      </div>
    )
  },
)

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
    <div className="grid gap-3">
      <div className="flex justify-end">
        <div className="max-w-[80%] border border-border/70 bg-muted/40 px-4 py-3 text-sm text-foreground">
          <div className="mb-1 flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <User className="h-3.5 w-3.5" />
            {t("user")}
          </div>
          <p className="whitespace-pre-wrap leading-6">{turn.input_text}</p>
        </div>
      </div>
      <div className="flex justify-start">
        <div className="max-w-[88%] border border-border/70 bg-card px-4 py-3 text-sm text-foreground shadow-sm">
          <div className="mb-1 flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <Bot className="h-3.5 w-3.5" />
            {t("assistant")}
          </div>
          <p className="whitespace-pre-wrap leading-6">
            {turn.final_text || turn.error_message || t("noFinalText")}
          </p>
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
  if (events.length === 0) return null
  return (
    <div className="mt-4 border-t border-border/70 pt-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Activity className="h-3.5 w-3.5" />
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

function groupEventsByTurn(events: AgentCoreEvent[]) {
  const grouped = new Map<string, AgentCoreEvent[]>()
  for (const event of events) {
    const list = grouped.get(event.turn_id) ?? []
    list.push(event)
    grouped.set(event.turn_id, list)
  }
  return grouped
}

function filterMemoriesForTurn(
  memories: AgentCoreMemory[],
  turnId: string,
) {
  return memories.filter((memory) => {
    const memoryTurnId = readString(memory.source?.turn_id)
    return !memoryTurnId || memoryTurnId === turnId
  })
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

function shortId(id: string) {
  return id.slice(0, 8)
}

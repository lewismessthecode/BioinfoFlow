"use client"

import { useMemo, useRef } from "react"
import { Play, RotateCcw, ExternalLink } from "@/lib/icons"
import { useDemoReplay } from "@/lib/demo/demo-context"
import { AgentCoreTurnBlock } from "@/components/bioinfoflow/agent-core/agent-core-turn-block"
import { DagPanel } from "@/components/bioinfoflow/dag/dag-panel"
import { Logo } from "@/components/bioinfoflow/logo"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import type { AgentCoreEvent } from "@/lib/agent-core"

export default function DemoPage() {
  const {
    turns,
    events,
    dag,
    runStatus,
    currentTask,
    status,
    progress,
    play,
    isStreaming,
  } = useDemoReplay()

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const eventsByTurn = useMemo(() => groupEventsByTurn(events), [events])

  const statusLabel =
    status === "idle"
      ? "Ready"
      : status === "playing"
        ? currentTask
          ? `Running: ${currentTask}`
          : "Playing..."
        : status === "finished"
          ? "Demo complete"
          : "Paused"

  return (
    <>
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-3">
          <Logo size={28} />
          <span className="text-sm font-semibold tracking-tight">Bioinfoflow</span>
          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-600 dark:text-amber-400">
            Demo
          </span>
        </div>

        <div className="flex items-center gap-3">
          {status === "finished" ? (
            <Button variant="outline" size="sm" onClick={play} className="gap-2">
              <RotateCcw className="size-3.5" />
              Replay
            </Button>
          ) : status === "idle" ? (
            <Button variant="outline" size="sm" onClick={play} className="gap-2">
              <Play className="size-3.5" />
              Start Demo
            </Button>
          ) : null}

          <Button variant="default" size="sm" className="gap-2" asChild>
            <a href="https://github.com/lewisliu/bioinfoflow" target="_blank" rel="noopener noreferrer">
              <ExternalLink className="size-3.5" />
              Install
            </a>
          </Button>
        </div>
      </header>

      {/* Progress bar */}
      {status === "playing" && (
        <div className="px-4">
          <Progress value={progress * 100} className="h-0.5" />
        </div>
      )}

      {/* Main content: Chat + DAG */}
      <div className="flex flex-1 min-h-0">
        {/* Chat panel */}
        <div className="flex flex-1 flex-col border-r border-border">
          <div className="flex items-center gap-2 border-b border-border px-4 py-2">
            <div className="size-2 rounded-full bg-success animate-pulse" />
            <span className="text-xs font-medium text-muted-foreground">
              {statusLabel}
            </span>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4">
            {turns.length === 0 && status === "idle" ? (
              <div className="flex h-full items-center justify-center">
                <div className="text-center space-y-3">
                  <div className="mx-auto flex size-16 items-center justify-center rounded-2xl bg-muted">
                    <Play className="size-6 text-muted-foreground" />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Watch an AI agent run a bioinformatics pipeline
                  </p>
                </div>
              </div>
            ) : (
              <div className="mx-auto flex w-full max-w-4xl flex-col gap-5">
                {turns.map((turn) => (
                  <AgentCoreTurnBlock
                    key={turn.id}
                    turn={turn}
                    events={eventsByTurn.get(turn.id) ?? []}
                    artifacts={[]}
                    memories={[]}
                    onApproveAction={() => undefined}
                    onRejectAction={() => undefined}
                    onAcceptMemory={() => undefined}
                    onRejectMemory={() => undefined}
                  />
                ))}
                {isStreaming ? (
                  <div className="text-xs font-medium text-muted-foreground">
                    AgentCore is streaming...
                  </div>
                ) : null}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* DAG panel */}
        <div className="hidden w-[400px] flex-shrink-0 flex-col lg:flex">
          <div className="flex items-center gap-2 border-b border-border px-4 py-2">
            <span className="text-xs font-medium text-muted-foreground">
              Pipeline DAG
            </span>
            {runStatus && (
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${
                runStatus === "completed"
                  ? "bg-success-muted text-success-foreground"
                  : runStatus === "running"
                    ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
                    : "bg-muted text-muted-foreground"
              }`}>
                {runStatus}
              </span>
            )}
          </div>

          <div className="flex-1 min-h-0">
            {dag ? (
              <DagPanel
                dag={dag}
                variant="embedded"
                title="E. coli QC Pipeline"
              />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                DAG will appear when pipeline starts
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom bar */}
      {status === "finished" && (
        <div className="border-t border-border bg-muted/30 px-4 py-3 text-center">
          <p className="text-sm text-muted-foreground">
            Ready to try it yourself?{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono">
              docker compose up -d
            </code>
            {" "}to get started.
          </p>
        </div>
      )}
    </>
  )
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

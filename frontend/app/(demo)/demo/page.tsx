"use client"

import { useTranslations } from "next-intl"

import { AgentTranscript } from "@/components/bioinfoflow/agent/agent-transcript"
import { DagPanel } from "@/components/bioinfoflow/dag/dag-panel"
import { Logo } from "@/components/bioinfoflow/logo"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { StatusBadge } from "@/components/ui/status-badge"
import { useDemoReplay } from "@/lib/demo/demo-context"
import { ExternalLink, Play, RotateCcw, Square } from "@/lib/icons"

export default function DemoPage() {
  const t = useTranslations("demoAgent")
  const {
    snapshot,
    dag,
    runStatus,
    currentTask,
    status,
    progress,
    play,
    pause,
  } = useDemoReplay()
  const statusLabel =
    status === "idle"
      ? t("status.ready")
      : status === "playing"
        ? currentTask
          ? t("status.running", { task: currentTask })
          : t("status.playing")
        : status === "finished"
          ? t("status.complete")
          : t("status.paused")

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2 sm:px-4">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <Logo size={28} />
          <span className="truncate text-sm font-semibold tracking-tight">
            Bioinfoflow
          </span>
          <StatusBadge
            variant="warning"
            className="px-2.5 py-0.5 text-[10px] uppercase tracking-wider"
          >
            {t("badge")}
          </StatusBadge>
        </div>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          {status === "finished" ? (
            <Button variant="outline" size="sm" onClick={play} className="gap-2">
              <RotateCcw data-icon="inline-start" aria-hidden="true" />
              {t("replay")}
            </Button>
          ) : status === "idle" ? (
            <Button variant="outline" size="sm" onClick={play} className="gap-2">
              <Play data-icon="inline-start" aria-hidden="true" />
              {t("start")}
            </Button>
          ) : status === "playing" ? (
            <Button variant="outline" size="sm" onClick={pause} className="gap-2">
              <Square data-icon="inline-start" aria-hidden="true" />
              {t("pause")}
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={play} className="gap-2">
              <RotateCcw data-icon="inline-start" aria-hidden="true" />
              {t("restart")}
            </Button>
          )}

          <Button variant="default" size="sm" className="gap-2" asChild>
            <a
              href="https://github.com/lewisliu/bioinfoflow"
              target="_blank"
              rel="noopener noreferrer"
            >
              <ExternalLink data-icon="inline-start" aria-hidden="true" />
              {t("install")}
            </a>
          </Button>
        </div>
      </header>

      {status === "playing" ? (
        <div className="px-3 sm:px-4">
          <Progress
            value={progress * 100}
            className="h-0.5"
            aria-label={t("progress")}
          />
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col border-r border-border">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2 sm:px-4">
            <div className="size-2 rounded-full bg-success" aria-hidden="true" />
            <span className="truncate text-xs font-medium text-muted-foreground">
              {statusLabel}
            </span>
          </div>

          <div className="min-h-0 flex-1">
            {snapshot.entries.length === 0 &&
            !snapshot.active_run &&
            status === "idle" ? (
              <div className="flex h-full items-center justify-center px-4">
                <div className="flex flex-col items-center gap-3 text-center">
                  <div className="flex size-16 items-center justify-center rounded-2xl bg-muted">
                    <Play
                      className="size-6 text-muted-foreground"
                      aria-hidden="true"
                    />
                  </div>
                  <p className="text-sm text-muted-foreground">{t("empty")}</p>
                </div>
              </div>
            ) : (
              <AgentTranscript
                className="h-full"
                entries={snapshot.entries}
                runs={snapshot.runs}
                activeRun={snapshot.active_run}
              />
            )}
          </div>
        </div>

        <div className="hidden w-[400px] flex-shrink-0 flex-col lg:flex">
          <div className="flex items-center gap-2 border-b border-border px-4 py-2">
            <span className="text-xs font-medium text-muted-foreground">
              {t("dag.title")}
            </span>
            {runStatus ? (
              <StatusBadge
                variant={
                  runStatus === "completed"
                    ? "success"
                    : runStatus === "running"
                      ? "running"
                      : "neutral"
                }
                className="px-2 py-0.5 text-[10px] uppercase tracking-wider"
              >
                {t(`runStatus.${runStatus}`)}
              </StatusBadge>
            ) : null}
          </div>

          <div className="min-h-0 flex-1">
            {dag ? (
              <DagPanel dag={dag} variant="embedded" title={t("dag.pipeline")} />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                {t("dag.waiting")}
              </div>
            )}
          </div>
        </div>
      </div>

      {status === "finished" ? (
        <div className="border-t border-border bg-muted/30 px-4 py-3 text-center">
          <p className="text-sm text-muted-foreground">
            {t("try.prefix")}{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
              docker compose up -d
            </code>{" "}
            {t("try.suffix")}
          </p>
        </div>
      ) : null}
    </>
  )
}

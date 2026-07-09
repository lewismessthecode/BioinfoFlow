"use client"

import { useState } from "react"
import Link from "next/link"
import { motion } from "framer-motion"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { ExternalLink, Activity } from "@/lib/icons"
import { StatusBadge } from "@/components/ui/status-badge"
import { Button } from "@/components/ui/button"
import { formatDateTime, formatDuration } from "@/lib/format-utils"
import { cn } from "@/lib/utils"
import { runStatusLabel, runStatusVariant } from "@/constants/status-config"
import type { DagData, Run, RunLogs, RunOutputs } from "@/lib/types"
import dynamic from "next/dynamic"
import { RunDetailContent } from "./run-detail-content"
const DagFullscreenDialog = dynamic(
  () => import("./dag-fullscreen-dialog").then((m) => ({ default: m.DagFullscreenDialog })),
  { ssr: false },
)

interface RunInlineDetailProps {
  run: Run
  logs: RunLogs | null
  outputs: RunOutputs | null
  dag: DagData | null
  workflowName: string
  workflowId?: string | null
  projectId: string
  onDownloadResults: (run: Run) => void
  onRerun: (run: Run) => void
  onDelete: (run: Run) => void
  onDownloadFile: (path: string) => void
  onCleanup?: (run: Run) => void
  colSpan: number
}

export function RunInlineDetail({
  run,
  logs,
  outputs,
  dag,
  workflowName,
  workflowId,
  projectId,
  onDownloadResults,
  onRerun,
  onDelete,
  onDownloadFile,
  onCleanup,
  colSpan,
}: RunInlineDetailProps) {
  const router = useRouter()
  const tRuns = useTranslations("runs")
  const tStatus = useTranslations("status")
  const [dagFullscreen, setDagFullscreen] = useState(false)

  return (
    <tr>
      <td colSpan={colSpan} className="p-0">
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{
            height: { duration: 0.35, ease: [0.22, 1, 0.36, 1] },
            opacity: { duration: 0.2 },
          }}
          className="overflow-hidden"
        >
          <div className="border-l-3 border-primary bg-accent/5">
            {/* Compact header with metadata */}
            <div className="px-6 py-4 border-b border-border/40">
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2.5">
                      <h3 className="font-mono text-[15px] font-semibold tracking-tight">{run.run_id}</h3>
                      <StatusBadge variant={runStatusVariant[run.status]}>
                        {tStatus(runStatusLabel[run.status] ?? run.status)}
                      </StatusBadge>
                    </div>
                    <p className="text-[13px] text-muted-foreground flex items-center gap-1.5 mt-1">
                      <Activity className="w-3 h-3 shrink-0" />
                      {workflowId ? (
                        <Link
                          href={`/workflows/${workflowId}`}
                          className="truncate transition-colors hover:text-foreground hover:underline underline-offset-4"
                          onClick={(event) => event.stopPropagation()}
                        >
                          {workflowName}
                        </Link>
                      ) : (
                        <span className="truncate">{workflowName}</span>
                      )}
                    </p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="shrink-0 text-muted-foreground hover:text-foreground"
                  onClick={() => router.push(`/runs/${run.run_id}`)}
                >
                  <ExternalLink className="w-3.5 h-3.5 mr-1.5" />
                  {tRuns("openFullPage")}
                </Button>
              </div>

              {/* Metadata row — subtle card grid */}
              <div className="grid grid-cols-2 gap-2 mt-4 sm:grid-cols-4">
                {[
                  { label: tRuns("detail.started"), value: formatDateTime(run.started_at) },
                  { label: tRuns("detail.duration"), value: formatDuration(run.duration_seconds), mono: true },
                  { label: tRuns("detail.workspace"), value: `runs/${run.run_id}`, mono: true, title: `runs/${run.run_id}` },
                  { label: tRuns("samples"), value: String(run.samples_count ?? "-") },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl border border-border/50 bg-background/60 px-3 py-2">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{item.label}</p>
                    <p className={cn("mt-0.5 text-[13px] font-medium text-foreground", item.mono && "font-mono", item.title && "truncate")} title={item.title}>{item.value}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Content area */}
            <RunDetailContent
              run={run}
              logs={logs}
              outputs={outputs}
              dag={dag}
              workflowName={workflowName}
              projectId={projectId}
              variant="inline"
              onDownloadResults={onDownloadResults}
              onRerun={onRerun}
              onDelete={onDelete}
              onDownloadFile={onDownloadFile}
              onOpenDagFullscreen={() => setDagFullscreen(true)}
              onCleanup={onCleanup}
            />
          </div>
        </motion.div>

        <DagFullscreenDialog
          open={dagFullscreen}
          onOpenChange={setDagFullscreen}
          runId={run.run_id}
          dag={dag}
          workflowName={workflowName}
        />
      </td>
    </tr>
  )
}

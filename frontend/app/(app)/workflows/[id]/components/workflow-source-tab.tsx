"use client"

import { useMemo, useState } from "react"
import { Copy, ExternalLink, FileCode, GitCompare, Rows3 } from "lucide-react"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { toast } from "sonner"
import type { Workflow, WorkflowSource, WorkflowEngine } from "@/lib/types"
import { cn } from "@/lib/utils"
import {
  buildSplitDiffRows,
  buildWorkflowSourceDiff,
} from "@/lib/workflow-source-diff"

interface WorkflowSourceTabProps {
  source: string | null
  sourceRef: string | null | undefined
  workflowSource: WorkflowSource
  engine: WorkflowEngine
  currentVersion: string
  compareCandidates?: Workflow[]
  selectedCompareWorkflowId?: string | null
  compareSource?: string | null
  isCompareLoading?: boolean
  onCompareWorkflowChange?: (workflowId: string | null) => void
}

function SourceTextBlock({ source }: { source: string }) {
  return (
    <div className="relative">
      <pre className="py-4 pr-4 pl-16 overflow-x-auto text-sm font-mono leading-relaxed max-h-[600px] overflow-y-auto bg-background">
        <code className="text-foreground/90">{source}</code>
      </pre>
      <div className="absolute top-0 left-0 py-4 pl-4 pr-2 select-none pointer-events-none">
        <div className="flex flex-col text-sm font-mono leading-relaxed text-muted-foreground/50 text-right min-w-[2rem]">
          {source.split("\n").map((_, idx) => (
            <span key={idx}>{idx + 1}</span>
          ))}
        </div>
      </div>
    </div>
  )
}

function DiffCell({
  kind,
  sign,
  lineNumber,
  text,
  isEmpty = false,
}: {
  kind: "context" | "add" | "remove"
  sign: " " | "+" | "-"
  lineNumber: number | null
  text: string
  isEmpty?: boolean
}) {
  return (
    <div
      className={cn(
        "grid min-h-7 grid-cols-[56px_22px_minmax(0,1fr)] font-mono text-[13px] leading-5",
        kind === "context" && "bg-transparent",
        kind === "remove" && !isEmpty && "bg-rose-50/90 dark:bg-rose-950/25",
        kind === "add" && !isEmpty && "bg-emerald-50/90 dark:bg-emerald-950/25",
        isEmpty && "bg-muted/20 text-transparent",
      )}
    >
      <div className="px-2 py-1 text-right text-muted-foreground/55 select-none">
        {lineNumber ?? ""}
      </div>
      <div
        className={cn(
          "px-1.5 py-1 text-center select-none",
          kind === "remove" && !isEmpty && "text-rose-700 dark:text-rose-300",
          kind === "add" && !isEmpty && "text-emerald-700 dark:text-emerald-300",
          kind === "context" && "text-muted-foreground/50",
        )}
      >
        {sign}
      </div>
      <pre className="overflow-hidden px-3 py-1 whitespace-pre-wrap break-all text-foreground/90">
        {text || " "}
      </pre>
    </div>
  )
}

export function WorkflowSourceTab({
  source,
  sourceRef,
  workflowSource,
  engine,
  currentVersion,
  compareCandidates = [],
  selectedCompareWorkflowId = null,
  compareSource = null,
  isCompareLoading = false,
  onCompareWorkflowChange,
}: WorkflowSourceTabProps) {
  const tWorkflows = useTranslations("workflows")
  const tCommon = useTranslations("common")
  const [viewMode, setViewMode] = useState<"raw" | "diff">("raw")

  const compareWorkflow = useMemo(
    () =>
      compareCandidates.find((item) => item.id === selectedCompareWorkflowId) ?? null,
    [compareCandidates, selectedCompareWorkflowId],
  )

  const diff = useMemo(() => {
    if (!source || !compareSource) return null
    return buildWorkflowSourceDiff(compareSource, source)
  }, [compareSource, source])

  const splitRows = useMemo(
    () => (diff ? buildSplitDiffRows(diff.rows) : []),
    [diff],
  )

  const handleCopy = () => {
    if (source) {
      navigator.clipboard.writeText(source)
      toast.success(tWorkflows("detail.source.copied"))
    }
  }

  const languageLabel =
    engine === "wdl" ? "WDL"
    : engine === "nextflow" ? "Nextflow (Groovy)"
    : tWorkflows("detail.source.unknownLanguage")

  if (workflowSource !== "local") {
    return (
      <div className="border border-border rounded-lg p-6">
        <div className="text-center py-8">
          <FileCode className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
          <h3 className="text-sm font-medium text-foreground mb-2">
            {tWorkflows("detail.source.notLocalTitle")}
          </h3>
          <p className="text-sm text-muted-foreground mb-4 max-w-md mx-auto">
            {tWorkflows("detail.source.notLocalDescription", {
              source: workflowSource === "nf-core" ? "nf-core" : "GitHub",
            })}
          </p>
          {sourceRef && (
            <Button variant="outline" asChild>
              <a
                href={
                  sourceRef.startsWith("http")
                    ? sourceRef
                    : `https://github.com/${sourceRef}`
                }
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink className="h-4 w-4 mr-2" />
                {tWorkflows("detail.source.viewOnGithub")}
              </a>
            </Button>
          )}
        </div>
      </div>
    )
  }

  if (!source) {
    return (
      <div className="border border-border rounded-lg p-6">
        <div className="text-center py-8">
          <FileCode className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
          <h3 className="text-sm font-medium text-foreground mb-2">{tWorkflows("detail.source.loadingTitle")}</h3>
          <p className="text-sm text-muted-foreground">
            {tWorkflows("detail.source.loadingDescription")}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-md ring-1 ring-border/60 overflow-hidden bg-background">
      <div className="bg-secondary/20 px-4 py-3 border-b border-border/40 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <FileCode className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium text-foreground">{languageLabel}</span>
            <span className="text-xs text-muted-foreground">
              ({source.split("\n").length} {tWorkflows("detail.source.lines")})
            </span>
            <Badge variant="outline" className="font-mono text-[11px]">
              {tWorkflows("detail.source.currentVersionLabel", {
                version: currentVersion,
              })}
            </Badge>
            {diff ? (
              <>
                <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">
                  +{diff.summary.additions}
                </Badge>
                <Badge className="border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300">
                  -{diff.summary.deletions}
                </Badge>
              </>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant={viewMode === "raw" ? "default" : "ghost"}
              size="sm"
              onClick={() => setViewMode("raw")}
            >
              <Rows3 className="mr-1.5 h-4 w-4" />
              {tWorkflows("detail.source.rawView")}
            </Button>
            <Button
              variant={viewMode === "diff" ? "default" : "ghost"}
              size="sm"
              disabled={!compareWorkflow || !compareSource}
              onClick={() => setViewMode("diff")}
            >
              <GitCompare className="mr-1.5 h-4 w-4" />
              {tWorkflows("detail.source.diffView")}
            </Button>
            <Button variant="ghost" size="sm" onClick={handleCopy}>
              <Copy className="h-4 w-4 mr-1" />
              {tCommon("copy")}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
              {tWorkflows("detail.source.compareVersion")}
            </span>
            <Select
              value={selectedCompareWorkflowId ?? "__none__"}
              onValueChange={(value) => {
                const nextWorkflowId = value === "__none__" ? null : value
                if (nextWorkflowId) {
                  setViewMode("diff")
                }
                onCompareWorkflowChange?.(nextWorkflowId)
              }}
            >
              <SelectTrigger
                size="sm"
                aria-label={tWorkflows("detail.source.compareVersion")}
                className="min-w-[220px] bg-background"
              >
                <SelectValue
                  placeholder={tWorkflows("detail.source.comparePlaceholder")}
                />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">
                  {tWorkflows("detail.source.compareNone")}
                </SelectItem>
                {compareCandidates.map((candidate) => (
                  <SelectItem key={candidate.id} value={candidate.id}>
                    {candidate.version}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {compareWorkflow ? (
            <p className="text-xs text-muted-foreground">
              {isCompareLoading
                ? tWorkflows("detail.source.compareLoading")
                : tWorkflows("detail.source.compareActive", {
                    current: currentVersion,
                    previous: compareWorkflow.version,
                  })}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              {compareCandidates.length > 0
                ? tWorkflows("detail.source.compareHint")
                : tWorkflows("detail.source.compareUnavailable")}
            </p>
          )}
        </div>
      </div>

      {viewMode === "diff" && diff ? (
        <div className="max-h-[680px] overflow-auto bg-background">
          <div className="min-w-[920px]">
            <div className="sticky top-0 z-10 grid grid-cols-2 border-b border-border/40 bg-muted/20 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground/80 backdrop-blur">
              <div className="px-4 py-2.5">
                {tWorkflows("detail.source.compareVersionLabel", {
                  version: compareWorkflow?.version ?? "—",
                })}
              </div>
              <div className="px-4 py-2.5">
                {tWorkflows("detail.source.currentVersionLabel", {
                  version: currentVersion,
                })}
              </div>
            </div>
            <div>
              {splitRows.map((row, index) => (
                <div key={`${row.type}-${index}`} className="grid grid-cols-2">
                  <div>
                    <DiffCell
                      kind={row.type}
                      sign={row.type === "remove" ? "-" : " "}
                      lineNumber={row.left?.lineNumber ?? null}
                      text={row.left?.text ?? ""}
                      isEmpty={row.left === null}
                    />
                  </div>
                  <DiffCell
                    kind={row.type}
                    sign={row.type === "add" ? "+" : " "}
                    lineNumber={row.right?.lineNumber ?? null}
                    text={row.right?.text ?? ""}
                    isEmpty={row.right === null}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <SourceTextBlock source={source} />
      )}
    </div>
  )
}

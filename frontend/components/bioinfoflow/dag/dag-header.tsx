import { useTranslations } from "next-intl"
import { Loader2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"
import type { ProjectWorkflowGroup, Run, RunStatus } from "@/lib/types"

const statusDot: Record<RunStatus, string> = {
  pending: "bg-muted-foreground/50",
  queued: "bg-warning/70",
  running: "bg-emerald-400",
  completed: "bg-emerald-500",
  failed: "bg-destructive",
  cancelled: "bg-muted-foreground/40",
}

interface DagHeaderProps {
  displayName: string
  workflowGroups: ProjectWorkflowGroup[]
  selectedGroupIndex: number | null
  onGroupChange: (index: number) => void
  workflowGroupsLoading: boolean
  isLoading: boolean
  showRunSelect: boolean
  runId: string | null | undefined
  runs: Run[]
  runsLoading: boolean
  runsError: string | null
  onRunSelect?: (run: Run | null) => void
}

export function DagHeader({
  displayName,
  workflowGroups,
  selectedGroupIndex,
  onGroupChange,
  workflowGroupsLoading,
  isLoading,
  showRunSelect,
  runId,
  runs,
  runsLoading,
  runsError,
  onRunSelect,
}: DagHeaderProps) {
  const tDag = useTranslations("dag")

  return (
    <div className="relative flex items-center justify-between border-b border-border px-4 py-3">
      <div className="flex items-center gap-2 min-w-0">
        {workflowGroups.length > 1 ? (
          <Select
            value={selectedGroupIndex !== null ? String(selectedGroupIndex) : ""}
            onValueChange={(value) => onGroupChange(Number(value))}
          >
            <SelectTrigger size="sm" className="h-7 max-w-[180px] bg-background/80 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {workflowGroups.map((group, index) => (
                <SelectItem key={group.pinned_workflow.id} value={String(index)} textValue={group.name}>
                  <span className="flex items-center gap-2">
                    <span className="truncate">{group.name}</span>
                    <Badge variant="outline" className="text-2xs shrink-0">
                      {group.source}
                    </Badge>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <span className="text-sm font-medium text-foreground truncate">{displayName}</span>
        )}
        {workflowGroupsLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground shrink-0" />}
      </div>
      <div className="flex items-center gap-2">
        {showRunSelect && onRunSelect && (
          <Select
            value={runId || ""}
            onValueChange={(value) => {
              if (!value) {
                onRunSelect(null)
                return
              }
              const selected = runs.find((run) => run.run_id === value) || null
              onRunSelect(selected)
            }}
          >
            <SelectTrigger size="sm" className="h-8 bg-background/80" aria-label={tDag("runSelect.ariaLabel")}>
              <SelectValue placeholder={tDag("runSelect.placeholder")} />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectLabel>{tDag("runSelect.groups.runs")}</SelectLabel>
                {runsLoading && <div className="px-2 py-1.5 text-xs text-muted-foreground">{tDag("runSelect.loading")}</div>}
                {runsError && !runsLoading && <div className="px-2 py-1.5 text-xs text-destructive">{runsError}</div>}
                {!runsLoading &&
                  !runsError &&
                  runs.map((run) => (
                    <SelectItem key={run.run_id} value={run.run_id} textValue={run.run_id}>
                      <span className="flex items-center gap-2">
                        <span className={cn("h-2 w-2 rounded-full", statusDot[run.status])} />
                        <span className="font-mono text-xs">{run.run_id.slice(0, 8)}</span>
                        <span className="text-xs text-muted-foreground">{run.status}</span>
                      </span>
                    </SelectItem>
                  ))}
                {!runsLoading && !runsError && runs.length === 0 && (
                  <div className="px-2 py-1.5 text-xs text-muted-foreground">{tDag("runSelect.empty")}</div>
                )}
              </SelectGroup>
            </SelectContent>
          </Select>
        )}
        {isLoading && <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none text-muted-foreground" />}
      </div>
    </div>
  )
}

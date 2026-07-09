import {
  MoreHorizontal,
  Play,
  Trash2,
} from "@/lib/icons"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { toast } from "sonner"
import { formatDate } from "@/lib/format-utils"
import type { HubWorkflowGroup, ProjectWorkflowGroup, Workflow } from "@/lib/types"

/* ── hub table ──────────────────────────────────────────── */

export function HubWorkflowsTable({
  groups,
  activeProjectId,
  tWorkflows,
  tCommon,
  formatWorkflowName,
  onBind,
  onAddAndRun,
  onViewDetails,
  onEditParameters,
  onDuplicate,
  onDelete,
}: {
  groups: HubWorkflowGroup[]
  activeProjectId: string
  tWorkflows: (key: string, values?: Record<string, unknown>) => string
  tCommon: (key: string) => string
  formatWorkflowName: (workflow: Workflow) => string
  onBind: (workflow: Workflow) => void
  onAddAndRun: (workflow: Workflow) => void
  onViewDetails: (workflow: Workflow) => void
  onEditParameters: (workflow: Workflow) => void
  onDuplicate: (workflow: Workflow) => void
  onDelete: (workflow: Workflow) => void
}) {
  return (
    <>
      {groups.map((group) => {
        const workflow = group.latest_workflow
        return (
          <tr key={`${group.source}:${group.engine}:${group.name}`} className="border-b border-border last:border-0 hover:bg-secondary/30">
            <td className="px-4 py-3">
              <div>
                <p className="font-medium text-foreground text-sm">{formatWorkflowName(workflow)}</p>
                <p className="text-xs text-muted-foreground">{workflow.description || tWorkflows("noDescription")}</p>
              </div>
            </td>
            <td className="px-4 py-3 text-sm text-muted-foreground">{workflow.source}</td>
            <td className="px-4 py-3 text-sm text-muted-foreground">{workflow.engine}</td>
            <td className="px-4 py-3 text-sm text-muted-foreground">
              <div className="flex items-center gap-2">
                <span className="font-mono">{workflow.version}</span>
                {group.versions.length > 1 ? (
                  <span className="text-xs text-muted-foreground">
                    {tWorkflows("versionCount", { count: group.versions.length })}
                  </span>
                ) : null}
              </div>
            </td>
            <td className="px-4 py-3 text-sm text-muted-foreground">{formatDate(workflow.updated_at)}</td>
            <td className="px-4 py-3 text-right">
              <div className="flex items-center justify-end gap-2">
                {activeProjectId ? (
                  <>
                    <Button size="sm" variant="outline" onClick={() => onBind(workflow)}>
                      {tWorkflows("actions.add")}
                    </Button>
                    <Button size="sm" onClick={() => onAddAndRun(workflow)}>
                      <Play className="h-3.5 w-3.5 mr-1" />
                      {tWorkflows("run")}
                    </Button>
                  </>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => toast.error(tWorkflows("errors.selectProjectToRun"))}>
                    {tWorkflows("actions.selectProject")}
                  </Button>
                )}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={tCommon("actions")}>
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => onViewDetails(workflow)}>{tWorkflows("viewDetails")}</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => onEditParameters(workflow)}>{tWorkflows("editParameters")}</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => onDuplicate(workflow)}>{tCommon("duplicate")}</DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem className="text-destructive" onClick={() => onDelete(workflow)}>{tWorkflows("delete")}</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </td>
          </tr>
        )
      })}
    </>
  )
}

/* ── project table ──────────────────────────────────────── */

export function ProjectWorkflowsTable({
  groups,
  tWorkflows,
  formatWorkflowName,
  onRun,
  onUnbindGroup,
  onSetPinnedVersion,
}: {
  groups: ProjectWorkflowGroup[]
  tWorkflows: (key: string, values?: Record<string, unknown>) => string
  formatWorkflowName: (workflow: Workflow) => string
  onRun: (workflow: Workflow) => void
  onUnbindGroup: (group: ProjectWorkflowGroup) => void
  onSetPinnedVersion: (workflowId: string) => void
}) {
  return (
    <>
      {groups.map((group) => {
        const workflow = group.pinned_workflow
        return (
          <tr key={`${group.source}:${group.name}`} className="border-b border-border last:border-0 hover:bg-secondary/30">
            <td className="px-4 py-3">
              <div>
                <p className="font-medium text-foreground text-sm">{formatWorkflowName(workflow)}</p>
                <p className="text-xs text-muted-foreground">{workflow.description || tWorkflows("noDescription")}</p>
              </div>
            </td>
            <td className="px-4 py-3 text-sm text-muted-foreground">{workflow.source}</td>
            <td className="px-4 py-3 text-sm text-muted-foreground">{workflow.engine}</td>
            <td className="px-4 py-3 text-sm text-muted-foreground">
              <div className="flex items-center gap-2 justify-between">
                <span className="font-mono">{workflow.version}</span>
                <Select value={workflow.id} onValueChange={(v) => onSetPinnedVersion(v)}>
                  <SelectTrigger className="h-8 w-[140px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {group.versions.map((v) => (
                      <SelectItem key={v.id} value={v.id}>
                        {v.version}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </td>
            <td className="px-4 py-3 text-sm text-muted-foreground">{formatDate(workflow.updated_at)}</td>
            <td className="px-4 py-3 text-right">
              <div className="flex items-center justify-end gap-2">
                <Button size="sm" variant="outline" onClick={() => onRun(workflow)}>
                  <Play className="h-3.5 w-3.5 mr-1" />
                  {tWorkflows("run")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-destructive hover:text-destructive"
                  onClick={() => onUnbindGroup(group)}
                >
                  <Trash2 className="h-3.5 w-3.5 mr-1" />
                  {tWorkflows("actions.remove")}
                </Button>
              </div>
            </td>
          </tr>
        )
      })}
    </>
  )
}

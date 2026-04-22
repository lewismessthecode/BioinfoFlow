"use client"

import { useTranslations } from "next-intl"
import { Play, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { WorkflowPills } from "./workflow-pills"
import { WorkflowCardBase } from "./workflow-card-base"
import type { ProjectWorkflowGroup, Workflow } from "@/lib/types"

interface ProjectGroupCardProps {
  group: ProjectWorkflowGroup
  formatWorkflowName: (workflow: Workflow) => string
  onRun: (workflow: Workflow) => void
  onViewDetails: (workflow: Workflow) => void
  onUnbindGroup: (group: ProjectWorkflowGroup) => void
  onSetPinnedVersion: (workflowId: string) => void
}

export function ProjectGroupCard({
  group,
  formatWorkflowName,
  onRun,
  onViewDetails,
  onUnbindGroup,
  onSetPinnedVersion,
}: ProjectGroupCardProps) {
  const tWorkflows = useTranslations("workflows")
  const workflow = group.pinned_workflow

  return (
    <WorkflowCardBase
      displayName={formatWorkflowName(workflow)}
      estimatedTime={workflow.estimated_time}
      nameWrapper={(children) => (
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="cursor-default">{children}</div>
          </TooltipTrigger>
          {workflow.description && (
            <TooltipContent side="right" className="max-w-xs">
              {workflow.description}
            </TooltipContent>
          )}
        </Tooltip>
      )}
      menuItems={
        <>
          <DropdownMenuItem onClick={() => onViewDetails(workflow)}>{tWorkflows("viewDetails")}</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-destructive" onClick={() => onUnbindGroup(group)}>
            <Trash2 className="h-4 w-4 mr-2" />
            {tWorkflows("actions.removeFromProject")}
          </DropdownMenuItem>
        </>
      }
      actions={
        <>
          <Button className="w-full" size="sm" variant="outline" onClick={() => onRun(workflow)}>
            <Play className="h-3.5 w-3.5 mr-1.5" />
            {tWorkflows("run")}
          </Button>
          <Select value={workflow.id} onValueChange={(v) => onSetPinnedVersion(v)}>
            <SelectTrigger size="sm" className="text-xs">
              <SelectValue placeholder={tWorkflows("version")} />
            </SelectTrigger>
            <SelectContent>
              {group.versions.map((v) => (
                <SelectItem key={v.id} value={v.id}>
                  {v.version}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </>
      }
    >
      {/* Pills */}
      <div className="mt-3">
        <WorkflowPills workflow={workflow} showSource />
      </div>
    </WorkflowCardBase>
  )
}

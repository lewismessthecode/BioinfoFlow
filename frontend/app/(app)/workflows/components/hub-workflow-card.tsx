"use client"

import { useMemo, useState } from "react"
import { useTranslations } from "next-intl"
import { ArrowUpRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { WorkflowPills } from "./workflow-pills"
import { WorkflowCardBase } from "./workflow-card-base"
import type { HubWorkflowGroup, Workflow } from "@/lib/types"

interface HubWorkflowCardProps {
  group: HubWorkflowGroup
  formatWorkflowName: (workflow: Workflow) => string
  activeProjectId: string
  onBind: (workflow: Workflow) => void
  onViewDetails: (workflow: Workflow) => void
  onEditParameters: (workflow: Workflow) => void
  onDuplicate: (workflow: Workflow) => void
  onDelete: (workflow: Workflow) => void
}

export function HubWorkflowCard({
  group,
  formatWorkflowName,
  activeProjectId,
  onBind,
  onViewDetails,
  onEditParameters,
  onDuplicate,
  onDelete,
}: HubWorkflowCardProps) {
  const tWorkflows = useTranslations("workflows")
  const tCommon = useTranslations("common")
  const [selectedVersionId, setSelectedVersionId] = useState(group.latest_workflow.id)
  const workflow = useMemo(
    () => group.versions.find((item) => item.id === selectedVersionId) ?? group.latest_workflow,
    [group.latest_workflow, group.versions, selectedVersionId],
  )
  const displayName = formatWorkflowName(workflow)
  const description = workflow.description
  const scaleLabel = null

  return (
    <WorkflowCardBase
      displayName={displayName}
      estimatedTime={workflow.estimated_time}
      nameWrapper={(children) => (
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="cursor-default">{children}</div>
          </TooltipTrigger>
          {description && (
            <TooltipContent side="right" className="max-w-xs">
              {description}
            </TooltipContent>
          )}
        </Tooltip>
      )}
      menuItems={
        <>
          <DropdownMenuItem onClick={() => onViewDetails(workflow)}>{tWorkflows("viewDetails")}</DropdownMenuItem>
          <DropdownMenuItem onClick={() => onEditParameters(workflow)}>{tWorkflows("editParameters")}</DropdownMenuItem>
          <DropdownMenuItem onClick={() => onDuplicate(workflow)}>{tCommon("duplicate")}</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-destructive" onClick={() => onDelete(workflow)}>{tWorkflows("delete")}</DropdownMenuItem>
        </>
      }
      actions={
        <>
          <Button className="w-full" size="sm" variant="outline" onClick={() => activeProjectId ? onBind(workflow) : onViewDetails(workflow)}>
            {activeProjectId ? tWorkflows("actions.add") : tWorkflows("viewDetails")}
          </Button>
          <Button className="w-full min-w-0" size="sm" variant="outline" onClick={() => onViewDetails(workflow)}>
            <ArrowUpRight className="h-3.5 w-3.5 mr-1 shrink-0" />
            <span className="truncate">{tWorkflows("detail.tabs.overview")}</span>
          </Button>
        </>
      }
    >
      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <WorkflowPills workflow={workflow} scaleLabel={scaleLabel} />
      </div>
      {group.versions.length > 1 ? (
        <div className="mt-2 flex items-center gap-2">
          <Select value={selectedVersionId} onValueChange={setSelectedVersionId}>
            <SelectTrigger className="h-8 w-[150px] rounded-full bg-background text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {group.versions.map((version) => (
                <SelectItem key={version.id} value={version.id}>
                  {version.version}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Badge variant="secondary" className="rounded-full px-2.5 text-xs-tight">
            {tWorkflows("versionCount", { count: group.versions.length })}
          </Badge>
        </div>
      ) : null}
    </WorkflowCardBase>
  )
}

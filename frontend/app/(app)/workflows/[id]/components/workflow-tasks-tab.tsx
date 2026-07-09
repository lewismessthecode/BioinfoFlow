"use client"

import { useState } from "react"
import { useTranslations } from "next-intl"
import { ChevronDown, ChevronRight, Box } from "@/lib/icons"
import { Badge } from "@/components/ui/badge"
import { IconBox } from "@/components/ui/icon-box"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { WorkflowSchema } from "@/lib/types"

interface WorkflowTasksTabProps {
  schema: WorkflowSchema | null
}

export function WorkflowTasksTab({ schema }: WorkflowTasksTabProps) {
  const tWorkflows = useTranslations("workflows")
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set())

  if (!schema) {
    return (
      <div className="border border-border rounded-lg p-6">
        <div className="text-center text-muted-foreground py-8">
          <p className="text-sm">{tWorkflows("detail.tasks.noInfoTitle")}</p>
          <p className="text-xs mt-1">
            {tWorkflows("detail.tasks.noInfoDescription")}
          </p>
        </div>
      </div>
    )
  }

  const tasks = schema.tasks || []

  const toggleTask = (taskName: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev)
      if (next.has(taskName)) {
        next.delete(taskName)
      } else {
        next.add(taskName)
      }
      return next
    })
  }

  const expandAll = () => {
    setExpandedTasks(new Set(tasks.map((t) => t.name)))
  }

  const collapseAll = () => {
    setExpandedTasks(new Set())
  }

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="bg-secondary/30 px-4 py-3 border-b border-border flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground">
          {tWorkflows("detail.tasks.title")}
          <Badge variant="secondary" className="ml-2">
            {tasks.length}
          </Badge>
        </h3>
        {tasks.length > 0 && (
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={expandAll}>
              {tWorkflows("detail.tasks.expandAll")}
            </Button>
            <Button variant="ghost" size="sm" onClick={collapseAll}>
              {tWorkflows("detail.tasks.collapseAll")}
            </Button>
          </div>
        )}
      </div>

      {tasks.length > 0 ? (
        <div className="divide-y divide-border">
          {tasks.map((task) => {
            const isExpanded = expandedTasks.has(task.name)
            const hasDetails =
              (task.inputs && task.inputs.length > 0) ||
              (task.outputs && task.outputs.length > 0) ||
              task.container

            return (
              <div key={task.name}>
                <button
                  onClick={() => hasDetails && toggleTask(task.name)}
                  className={cn(
                    "w-full px-4 py-3 flex items-center gap-3 text-left transition-colors",
                    hasDetails && "hover:bg-secondary/30 cursor-pointer",
                    !hasDetails && "cursor-default"
                  )}
                  disabled={!hasDetails}
                >
                  {hasDetails ? (
                    isExpanded ? (
                      <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
                    )
                  ) : (
                    <div className="w-4" />
                  )}
                  <IconBox icon={Box} />

                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-foreground font-mono text-sm">{task.name}</p>
                    {task.container && (
                      <p className="text-xs text-muted-foreground truncate">{task.container}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {task.inputs && task.inputs.length > 0 && (
                      <Badge variant="outline" className="text-xs">
                        {tWorkflows("detail.tasks.inputsCount", { count: task.inputs.length })}
                      </Badge>
                    )}
                    {task.outputs && task.outputs.length > 0 && (
                      <Badge variant="outline" className="text-xs">
                        {tWorkflows("detail.tasks.outputsCount", { count: task.outputs.length })}
                      </Badge>
                    )}
                  </div>
                </button>

                {isExpanded && hasDetails && (
                  <div className="px-4 pb-4 pl-16 space-y-3">
                    {/* Container */}
                    {task.container && (
                      <div>
                        <p className="text-xs font-medium text-muted-foreground mb-1">{tWorkflows("detail.tasks.container")}</p>
                        <code className="text-xs bg-secondary/50 px-2 py-1 rounded font-mono">
                          {task.container}
                        </code>
                      </div>
                    )}

                    {/* Inputs */}
                    {task.inputs && task.inputs.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-muted-foreground mb-1">{tWorkflows("detail.overview.inputs")}</p>
                        <div className="flex flex-wrap gap-1">
                          {task.inputs.map((input, idx) => (
                            <Badge key={idx} variant="secondary" className="text-xs font-mono">
                              {input}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Outputs */}
                    {task.outputs && task.outputs.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-muted-foreground mb-1">{tWorkflows("detail.overview.outputs")}</p>
                        <div className="flex flex-wrap gap-1">
                          {task.outputs.map((output, idx) => (
                            <Badge key={idx} variant="secondary" className="text-xs font-mono">
                              {output}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="p-6 text-center text-muted-foreground text-sm">
          {tWorkflows("detail.tasks.noTasks")}
        </div>
      )}
    </div>
  )
}

"use client"

import { ListChecks } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeArtifact } from "@/lib/agent-runtime"
import { todosFromArtifact } from "./artifact-viewers"
import { TodoChecklist } from "./todo-checklist"

export function InlineTodoCard({ artifact }: { artifact: AgentRuntimeArtifact }) {
  const t = useTranslations("agentRuntime")
  const todos = todosFromArtifact(artifact)
  if (!todos.length) return null

  return (
    <div
      className="mb-3 rounded-2xl border border-border/60 bg-card/70 px-3 py-3 shadow-sm"
      data-testid="inline-todo-card"
    >
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
        <ListChecks className="h-4 w-4 text-muted-foreground" />
        {t("progress.tasks")}
      </div>
      <TodoChecklist todos={todos} compact />
    </div>
  )
}

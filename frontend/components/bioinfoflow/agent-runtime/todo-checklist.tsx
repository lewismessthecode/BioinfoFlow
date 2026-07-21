"use client"

import { AlertTriangle, Check, Circle, CircleSlash2, Loader2 } from "@/lib/icons"
import { useTranslations } from "next-intl"

import type { AgentTodoDisplayItem, AgentTodoDisplayStatus, AgentTodoItem } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

type TodoChecklistItem = AgentTodoItem | AgentTodoDisplayItem

export function TodoChecklist({ todos, compact = false }: { todos: TodoChecklistItem[]; compact?: boolean }) {
  const t = useTranslations("agentRuntime")
  if (!todos.length) {
    return <p className="text-sm text-muted-foreground">{t("progress.empty")}</p>
  }
  return (
    <ul className="grid gap-1.5" data-testid="todo-checklist">
      {todos.map((todo, index) => {
        const displayStatus = todoDisplayStatus(todo)
        return (
          <li
            key={`${index}-${todo.content}`}
            className={cn(
              "flex items-start gap-2.5 rounded-xl text-sm",
              compact ? "px-1 py-1" : "border px-3 py-2",
              !compact && statusFrame(displayStatus),
            )}
          >
            <TodoStatusIcon status={displayStatus} />
            <span
              className={cn(
                "min-w-0 flex-1 break-words",
                displayStatus === "completed" && "text-muted-foreground line-through",
                displayStatus === "in_progress" && "font-medium text-foreground",
                ["failed", "cancelled", "stopped"].includes(displayStatus) &&
                  "text-muted-foreground",
              )}
            >
              {displayStatus === "in_progress" && todo.activeForm
                ? todo.activeForm
                : todo.content}
              {"errorMessage" in todo && todo.errorMessage ? (
                <span className="mt-0.5 block text-xs text-destructive">
                  {todo.errorMessage}
                </span>
              ) : null}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

function statusFrame(status: AgentTodoDisplayStatus) {
  if (status === "in_progress") return "border-primary/40 bg-primary/5"
  if (status === "failed") return "border-error-border bg-error-muted"
  if (status === "cancelled" || status === "stopped") return "border-muted-foreground/20 bg-muted/35"
  return "border-border/60 bg-card"
}

function todoDisplayStatus(todo: TodoChecklistItem): AgentTodoDisplayStatus {
  return "displayStatus" in todo ? todo.displayStatus : todo.status
}

function TodoStatusIcon({ status }: { status: AgentTodoDisplayStatus }) {
  const className = "mt-0.5 h-4 w-4 shrink-0"
  if (status === "completed") {
    return <Check className={cn(className, "text-success-foreground")} />
  }
  if (status === "in_progress") {
    return <Loader2 className={cn(className, "animate-spin text-primary")} data-testid="todo-spinner" />
  }
  if (status === "failed") {
    return <AlertTriangle className={cn(className, "text-error-foreground")} />
  }
  if (status === "cancelled" || status === "stopped") {
    return <CircleSlash2 className={cn(className, "text-muted-foreground")} />
  }
  return <Circle className={cn(className, "text-muted-foreground/50")} />
}

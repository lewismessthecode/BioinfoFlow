"use client"

import { Check, Circle, Loader2 } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentTodoItem } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function TodoChecklist({ todos, compact = false }: { todos: AgentTodoItem[]; compact?: boolean }) {
  const t = useTranslations("agentRuntime")
  if (!todos.length) {
    return <p className="text-sm text-muted-foreground">{t("progress.empty")}</p>
  }
  return (
    <ul className="grid gap-1.5" data-testid="todo-checklist">
      {todos.map((todo, index) => (
        <li
          key={`${index}-${todo.content}`}
          className={cn(
            "flex items-start gap-2.5 rounded-xl text-sm",
            compact ? "px-1 py-1" : "border px-3 py-2",
            !compact &&
              (todo.status === "in_progress"
                ? "border-primary/40 bg-primary/5"
                : "border-border/60 bg-card"),
          )}
        >
          <TodoStatusIcon status={todo.status} />
          <span
            className={cn(
              "min-w-0 flex-1 break-words",
              todo.status === "completed" && "text-muted-foreground line-through",
              todo.status === "in_progress" && "font-medium text-foreground",
            )}
          >
            {todo.status === "in_progress" && todo.activeForm
              ? todo.activeForm
              : todo.content}
          </span>
        </li>
      ))}
    </ul>
  )
}

function TodoStatusIcon({ status }: { status: AgentTodoItem["status"] }) {
  const className = "mt-0.5 h-4 w-4 shrink-0"
  if (status === "completed") {
    return <Check className={cn(className, "text-emerald-500")} />
  }
  if (status === "in_progress") {
    return <Loader2 className={cn(className, "animate-spin text-primary")} />
  }
  return <Circle className={cn(className, "text-muted-foreground/50")} />
}

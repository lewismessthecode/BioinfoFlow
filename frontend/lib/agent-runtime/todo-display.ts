import type {
  AgentRuntimeTurn,
  AgentTodoDisplayItem,
  AgentTodoDisplayStatus,
  AgentTodoItem,
} from "./types"

export function deriveTodoDisplayItems(
  todos: AgentTodoItem[],
  turn?: AgentRuntimeTurn | null,
): AgentTodoDisplayItem[] {
  return todos.map((todo) => ({
    ...todo,
    displayStatus: displayStatusForTodo(todo, turn),
    terminalReason: terminalReasonForTurn(turn),
    errorMessage: turn?.status === "failed" ? turn.error_message ?? null : null,
  }))
}

function displayStatusForTodo(
  todo: AgentTodoItem,
  turn?: AgentRuntimeTurn | null,
): AgentTodoDisplayStatus {
  if (todo.status === "completed") return "completed"
  if (todo.status === "pending") return "pending"
  if (!turn) return "in_progress"

  switch (turn.status) {
    case "queued":
    case "running":
    case "waiting_user":
    case "waiting_approval":
      return "in_progress"
    case "failed":
      return "failed"
    case "cancelled":
      return "cancelled"
    case "completed":
      return "stopped"
  }
}

function terminalReasonForTurn(turn?: AgentRuntimeTurn | null) {
  if (!turn) return null
  if (turn.status === "failed") return "failed"
  if (turn.status === "cancelled") return "cancelled"
  if (turn.status === "completed") return "completed"
  return null
}

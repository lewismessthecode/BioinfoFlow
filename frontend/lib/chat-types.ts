/**
 * Chat message types — parts-based model.
 *
 * A message contains an array of typed parts. The renderer dispatches
 * based on part.type: "text" | "thinking" | "tool-call".
 */

// ---------------------------------------------------------------------------
// Message Parts
// ---------------------------------------------------------------------------

export type TextPart = {
  type: "text"
  text: string
}

export type ThinkingPart = {
  type: "thinking"
  text: string
  isStreaming: boolean
}

export type ToolCallPart = {
  type: "tool-call"
  id: string
  toolName: string
  args: Record<string, unknown>
  status: "running" | "done" | "error" | "cancelled"
  result?: string
  resultData?: unknown
  durationMs?: number
  progressText?: string
  progressStatus?: string
}

export type ApprovalPart = {
  type: "approval"
  approvalId: string
  toolName: string
  toolInput: Record<string, unknown>
  approvalType: string
  status: "pending" | "approved" | "rejected" | "cancelled"
  createdAt: Date
  risk?: string
}

export type MessagePart = TextPart | ThinkingPart | ToolCallPart | ApprovalPart

// ---------------------------------------------------------------------------
// Message
// ---------------------------------------------------------------------------

export type ChatMessage = {
  id: string
  role: "user" | "assistant"
  parts: MessagePart[]
  createdAt: Date
  streaming?: boolean
}

// ---------------------------------------------------------------------------
// SSE Event types from the backend
// ---------------------------------------------------------------------------

export type SSEEvent =
  | { type: "text_delta"; messageId: string; content: string }
  | { type: "thinking_delta"; messageId: string; content: string }
  | { type: "tool_call_start"; messageId: string; metadata: { id: string; name: string; args: Record<string, unknown> } }
  | { type: "tool_call_progress"; messageId: string; metadata: { id: string; name: string; status: string; preview: string } }
  | { type: "tool_call_end"; messageId: string; metadata: { id: string; name: string; result: string; result_json?: unknown; is_error: boolean; duration_ms: number } }
  | { type: "text"; messageId: string; content: string; metadata?: Record<string, unknown> }
  | { type: "error"; messageId: string; content: string }
  | { type: "done"; messageId: string }
  | { type: "approval_required"; messageId: string; metadata: { approval_id: string; tool: string; input: Record<string, unknown>; approval_type: string; risk?: string } }

// ---------------------------------------------------------------------------
// Hook return type
// ---------------------------------------------------------------------------

export type AgentChatStatus = "idle" | "streaming" | "error"

/**
 * Conversation export utilities.
 *
 * Converts a ChatMessage[] array to Markdown or JSON for download.
 */

import type { ChatMessage } from "@/lib/chat-types"

// ---------------------------------------------------------------------------
// Markdown export
// ---------------------------------------------------------------------------

function partToMarkdown(part: ChatMessage["parts"][number]): string {
  switch (part.type) {
    case "text":
      return part.text
    case "thinking":
      return `<details>\n<summary>Thinking</summary>\n\n${part.text}\n</details>`
    case "tool-call": {
      const status = part.status === "error" ? "❌" : "✅"
      const duration = part.durationMs
        ? ` (${part.durationMs < 1000 ? `${Math.round(part.durationMs)}ms` : `${(part.durationMs / 1000).toFixed(1)}s`})`
        : ""
      let result = ""
      if (part.result) {
        const truncated =
          part.result.length > 500
            ? part.result.slice(0, 500) + "\n..."
            : part.result
        result = `\n\`\`\`\n${truncated}\n\`\`\``
      }
      return `${status} **${part.toolName}**${duration}${result}`
    }
    case "approval": {
      const icon =
        part.status === "approved" ? "✅" :
        part.status === "rejected" ? "❌" :
        "⏳"
      return `${icon} Approval: **${part.toolName}** — ${part.status}`
    }
  }
}

function exportAsMarkdown(messages: ChatMessage[]): string {
  const lines: string[] = [
    `# Conversation Export`,
    ``,
    `*Exported: ${new Date().toISOString()}*`,
    ``,
    `---`,
    ``,
  ]

  for (const msg of messages) {
    const role = msg.role === "user" ? "## 🧑 User" : "## 🤖 Assistant"
    lines.push(role)
    lines.push("")
    for (const part of msg.parts) {
      lines.push(partToMarkdown(part))
      lines.push("")
    }
    lines.push("---")
    lines.push("")
  }

  return lines.join("\n")
}

// ---------------------------------------------------------------------------
// JSON export
// ---------------------------------------------------------------------------

function exportAsJSON(messages: ChatMessage[]): string {
  const cleaned = messages.map((msg) => ({
    id: msg.id,
    role: msg.role,
    createdAt: msg.createdAt.toISOString(),
    parts: msg.parts.map((part) => {
      if (part.type === "approval") {
        return { ...part, createdAt: part.createdAt.toISOString() }
      }
      return part
    }),
  }))
  return JSON.stringify(
    {
      exported_at: new Date().toISOString(),
      message_count: messages.length,
      messages: cleaned,
    },
    null,
    2,
  )
}

// ---------------------------------------------------------------------------
// Download helper
// ---------------------------------------------------------------------------

export function downloadConversation(
  messages: ChatMessage[],
  format: "markdown" | "json",
  filename?: string,
): void {
  const content = format === "markdown" ? exportAsMarkdown(messages) : exportAsJSON(messages)
  const ext = format === "markdown" ? "md" : "json"
  const mimeType = format === "markdown" ? "text/markdown" : "application/json"
  const name = filename || `conversation-${new Date().toISOString().slice(0, 10)}.${ext}`

  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

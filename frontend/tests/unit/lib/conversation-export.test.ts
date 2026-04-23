import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { ChatMessage } from "@/lib/chat-types"
import { downloadConversation } from "@/lib/conversation-export"

const fixedTime = new Date("2026-04-23T10:30:00Z")

function buildMessages(): ChatMessage[] {
  return [
    {
      id: "user-1",
      role: "user",
      createdAt: new Date("2026-04-23T10:00:00Z"),
      parts: [{ type: "text", text: "Run the QC workflow" }],
    },
    {
      id: "assistant-1",
      role: "assistant",
      createdAt: new Date("2026-04-23T10:01:00Z"),
      parts: [
        { type: "thinking", text: "Checking the latest workflow state", isStreaming: false },
        {
          type: "tool-call",
          id: "tool-1",
          toolName: "file_read",
          args: {},
          status: "done",
          durationMs: 1200,
          result: `${"A".repeat(510)}`,
        },
        {
          type: "approval",
          approvalId: "approval-1",
          toolName: "submit_run",
          toolInput: {},
          approvalType: "tool_risk",
          status: "approved",
          createdAt: new Date("2026-04-23T10:01:02Z"),
        },
      ],
    },
  ]
}

describe("downloadConversation", () => {
  let createObjectURLMock: ReturnType<typeof vi.fn>
  let revokeObjectURLMock: ReturnType<typeof vi.fn>
  let capturedBlob: Blob | null
  let anchor: HTMLAnchorElement
  let createElementSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(fixedTime)

    capturedBlob = null
    createObjectURLMock = vi.fn((blob: Blob) => {
      capturedBlob = blob
      return "blob:test-url"
    })
    revokeObjectURLMock = vi.fn()

    vi.stubGlobal("URL", {
      createObjectURL: createObjectURLMock,
      revokeObjectURL: revokeObjectURLMock,
    })

    anchor = document.createElement("a")
    const clickSpy = vi.spyOn(anchor, "click").mockImplementation(() => {})
    createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
      if (tagName === "a") return anchor
      return document.createElementNS("http://www.w3.org/1999/xhtml", tagName)
    })
    void clickSpy
  })

  afterEach(() => {
    createElementSpy.mockRestore()
    vi.useRealTimers()
  })

  it("exports Markdown with tool summaries and a stable default filename", async () => {
    downloadConversation(buildMessages(), "markdown")

    expect(createObjectURLMock).toHaveBeenCalledTimes(1)
    expect(anchor.download).toBe("conversation-2026-04-23.md")
    expect(anchor.href).toBe("blob:test-url")
    expect(revokeObjectURLMock).toHaveBeenCalledWith("blob:test-url")

    const content = await capturedBlob!.text()
    expect(content).toContain("# Conversation Export")
    expect(content).toContain("*Exported: 2026-04-23T10:30:00.000Z*")
    expect(content).toContain("## 🧑 User")
    expect(content).toContain("## 🤖 Assistant")
    expect(content).toContain("✅ **file_read** (1.2s)")
    expect(content).toContain("<summary>Thinking</summary>")
    expect(content).toContain("✅ Approval: **submit_run** — approved")
    expect(content).toContain("\n...\n```")
  })

  it("exports JSON with ISO timestamps and an explicit filename override", async () => {
    downloadConversation(buildMessages(), "json", "thread-export.json")

    expect(anchor.download).toBe("thread-export.json")

    const parsed = JSON.parse(await capturedBlob!.text()) as {
      exported_at: string
      message_count: number
      messages: Array<{ createdAt: string; parts: Array<Record<string, unknown>> }>
    }

    expect(parsed.exported_at).toBe("2026-04-23T10:30:00.000Z")
    expect(parsed.message_count).toBe(2)
    expect(parsed.messages[0].createdAt).toBe("2026-04-23T10:00:00.000Z")
    expect(parsed.messages[1].parts[2].createdAt).toBe("2026-04-23T10:01:02.000Z")
  })
})

import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { ChatMessage } from "@/lib/chat-types"

const {
  toastSuccessMock,
  toastErrorMock,
  clipboardWriteTextMock,
} = vi.hoisted(() => ({
  toastSuccessMock: vi.fn(),
  toastErrorMock: vi.fn(),
  clipboardWriteTextMock: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccessMock(...args),
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}))

vi.mock("@/components/bioinfoflow/chat/parts/text-part", () => ({
  TextPart: ({ part }: { part: { text: string } }) => (
    <div data-testid="text-part">{part.text}</div>
  ),
}))

vi.mock("@/components/bioinfoflow/chat/parts/thinking-part", () => ({
  ThinkingPart: ({ part }: { part: { text: string } }) => (
    <div data-testid="thinking-part">{part.text}</div>
  ),
}))

vi.mock("@/components/bioinfoflow/chat/parts/tool-call-part", () => ({
  ToolCallGroup: ({
    parts,
    isActiveFallback,
  }: {
    parts: Array<{ toolName: string }>
    isActiveFallback?: boolean
  }) => (
    <div data-active-fallback={isActiveFallback ? "true" : "false"} data-testid="tool-group">
      {parts.map((part) => part.toolName).join(",")}
    </div>
  ),
  ToolCallPart: ({ part }: { part: { toolName: string } }) => (
    <div data-testid="tool-call">{part.toolName}</div>
  ),
}))

vi.mock("@/components/bioinfoflow/chat/parts/approval-part", () => ({
  ApprovalPart: ({ part }: { part: { approvalId: string } }) => (
    <div data-testid="approval-part">{part.approvalId}</div>
  ),
}))

import { MessageBubble } from "@/components/bioinfoflow/chat/message-bubble"

function makeUserMessage(text: string): ChatMessage {
  return {
    id: "user-1",
    role: "user",
    createdAt: new Date("2026-04-23T10:00:00Z"),
    parts: [{ type: "text", text }],
  }
}

function makeAssistantMessage(): ChatMessage {
  return {
    id: "assistant-1",
    role: "assistant",
    createdAt: new Date("2026-04-23T10:01:00Z"),
    parts: [
      { type: "text", text: "Run complete" },
      {
        type: "tool-call",
        id: "tool-1",
        toolName: "file_read",
        args: {},
        status: "done",
        result: "ok",
      },
      {
        type: "tool-call",
        id: "tool-2",
        toolName: "grep",
        args: {},
        status: "done",
        result: "match",
      },
      {
        type: "approval",
        approvalId: "approval-1",
        toolName: "submit_run",
        toolInput: {},
        approvalType: "tool_risk",
        status: "pending",
        createdAt: new Date("2026-04-23T10:01:02Z"),
      },
    ],
  }
}

describe("MessageBubble", () => {
  beforeEach(() => {
    toastSuccessMock.mockReset()
    toastErrorMock.mockReset()
    clipboardWriteTextMock.mockReset()
    if (!navigator.clipboard) {
      Object.defineProperty(globalThis.navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: clipboardWriteTextMock,
        },
      })
      return
    }

    vi.spyOn(navigator.clipboard, "writeText").mockImplementation(clipboardWriteTextMock)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("lets the user edit the latest prompt and submit the trimmed replacement", async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()

    render(
      <MessageBubble
        message={makeUserMessage("Initial prompt")}
        messageIndex={3}
        isLastUserMessage
        onEdit={onEdit}
      />,
    )

    await user.click(screen.getByRole("button", { name: /edit/i }))

    const editor = screen.getByLabelText("Edit message")
    await user.clear(editor)
    await user.type(editor, "  Updated prompt  ")
    await user.keyboard("{Enter}")

    expect(onEdit).toHaveBeenCalledWith(3, "Updated prompt")
  })

  it("groups assistant tool calls, resolves approval blocks, and copies the visible text payload", async () => {
    const user = userEvent.setup()
    const onRegenerate = vi.fn()
    clipboardWriteTextMock.mockResolvedValue(undefined)

    render(
      <MessageBubble
        message={makeAssistantMessage()}
        onRegenerate={onRegenerate}
      />,
    )

    expect(screen.getByTestId("text-part")).toHaveTextContent("Run complete")
    expect(screen.getByTestId("tool-group")).toHaveTextContent("file_read,grep")
    expect(screen.getByTestId("approval-part")).toHaveTextContent("approval-1")

    await user.click(screen.getByRole("button", { name: /copy/i }))
    await waitFor(() => {
      expect(clipboardWriteTextMock).toHaveBeenCalledWith("Run complete")
      expect(toastSuccessMock).toHaveBeenCalledWith("Copied to clipboard")
    })

    await user.click(screen.getByRole("button", { name: /regenerate/i }))
    expect(onRegenerate).toHaveBeenCalledTimes(1)
  })

  it("marks the last completed tool group active while an assistant response is still streaming", () => {
    render(
      <MessageBubble
        message={{
          ...makeAssistantMessage(),
          streaming: true,
          parts: [
            { type: "text", text: "Let me try with the required parameter:" },
            {
              type: "tool-call",
              id: "tool-1",
              toolName: "list_runs",
              args: {},
              status: "done",
              result: "ok",
            },
            {
              type: "tool-call",
              id: "tool-2",
              toolName: "show_run",
              args: {},
              status: "done",
              result: "ok",
            },
          ],
        }}
      />,
    )

    expect(screen.getByTestId("tool-group")).toHaveAttribute("data-active-fallback", "true")
  })
})

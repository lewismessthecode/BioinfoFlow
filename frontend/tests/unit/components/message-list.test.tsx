import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { ChatMessage } from "@/lib/chat-types"

const bubblePropsRef = vi.hoisted(() => ({
  current: [] as Array<Record<string, unknown>>,
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      selectProject: "Select a project",
    }
    return labels[key] ?? key
  },
}))

vi.mock("@/components/bioinfoflow/chat/message-bubble", () => ({
  MessageBubble: (props: Record<string, unknown>) => {
    bubblePropsRef.current.push(props)
    const message = props.message as ChatMessage
    return <div data-testid={`bubble-${message.id}`}>{message.id}</div>
  },
}))

vi.mock("@/components/bioinfoflow/chat/typing-indicator", () => ({
  TypingIndicator: () => <div data-testid="typing-indicator" />,
}))

vi.mock("@/components/bioinfoflow/chat/chat-error-boundary", () => ({
  ChatErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

import { MessageList } from "@/components/bioinfoflow/chat/message-list"

function makeMessage(
  id: string,
  role: "user" | "assistant",
  text: string,
): ChatMessage {
  return {
    id,
    role,
    createdAt: new Date("2026-04-23T12:00:00Z"),
    parts: [{ type: "text", text }],
  }
}

describe("MessageList", () => {
  beforeEach(() => {
    bubblePropsRef.current = []
  })

  it("shows the project-selection empty state before a workspace is chosen", () => {
    render(
      <MessageList
        messages={[]}
        status="idle"
        isLoading={false}
        messagesEndRef={{ current: null }}
        onRegenerate={vi.fn()}
      />,
    )

    expect(screen.getByText("Select a project")).toBeInTheDocument()
    expect(
      screen.getByText("Choose a project from the sidebar to start chatting"),
    ).toBeInTheDocument()
  })

  it("flags the last user message, keeps regenerate on the newest assistant reply, and shows typing for an empty streaming reply", () => {
    const onRegenerate = vi.fn()
    const messages = [
      makeMessage("user-1", "user", "First prompt"),
      makeMessage("assistant-1", "assistant", "First answer"),
      makeMessage("user-2", "user", "Second prompt"),
      makeMessage("assistant-2", "assistant", " "),
    ]

    render(
      <MessageList
        messages={messages}
        status="streaming"
        isLoading={false}
        projectId="project-1"
        messagesEndRef={{ current: null }}
        onRegenerate={onRegenerate}
      />,
    )

    expect(screen.getByTestId("typing-indicator")).toBeInTheDocument()
    expect(screen.getByTestId("bubble-user-2")).toBeInTheDocument()
    expect(screen.getByTestId("bubble-assistant-2")).toBeInTheDocument()

    const user2Props = bubblePropsRef.current.find(
      (props) => (props.message as ChatMessage).id === "user-2",
    )
    const assistant2Props = bubblePropsRef.current.find(
      (props) => (props.message as ChatMessage).id === "assistant-2",
    )
    const assistant1Props = bubblePropsRef.current.find(
      (props) => (props.message as ChatMessage).id === "assistant-1",
    )

    expect(user2Props?.isLastUserMessage).toBe(true)
    expect(assistant1Props?.onRegenerate).toBeUndefined()
    expect(assistant2Props?.onRegenerate).toBe(onRegenerate)
  })

  it("shows a loading placeholder while the message history is still hydrating", () => {
    render(
      <MessageList
        messages={[makeMessage("assistant-1", "assistant", "Loading soon")]}
        status="idle"
        isLoading
        projectId="project-1"
        messagesEndRef={{ current: null }}
        onRegenerate={vi.fn()}
      />,
    )

    expect(screen.queryByTestId("bubble-assistant-1")).not.toBeInTheDocument()
  })
})

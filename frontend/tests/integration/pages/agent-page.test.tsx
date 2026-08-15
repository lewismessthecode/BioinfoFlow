import { forwardRef, useImperativeHandle } from "react"
import { fireEvent, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import AgentSessionPage from "@/app/(app)/agent/[sessionId]/page"
import AgentPage from "@/app/(app)/agent/page"
import { renderAppPage } from "@/tests/app-test-utils"

const mocks = vi.hoisted(() => ({
  params: vi.fn(() => ({ sessionId: "session-9" })),
  useEvents: vi.fn(),
  isMobile: vi.fn(() => false),
  workbench: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useParams: () => mocks.params(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/agent",
}))

vi.mock("@/hooks/use-events", () => ({
  useEvents: (...args: unknown[]) => mocks.useEvents(...args),
}))

vi.mock("@/hooks/use-media-query", () => ({
  useIsMobile: () => mocks.isMobile(),
}))

vi.mock("@/components/bioinfoflow/agent/agent-workbench", () => ({
  AgentWorkbench: forwardRef(function MockAgentWorkbench(
    props: {
      sessionId: string | null
      projectId: string | null
      onSessionResolved?: (session: unknown) => void
    },
    ref,
  ) {
    mocks.workbench(props)
    useImperativeHandle(ref, () => ({
      focusInput: vi.fn(),
      stop: vi.fn(),
      newConversation: vi.fn(),
    }))
    return (
      <div data-testid="agent-workbench">
        session:{props.sessionId ?? "draft"}|project:{props.projectId ?? "none"}
      </div>
    )
  }),
}))

vi.mock("@/components/bioinfoflow/live-deck", () => ({
  LiveDeck: ({ onCollapse }: { onCollapse: () => void }) => (
    <div data-testid="live-deck">
      <button type="button" onClick={onCollapse}>close</button>
    </div>
  ),
}))

vi.mock("@/components/ui/resize-handle", () => ({
  ResizeHandle: () => <div data-testid="resize-handle" />,
}))

describe("Agent pages", () => {
  beforeEach(() => {
    localStorage.clear()
    mocks.params.mockReturnValue({ sessionId: "session-9" })
    mocks.useEvents.mockReset()
    mocks.workbench.mockReset()
    mocks.isMobile.mockReturnValue(false)
  })

  it("treats /agent as a new draft even when app context still names an old session", () => {
    renderAppPage(<AgentPage />, {
      projectContext: {
        activeConversationId: "session-old",
        selectedProjectId: "project-1",
        conversationProjectId: "project-1",
      },
    })

    expect(screen.getByTestId("agent-workbench")).toHaveTextContent(
      "session:draft|project:project-1",
    )
    expect(mocks.workbench).toHaveBeenLastCalledWith(
      expect.objectContaining({ sessionId: null }),
    )
  })

  it("treats the dynamic route parameter as the existing-session authority", () => {
    renderAppPage(<AgentSessionPage />, {
      projectContext: {
        activeConversationId: "session-old",
        conversationProjectId: "project-2",
      },
    })

    expect(screen.getByTestId("agent-workbench")).toHaveTextContent(
      "session:session-9|project:project-2",
    )
  })

  it("keeps the LiveDeck hidden until the dedicated shifted shortcut is used", () => {
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
    fireEvent.keyDown(window, { key: "b", ctrlKey: true, shiftKey: true })
    expect(screen.getByTestId("live-deck")).toBeInTheDocument()
  })
})

import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createAppWrapper } from "@/tests/app-test-utils"
import { useAgentChat } from "@/hooks/use-agent-chat"
import { apiRequest } from "@/lib/api"

const captured = vi.hoisted(() => ({
  onAgentEvent: null as ((event: unknown) => void) | null,
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
    getApiErrorMessage: actual.getApiErrorMessage,
  }
})

vi.mock("@/hooks/use-events", () => ({
  useEvents: (options: { onAgentEvent?: (event: unknown) => void }) => {
    captured.onAgentEvent = options.onAgentEvent ?? null
    return { connectionState: "connected" }
  },
}))

vi.mock("@/hooks/use-chat-scroll", () => ({
  useChatScroll: () => ({
    messagesEndRef: { current: null },
    scrollContainerRef: { current: null },
    scrollFabProps: {},
  }),
}))

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

describe("useAgentChat", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  beforeEach(() => {
    captured.onAgentEvent = null
    apiRequestMock.mockReset()
    window.localStorage.clear()
  })

  it("renders and updates Hermes approval cards from approval events", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/agent/conversations/conversation-1") {
        return {
          data: {
            conversation_id: "conversation-1",
            project_id: "project-1",
            title: "Hermes Thread",
            pinned: false,
            storage_backend: "hermes",
            messages: [],
          },
          meta: undefined,
        }
      }
      if (path === "/agent/conversations/conversation-1/status") {
        return {
          data: {
            conversation_id: "conversation-1",
            is_running: true,
            response_id: "response-1",
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
      selectedProjectId: "project-1",
      conversationProjectId: "project-1",
      activeConversationId: "conversation-1",
    })

    const { result } = renderHook(() => useAgentChat("project-1"), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(captured.onAgentEvent).not.toBeNull()

    act(() => {
      captured.onAgentEvent?.({
        event: "agent.approval.requested",
        conversation_id: "conversation-1",
        project_id: "project-1",
        timestamp: "2026-04-15T10:00:00Z",
        id: "event-1",
        data: {
          approval_id: "approval-1",
          response_id: "response-1",
          tool: "clarify",
          approval_type: "clarify",
          payload: {
            input: { question: "Approve shell?", choices: ["approve", "reject"] },
          },
        },
      })
    })

    await waitFor(() =>
      expect(result.current.messages.some((message) => message.id === "response-1")).toBe(true)
    )
    const approvalMessage = result.current.messages.find((message) => message.id === "response-1")
    expect(approvalMessage).toBeDefined()
    expect(approvalMessage?.parts[0]).toMatchObject({
      type: "approval",
      approvalId: "approval-1",
      toolName: "clarify",
      approvalType: "clarify",
      status: "pending",
    })

    act(() => {
      captured.onAgentEvent?.({
        event: "agent.approval.resolved",
        conversation_id: "conversation-1",
        project_id: "project-1",
        timestamp: "2026-04-15T10:00:02Z",
        id: "event-2",
        data: {
          approval_id: "approval-1",
          status: "approved",
        },
      })
    })

    await waitFor(() =>
      expect(
        result.current.messages.find((message) => message.id === "response-1")?.parts[0]
      ).toMatchObject({
        type: "approval",
        approvalId: "approval-1",
        status: "approved",
      })
    )
  })

  it("keeps Hermes tool progress and risky approvals inline on one assistant message", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/agent/conversations/conversation-1") {
        return {
          data: {
            conversation_id: "conversation-1",
            project_id: "project-1",
            title: "Hermes Thread",
            pinned: false,
            storage_backend: "hermes",
            messages: [],
          },
          meta: undefined,
        }
      }
      if (path === "/agent/conversations/conversation-1/status") {
        return {
          data: {
            conversation_id: "conversation-1",
            is_running: true,
            response_id: "response-1",
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
      selectedProjectId: "project-1",
      conversationProjectId: "project-1",
      activeConversationId: "conversation-1",
    })

    const { result } = renderHook(() => useAgentChat("project-1"), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(captured.onAgentEvent).not.toBeNull()

    act(() => {
      captured.onAgentEvent?.({
        event: "agent.tool_call_start",
        conversation_id: "conversation-1",
        project_id: "project-1",
        timestamp: "2026-04-15T10:00:00Z",
        id: "event-tool-start",
        data: {
          id: "response-1",
          content: "submit_run",
          metadata: {
            response_id: "response-1",
            id: "tool-1",
            name: "submit_run",
            args: { workflow_name: "nf-core/rnaseq" },
          },
        },
      })
      captured.onAgentEvent?.({
        event: "agent.tool_call_progress",
        conversation_id: "conversation-1",
        project_id: "project-1",
        timestamp: "2026-04-15T10:00:01Z",
        id: "event-tool-progress",
        data: {
          id: "response-1",
          content: "Waiting for approval",
          metadata: {
            response_id: "response-1",
            id: "tool-1",
            name: "submit_run",
            status: "requires_approval",
            preview: "Waiting for approval",
          },
        },
      })
      captured.onAgentEvent?.({
        event: "agent.approval.requested",
        conversation_id: "conversation-1",
        project_id: "project-1",
        timestamp: "2026-04-15T10:00:02Z",
        id: "event-approval",
        data: {
          approval_id: "approval-risk-1",
          response_id: "response-1",
          tool: "submit_run",
          approval_type: "tool_risk",
          payload: {
            input: { workflow_name: "nf-core/rnaseq" },
            risk: "act_high",
          },
        },
      })
    })

    await waitFor(() =>
      expect(result.current.messages.some((message) => message.id === "response-1")).toBe(true)
    )

    const assistantMessage = result.current.messages.find((message) => message.id === "response-1")
    expect(assistantMessage).toBeDefined()
    expect(assistantMessage?.parts.some((part) => part.type === "tool-call")).toBe(true)
    expect(assistantMessage?.parts.some((part) => part.type === "approval")).toBe(true)
    expect(result.current.currentActivity).toBe("Waiting for approval")
    expect(assistantMessage?.parts.find((part) => part.type === "approval")).toMatchObject({
      type: "approval",
      approvalId: "approval-risk-1",
      toolName: "submit_run",
      approvalType: "tool_risk",
      status: "pending",
    })
  })

  it("optimistically flips approval activity to resume the interrupted Hermes tool", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/agent/conversations/conversation-1") {
        return {
          data: {
            conversation_id: "conversation-1",
            project_id: "project-1",
            title: "Hermes Thread",
            pinned: false,
            storage_backend: "hermes",
            messages: [],
          },
          meta: undefined,
        }
      }
      if (path === "/agent/conversations/conversation-1/status") {
        return {
          data: {
            conversation_id: "conversation-1",
            is_running: true,
            response_id: "response-1",
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
      selectedProjectId: "project-1",
      conversationProjectId: "project-1",
      activeConversationId: "conversation-1",
    })

    const { result } = renderHook(() => useAgentChat("project-1"), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(captured.onAgentEvent).not.toBeNull()

    act(() => {
      captured.onAgentEvent?.({
        event: "agent.tool_call_start",
        conversation_id: "conversation-1",
        project_id: "project-1",
        timestamp: "2026-04-15T10:00:00Z",
        id: "event-tool-start",
        data: {
          id: "response-1",
          content: "submit_run",
          metadata: {
            response_id: "response-1",
            id: "tool-1",
            name: "submit_run",
            args: { workflow_name: "nf-core/rnaseq" },
          },
        },
      })
      captured.onAgentEvent?.({
        event: "agent.tool_call_progress",
        conversation_id: "conversation-1",
        project_id: "project-1",
        timestamp: "2026-04-15T10:00:01Z",
        id: "event-tool-progress",
        data: {
          id: "response-1",
          content: "Waiting for approval",
          metadata: {
            response_id: "response-1",
            id: "tool-1",
            name: "submit_run",
            status: "requires_approval",
            preview: "Waiting for approval",
          },
        },
      })
      captured.onAgentEvent?.({
        event: "agent.approval.requested",
        conversation_id: "conversation-1",
        project_id: "project-1",
        timestamp: "2026-04-15T10:00:02Z",
        id: "event-approval",
        data: {
          approval_id: "approval-risk-1",
          response_id: "response-1",
          tool: "submit_run",
          approval_type: "tool_risk",
          payload: {
            input: { workflow_name: "nf-core/rnaseq" },
            risk: "act_high",
          },
        },
      })
      captured.onAgentEvent?.({
        event: "agent.approval.resolved",
        conversation_id: "conversation-1",
        project_id: "project-1",
        timestamp: "2026-04-15T10:00:03Z",
        id: "event-approval-resolved",
        data: {
          approval_id: "approval-risk-1",
          status: "approved",
        },
      })
    })

    await waitFor(() => expect(result.current.currentActivity).toBe("Approval received, resuming submit_run"))

    const assistantMessage = result.current.messages.find((message) => message.id === "response-1")
    const toolPart = assistantMessage?.parts.find((part) => part.type === "tool-call")

    expect(toolPart).toMatchObject({
      type: "tool-call",
      toolName: "submit_run",
      progressStatus: "approved",
      progressText: "Approval received, resuming submit_run",
    })
    expect(assistantMessage?.parts.find((part) => part.type === "approval")).toMatchObject({
      type: "approval",
      approvalId: "approval-risk-1",
      status: "approved",
    })
  })

  it("forwards a staged execution policy on the first message before a conversation exists", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/agent/message" && options?.method === "POST") {
        return {
          data: {
            conversation_id: "conversation-2",
            status: "processing",
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
      selectedProjectId: "project-1",
      conversationProjectId: "project-1",
      activeConversationId: "",
    })

    const { result } = renderHook(() => useAgentChat("project-1"), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.setExecutionPolicy("bypass")
    })

    await act(async () => {
      await result.current.sendMessage("Start this with bypass approvals")
    })

    const messageCall = apiRequestMock.mock.calls.find(
      ([path, options]) => path === "/agent/message" && options?.method === "POST",
    )

    expect(messageCall).toBeDefined()
    expect(JSON.parse(String(messageCall?.[1]?.body))).toMatchObject({
      project_id: "project-1",
      content: "Start this with bypass approvals",
      execution_policy: "bypass",
    })
  })

  it("sends messages when crypto.randomUUID is unavailable", async () => {
    const originalCrypto = globalThis.crypto
    vi.stubGlobal("crypto", {
      ...originalCrypto,
      randomUUID: undefined,
      getRandomValues: originalCrypto.getRandomValues.bind(originalCrypto),
    })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/agent/message" && options?.method === "POST") {
        return {
          data: {
            conversation_id: "conversation-2",
            status: "processing",
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
      selectedProjectId: "project-1",
      conversationProjectId: "project-1",
      activeConversationId: "",
    })

    const { result } = renderHook(() => useAgentChat("project-1"), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.sendMessage("hello agent")
    })

    expect(apiRequestMock).toHaveBeenCalledWith(
      "/agent/message",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("hello agent"),
      }),
    )
  })
})

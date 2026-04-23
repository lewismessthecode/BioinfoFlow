import * as React from "react"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ChatStream } from "@/components/bioinfoflow/chat-stream"
import { createAppWrapper } from "@/tests/app-test-utils"
import { ApiError, apiRequest } from "@/lib/api"

const captured = vi.hoisted(() => ({
  onAgentEvent: null as ((event: unknown) => void) | null,
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}))

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => {
    const copy: Record<string, Record<string, string>> = {
      accessibility: {
        message: "Message",
        sendMessage: "Send message",
        stopGenerating: "Stop generating",
        selectProject: "Select a project to start",
      },
      greeting: {
        morning: "Good morning",
        afternoon: "Good afternoon",
        evening: "Good evening",
        lateNight: "Working late",
      },
      chat: {
        selectProject: "Select a project to start",
        selectProjectDescription:
          "Choose an existing workspace from the sidebar to continue your analysis, review past chats, or start a fresh run.",
        inboxWorkspaceTitle: "Assign a project to unlock workspace tools",
        inboxWorkspaceDescription:
          "Choose a project to let the agent edit files and run tools.",
        "quickStart.upload": "Upload data",
        "quickStart.tryDemo": "Try a demo",
        "quickStart.askQuestion": "Ask a question",
        "quickStart.uploadDescription": "Upload your data and let me inspect it.",
        "quickStart.tryDemoDescription": "Run a sample bioinformatics workflow.",
        "quickStart.askQuestionDescription": "Ask me to inspect this workspace.",
      },
      agent: {
        disclaimer: "Agent responses may make mistakes.",
      },
    }

    return (key: string) => copy[namespace]?.[key] ?? `${namespace}.${key}`
  },
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
    getApiErrorMessage: (error: unknown, fallback: string) =>
      error instanceof Error ? error.message : fallback,
  }
})

vi.mock("@/hooks/use-events", () => ({
  useEvents: (options: { onAgentEvent?: (event: unknown) => void }) => {
    captured.onAgentEvent = options.onAgentEvent ?? null
    return { connectionState: "connected" }
  },
}))

vi.mock("sonner", () => ({
  toast: {
    error: captured.toastError,
    success: captured.toastSuccess,
  },
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  useWorkspaceShell: () => ({
    isLoading: false,
    hasProjects: true,
    handleQuickCreateProject: vi.fn(),
    openCreateProjectDialog: vi.fn(),
  }),
}))

vi.mock("@/components/bioinfoflow/chat/model-selector", () => ({
  ModelSelector: () => <div data-testid="model-selector" />,
}))

vi.mock("@/components/bioinfoflow/chat/execution-mode-selector", () => ({
  ExecutionModeSelector: () => <div data-testid="execution-mode-selector" />,
}))

vi.mock("@/components/bioinfoflow/chat/scroll-to-bottom", () => ({
  ScrollToBottom: () => null,
}))

vi.mock("@/components/bioinfoflow/chat/bypass-banner", () => ({
  BypassBanner: () => null,
}))

describe("Agent capability paths", () => {
  const apiRequestMock = vi.mocked(apiRequest)
  const Wrapper = createAppWrapper({
    activeProjectId: "project-1",
    selectedProjectId: "project-1",
    conversationProjectId: "project-1",
  })
  const emitAgentEvent = (event: unknown) => {
    act(() => {
      captured.onAgentEvent?.(event)
    })
  }

  beforeEach(() => {
    apiRequestMock.mockReset()
    captured.onAgentEvent = null
    captured.toastError.mockReset()
    captured.toastSuccess.mockReset()
    window.localStorage.clear()
    Element.prototype.scrollIntoView = vi.fn()
  })

  it("supports a natural-language workflow request that generates, registers, approves, and starts a run", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/user-settings") {
        return {
          data: {
            provider_credentials: { openai: { api_key: "sk-test" } },
            selected_provider: "openai",
            selected_model: "gpt-test",
            configured_providers: ["openai"],
          },
          meta: undefined,
        }
      }
      if (path === "/user-settings/models") {
        return {
          data: [
            {
              provider: "openai",
              label: "OpenAI",
              models: [{ id: "gpt-test", name: "GPT Test", context_window: 128000 }],
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/agent/message" && options?.method === "POST") {
        return {
          data: {
            conversation_id: "conversation-1",
            response_id: "response-1",
          },
          meta: undefined,
        }
      }
      if (path === "/agent/approvals/approval-1/resolve" && options?.method === "POST") {
        return { data: { success: true }, meta: undefined }
      }
      if (path === "/agent/conversations/conversation-1") {
        return {
          data: {
            conversation_id: "conversation-1",
            project_id: "project-1",
            title: "Run RNA-seq on the workspace samples",
            pinned: false,
            messages: [],
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    render(<ChatStream projectId="project-1" workspaceEnabled />, { wrapper: Wrapper })

    await waitFor(() => expect(screen.getByTestId("model-selector")).toBeInTheDocument())

    const prompt =
      "Generate an RNA-seq workflow from these FASTQs, register it, and launch the run."
    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: prompt },
    })
    fireEvent.click(screen.getByRole("button", { name: "Send message" }))

    await waitFor(() => {
      expect(screen.getByText(prompt)).toBeInTheDocument()
    })
    expect(captured.onAgentEvent).not.toBeNull()

    await waitFor(() => {
      const call = apiRequestMock.mock.calls.find(
        ([path, options]) => path === "/agent/message" && options?.method === "POST"
      )
      expect(call).toBeDefined()
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        project_id: "project-1",
        content: prompt,
        model: "gpt-test",
      })
    })

    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "" },
    })

    emitAgentEvent({
      event: "agent.tool_call_start",
      conversation_id: "conversation-1",
      project_id: "project-1",
      timestamp: "2026-04-23T10:00:00Z",
      id: "evt-generate-start",
      data: {
        id: "response-1",
        metadata: {
          response_id: "response-1",
          id: "tool-1",
          name: "generate_workflow",
          args: { workflow_name: "rnaseq" },
        },
      },
    })
    emitAgentEvent({
      event: "agent.tool_call_end",
      conversation_id: "conversation-1",
      project_id: "project-1",
      timestamp: "2026-04-23T10:00:01Z",
      id: "evt-generate-end",
      data: {
        id: "response-1",
        metadata: {
          response_id: "response-1",
          id: "tool-1",
          name: "generate_workflow",
          result: "Drafted workflow",
          result_json: { summary: "Drafted workflow" },
          duration_ms: 420,
          is_error: false,
        },
      },
    })
    emitAgentEvent({
      event: "agent.tool_call_start",
      conversation_id: "conversation-1",
      project_id: "project-1",
      timestamp: "2026-04-23T10:00:02Z",
      id: "evt-register-start",
      data: {
        id: "response-1",
        metadata: {
          response_id: "response-1",
          id: "tool-2",
          name: "register_workflow",
          args: { workflow_name: "rnaseq" },
        },
      },
    })
    emitAgentEvent({
      event: "agent.tool_call_end",
      conversation_id: "conversation-1",
      project_id: "project-1",
      timestamp: "2026-04-23T10:00:03Z",
      id: "evt-register-end",
      data: {
        id: "response-1",
        metadata: {
          response_id: "response-1",
          id: "tool-2",
          name: "register_workflow",
          result: "Registered workflow",
          result_json: { summary: "Registered workflow" },
          duration_ms: 380,
          is_error: false,
        },
      },
    })
    emitAgentEvent({
      event: "agent.tool_call_start",
      conversation_id: "conversation-1",
      project_id: "project-1",
      timestamp: "2026-04-23T10:00:04Z",
      id: "evt-run-start",
      data: {
        id: "response-1",
        metadata: {
          response_id: "response-1",
          id: "tool-3",
          name: "submit_run",
          args: { workflow_name: "rnaseq", project_id: "project-1" },
        },
      },
    })
    emitAgentEvent({
      event: "agent.tool_call_progress",
      conversation_id: "conversation-1",
      project_id: "project-1",
      timestamp: "2026-04-23T10:00:05Z",
      id: "evt-run-progress",
      data: {
        id: "response-1",
        content: "Waiting for approval",
        metadata: {
          response_id: "response-1",
          id: "tool-3",
          name: "submit_run",
          status: "requires_approval",
          preview: "Waiting for approval",
        },
      },
    })
    emitAgentEvent({
      event: "agent.approval.requested",
      conversation_id: "conversation-1",
      project_id: "project-1",
      timestamp: "2026-04-23T10:00:06Z",
      id: "evt-approval",
      data: {
        approval_id: "approval-1",
        response_id: "response-1",
        tool: "submit_run",
        approval_type: "tool_risk",
        payload: {
          input: {
            workflow_name: "rnaseq",
            run_name: "rnaseq-project-1",
          },
          risk: "act_high",
        },
      },
    })

    await waitFor(() => {
      expect(screen.getByText("Waiting for approval")).toBeInTheDocument()
    })

    const toolsButton = screen.getByRole("button", { name: "Running tools (2/3)" })
    fireEvent.click(toolsButton)
    const expandedTools = toolsButton.parentElement
    expect(expandedTools).not.toBeNull()
    const toolsScope = within(expandedTools as HTMLElement)
    expect(toolsScope.getByText("generate_workflow")).toBeInTheDocument()
    expect(toolsScope.getByText("register_workflow")).toBeInTheDocument()
    expect(toolsScope.getByText("submit_run")).toBeInTheDocument()

    const approvalCard = screen.getByText("Approval required").closest("div[role='alert']")
    expect(approvalCard).not.toBeNull()
    const approvalScope = within(approvalCard as HTMLElement)
    expect(approvalScope.getByText("submit_run")).toBeInTheDocument()
    expect(approvalScope.getByText(/workflow_name: rnaseq/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Approve" }))

    await waitFor(() => {
      const call = apiRequestMock.mock.calls.find(
        ([path, options]) =>
          path === "/agent/approvals/approval-1/resolve" &&
          options?.method === "POST"
      )
      expect(call).toBeDefined()
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ action: "approve" })
    })

    emitAgentEvent({
      event: "agent.approval.resolved",
      conversation_id: "conversation-1",
      project_id: "project-1",
      timestamp: "2026-04-23T10:00:07Z",
      id: "evt-approval-resolved",
      data: {
        approval_id: "approval-1",
        status: "approved",
      },
    })
    emitAgentEvent({
      event: "agent.tool_call_end",
      conversation_id: "conversation-1",
      project_id: "project-1",
      timestamp: "2026-04-23T10:00:08Z",
      id: "evt-run-end",
      data: {
        id: "response-1",
        metadata: {
          response_id: "response-1",
          id: "tool-3",
          name: "submit_run",
          result: "Queued run run-123",
          result_json: { summary: "Queued run run-123" },
          duration_ms: 560,
          is_error: false,
        },
      },
    })
    emitAgentEvent({
      event: "agent.text_delta",
      conversation_id: "conversation-1",
      project_id: "project-1",
      timestamp: "2026-04-23T10:00:09Z",
      id: "evt-text",
      data: {
        id: "response-1",
        content: "Registered the workflow and queued run run-123.",
        metadata: {
          response_id: "response-1",
        },
      },
    })
    emitAgentEvent({
      event: "agent.done",
      conversation_id: "conversation-1",
      project_id: "project-1",
      timestamp: "2026-04-23T10:00:10Z",
      id: "evt-done",
      data: {
        id: "response-1",
        metadata: {
          input_tokens: 1000,
          output_tokens: 500,
          context_tokens: 2000,
        },
      },
    })

    await waitFor(() => {
      expect(screen.getByText("Approved")).toBeInTheDocument()
    })
    expect(
      screen.getByText("Registered the workflow and queued run run-123.")
    ).toBeInTheDocument()
    expect(screen.getByText("1.5k tokens")).toBeInTheDocument()
  })

  it("keeps the user's natural-language prompt visible and surfaces an explicit error when the agent cannot start", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/user-settings") {
        return {
          data: {
            provider_credentials: { openai: { api_key: "sk-test" } },
            selected_provider: "openai",
            selected_model: "gpt-test",
            configured_providers: ["openai"],
          },
          meta: undefined,
        }
      }
      if (path === "/user-settings/models") {
        return {
          data: [
            {
              provider: "openai",
              label: "OpenAI",
              models: [{ id: "gpt-test", name: "GPT Test", context_window: 128000 }],
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/agent/message" && options?.method === "POST") {
        throw new ApiError("Agent bootstrap failed", { status: 503 })
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    render(<ChatStream projectId="project-1" workspaceEnabled />, { wrapper: Wrapper })

    await waitFor(() => expect(screen.getByTestId("model-selector")).toBeInTheDocument())

    const prompt = "Create and run the best workflow for these files."
    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: prompt },
    })
    fireEvent.click(screen.getByRole("button", { name: "Send message" }))

    await waitFor(() => {
      expect(captured.toastError).toHaveBeenCalledWith("Agent bootstrap failed")
    })
    expect(screen.getByText(prompt)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Stop generating" })).not.toBeInTheDocument()
  })
})

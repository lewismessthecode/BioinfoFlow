import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach } from "vitest"

const useAgentChatMock = vi.fn()
const useLlmSettingsMock = vi.fn()
const useWorkspaceShellMock = vi.fn()

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => {
    const copy: Record<string, Record<string, string>> = {
      chat: {
        selectProject: "Select a project to start",
        selectProjectDescription: "Choose an existing workspace from the sidebar to continue your analysis, review past chats, or start a fresh run.",
      },
      welcome: {
        eyebrow: "Analysis Workspace",
        title: "Start your first analysis",
        subtitle: "Choose a project template or create a custom workspace.",
        blankName: "Blank Workspace",
        blankDescription: "Start with an empty project for ad hoc exploration",
        wgsName: "WGS Analysis",
        wgsDescription: "Whole genome sequencing variant calling",
        rnaseqName: "RNA-seq Analysis",
        rnaseqDescription: "Differential gene expression analysis",
        createFromTemplate: "Use Template",
        customProjectLabel: "Custom Setup",
        customProjectDescription: "Need a custom folder structure, naming scheme, or workspace path? Start with a blank project and configure it yourself.",
        customProject: "Create a custom project",
      },
      accessibility: {
        message: "Message",
        selectProject: "Select a project to start",
        attachFile: "Attach file",
        stopGenerating: "Stop generating",
        sendMessage: "Send message",
      },
      greeting: {
        morning: "Good morning",
        afternoon: "Good afternoon",
        evening: "Good evening",
        lateNight: "Working late",
      },
    }

    return copy[namespace]?.[key] ?? key
  },
}))

vi.mock("@/hooks/use-agent-chat", () => ({
  useAgentChat: (...args: unknown[]) => useAgentChatMock(...args),
}))

vi.mock("@/hooks/use-llm-settings", () => ({
  useLlmSettings: (...args: unknown[]) => useLlmSettingsMock(...args),
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  useWorkspaceShell: (...args: unknown[]) => useWorkspaceShellMock(...args),
}))

vi.mock("@/components/bioinfoflow/chat/model-selector", () => ({
  ModelSelector: () => <div data-testid="model-selector" />,
}))

vi.mock("@/components/bioinfoflow/chat/scroll-to-bottom", () => ({
  ScrollToBottom: () => null,
}))

vi.mock("@/components/bioinfoflow/chat/setup-banner", () => ({
  SetupBanner: () => null,
}))

import { ChatStream } from "@/components/bioinfoflow/chat-stream"

describe("ChatStream", () => {
  beforeEach(() => {
    useAgentChatMock.mockReset()
    useLlmSettingsMock.mockReset()
    useWorkspaceShellMock.mockReset()

    useAgentChatMock.mockReturnValue({
      messages: [],
      isLoading: false,
      status: "idle",
      sendMessage: vi.fn(),
      stop: vi.fn(),
      regenerate: vi.fn(),
      messagesEndRef: { current: null },
      scrollContainerRef: { current: null },
      scrollFabProps: {},
    })

    useLlmSettingsMock.mockReturnValue({
      models: [],
      selectedModel: null,
      setSelectedModel: vi.fn(),
      hasConfiguredProvider: true,
    })
  })

  it("shows workspace onboarding when no project exists", () => {
    useWorkspaceShellMock.mockReturnValue({
      isLoading: false,
      hasProjects: false,
      handleQuickCreateProject: vi.fn(),
      openCreateProjectDialog: vi.fn(),
    })

    render(<ChatStream />)

    expect(screen.getByText("Start your first analysis")).toBeInTheDocument()
    expect(screen.getByText("Blank Workspace")).toBeInTheDocument()
  })

  it("shows a project-selection empty state when workspaces already exist", () => {
    useWorkspaceShellMock.mockReturnValue({
      isLoading: false,
      hasProjects: true,
      handleQuickCreateProject: vi.fn(),
      openCreateProjectDialog: vi.fn(),
    })

    render(<ChatStream />)

    expect(screen.getByText("Select a project to start")).toBeInTheDocument()
    expect(
      screen.getByText(
        "Choose an existing workspace from the sidebar to continue your analysis, review past chats, or start a fresh run."
      )
    ).toBeInTheDocument()
  })
})

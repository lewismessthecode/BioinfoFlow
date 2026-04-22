import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { CommandPalette } from "@/components/bioinfoflow/command-palette"
import { apiRequest } from "@/lib/api"

const {
  pushMock,
  setSelectedProjectIdMock,
  setConversationProjectIdMock,
  setActiveConversationIdMock,
  setStoredConversationIdMock,
  translateMock,
  toastErrorMock,
  toastSuccessMock,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  setSelectedProjectIdMock: vi.fn(),
  setConversationProjectIdMock: vi.fn(),
  setActiveConversationIdMock: vi.fn(),
  setStoredConversationIdMock: vi.fn(),
  translateMock: vi.fn((key: string, values?: Record<string, string | number>) => {
    const labels: Record<string, string> = {
      searchPlaceholder: "Search",
      searchAriaLabel: "Search command palette",
      empty: "No results",
      "groups.actions": "Actions",
      "groups.projects": "Projects",
      "groups.conversations": "Conversations",
      "groups.runs": "Runs",
      "groups.workflows": "Workflows",
      "actions.newConversation": "New Conversation",
      "errors.loadFailed": "Load failed",
      "errors.createConversationFailed": "Create failed",
      conversationFallback: `Conversation ${values?.index ?? ""}`.trim(),
    }
    return labels[key] ?? key
  }),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => translateMock,
}))

vi.mock("@/components/bioinfoflow/project-context", () => ({
  useProjectContext: () => ({
    selectedProjectId: "",
    setSelectedProjectId: setSelectedProjectIdMock,
    conversationProjectId: "",
    setConversationProjectId: setConversationProjectIdMock,
    activeProjectId: "",
    setActiveProjectId: setSelectedProjectIdMock,
    activeConversationId: "",
    setActiveConversationId: setActiveConversationIdMock,
    activeProjectName: "",
    setActiveProjectName: vi.fn(),
    activeConversationTitle: "",
    setActiveConversationTitle: vi.fn(),
  }),
}))

vi.mock("@/lib/conversations", async () => {
  const actual = await vi.importActual<typeof import("@/lib/conversations")>("@/lib/conversations")
  return {
    ...actual,
    setStoredConversationId: setStoredConversationIdMock,
  }
})

vi.mock("@/lib/recent-conversations", () => ({
  getRecentConversations: () => [],
}))

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}))

vi.mock("@/components/ui/command", () => ({
  CommandDialog: ({
    open,
    children,
  }: {
    open: boolean
    children: React.ReactNode
  }) => (open ? <div>{children}</div> : null),
  CommandInput: ({
    placeholder,
    "aria-label": ariaLabel,
  }: {
    placeholder?: string
    "aria-label"?: string
  }) => <input aria-label={ariaLabel} placeholder={placeholder} />,
  CommandList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandEmpty: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandGroup: ({
    heading,
    children,
  }: {
    heading: string
    children: React.ReactNode
  }) => (
    <section aria-label={heading}>
      <div>{heading}</div>
      {children}
    </section>
  ),
  CommandItem: ({
    onSelect,
    children,
  }: {
    onSelect?: (value: string) => void
    children: React.ReactNode
  }) => <button onClick={() => onSelect?.("")}>{children}</button>,
  CommandSeparator: () => <hr />,
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
    getApiErrorMessage: vi.fn((_error: unknown, fallback: string) => fallback),
  }
})

describe("CommandPalette", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  beforeEach(() => {
    apiRequestMock.mockReset()
    pushMock.mockReset()
    setSelectedProjectIdMock.mockReset()
    setConversationProjectIdMock.mockReset()
    setActiveConversationIdMock.mockReset()
    setStoredConversationIdMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects/default") {
        return {
          data: {
            id: "project-default",
            name: "Recent",
            project_root: "asset://project",
            is_default: true,
          },
          meta: undefined,
        }
      }
      if (path === "/projects") {
        return {
          data: [
            { id: "project-b", name: "Bravo", project_root: "asset://project" },
            { id: "project-a", name: "Alpha", project_root: "asset://project" },
          ],
          meta: undefined,
        }
      }
      if (path === "/agent/conversations" && options?.method === "POST") {
        return {
          data: {
            id: "conversation-1",
            project_id: "project-default",
            title: "Untitled",
          },
          meta: undefined,
        }
      }
      if (path === "/workflows" || path === "/runs" || path === "/agent/conversations") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })
  })

  it("creates a new conversation in the default project without loading demo data", async () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />)

    expect(await screen.findByText("New Conversation")).toBeInTheDocument()
    expect(await screen.findByText("Bravo")).toBeInTheDocument()

    fireEvent.click(screen.getByText("New Conversation"))

    await waitFor(() => {
      const postCall = apiRequestMock.mock.calls.find(
        ([path, options]) =>
          path === "/agent/conversations" && options?.method === "POST"
      )
      expect(postCall).toBeDefined()
      expect(JSON.parse(postCall?.[1]?.body as string)).toEqual({})
    })

    expect(setSelectedProjectIdMock).toHaveBeenCalledWith("")
    expect(setConversationProjectIdMock).toHaveBeenCalledWith("project-default")
    expect(setActiveConversationIdMock).toHaveBeenCalledWith("conversation-1")
    expect(setStoredConversationIdMock).toHaveBeenCalledWith(
      "project-default",
      "conversation-1"
    )
    expect(apiRequestMock).not.toHaveBeenCalledWith("/demos", expect.anything())
  })
})

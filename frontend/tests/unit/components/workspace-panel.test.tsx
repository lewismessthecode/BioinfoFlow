import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

const {
  apiRequestMock,
  buildApiUrlMock,
  openInNewTabMock,
  toastErrorMock,
  toastWarningMock,
  useProjectContextMock,
  translateMock,
} = vi.hoisted(() => ({
  apiRequestMock: vi.fn(),
  buildApiUrlMock: vi.fn(),
  openInNewTabMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastWarningMock: vi.fn(),
  useProjectContextMock: vi.fn(),
  translateMock: vi.fn((key: string, values?: Record<string, string | number>) => {
    const copy: Record<string, string> = {
      loading: "Loading files",
      noFiles: "No files",
      selected: "Selected",
      "actions.preview": "Preview",
      "preview.title": "Preview",
      "preview.folder": "Folder preview",
      "preview.filesOnly": "Files only",
      "preview.loading": "Loading preview",
      "preview.unable": "Unable to preview",
      "preview.clickToLoad": "Click to load preview",
      "tree.loading": "Loading folder",
      "tree.empty": "Folder is empty",
      "errors.loadFilesFailed": "Load files failed",
      "errors.loadFolderFailed": "Load folder failed",
      "errors.previewFailed": "Preview failed",
      "errors.deleteFailed": "Delete failed",
      "toasts.deleteConfirmTitle": `Delete ${values?.name ?? ""}`.trim(),
      "toasts.deleteConfirmDescription": "Confirm delete",
      download: "Download",
      delete: "Delete",
      confirm: "Confirm",
      refreshWorkspace: "Refresh workspace",
    }
    if (key === "preview.lines") {
      return `First ${values?.count ?? 0} lines`
    }
    return copy[key] ?? key
  }),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => translateMock,
}))

vi.mock("@/components/bioinfoflow/project-context", () => ({
  useProjectContext: (...args: unknown[]) => useProjectContextMock(...args),
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: (...args: unknown[]) => apiRequestMock(...args),
    buildApiUrl: (...args: unknown[]) => buildApiUrlMock(...args),
    getApiErrorMessage: (_error: unknown, fallback: string) => fallback,
  }
})

vi.mock("@/lib/window-utils", () => ({
  openInNewTab: (...args: unknown[]) => openInNewTabMock(...args),
}))

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    warning: (...args: unknown[]) => toastWarningMock(...args),
  },
}))

import { WorkspacePanel } from "@/components/bioinfoflow/workspace-panel"

describe("WorkspacePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    buildApiUrlMock.mockReturnValue("https://download.test/file")
    useProjectContextMock.mockReturnValue({ activeProjectId: "project-1" })
  })

  it("shows an empty state without calling the API when no project is active", async () => {
    useProjectContextMock.mockReturnValue({ activeProjectId: null })

    render(<WorkspacePanel />)

    expect(await screen.findByText("No files")).toBeInTheDocument()
    expect(apiRequestMock).not.toHaveBeenCalled()
  })

  it("loads root files, hides dotfiles, and loads folder children on demand", async () => {
    apiRequestMock.mockImplementation(async (path: string, options?: { params?: Record<string, unknown> }) => {
      if (path === "/files" && options?.params?.path === ".") {
        return {
          data: {
            path: ".",
            files: [
              { name: ".hidden", type: "file", path: ".hidden" },
              { name: "results", type: "directory", path: "results" },
              { name: "report.txt", type: "file", path: "report.txt", size_bytes: 24 },
            ],
          },
        }
      }
      if (path === "/files" && options?.params?.path === "results") {
        return {
          data: {
            path: "results",
            files: [{ name: "child.txt", type: "file", path: "results/child.txt" }],
          },
        }
      }
      throw new Error(`Unexpected request: ${path}`)
    })

    render(<WorkspacePanel />)

    expect(await screen.findByText("report.txt")).toBeInTheDocument()
    expect(screen.queryByText(".hidden")).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: /results/i }))
    expect(await screen.findByText("child.txt")).toBeInTheDocument()
  })

  it("previews a selected file and downloads it through the helper URL", async () => {
    apiRequestMock.mockImplementation(async (path: string, options?: { params?: Record<string, unknown> }) => {
      if (path === "/files" && options?.params?.path === ".") {
        return {
          data: {
            path: ".",
            files: [{ name: "report.txt", type: "file", path: "report.txt", size_bytes: 24 }],
          },
        }
      }
      if (path === "/files/read") {
        return { data: { content: "preview line 1\npreview line 2" } }
      }
      throw new Error(`Unexpected request: ${path}`)
    })

    render(<WorkspacePanel />)

    await userEvent.click(await screen.findByRole("button", { name: /report.txt/i }))
    await userEvent.click(screen.getByRole("button", { name: "Preview" }))

    expect(await screen.findByText(/preview line 1/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: "Download" }))

    expect(buildApiUrlMock).toHaveBeenCalledWith("/files/download", {
      project_id: "project-1",
      path: "report.txt",
    })
    expect(openInNewTabMock).toHaveBeenCalledWith("https://download.test/file")
  })

  it("surfaces the delete confirmation toast and refreshes after confirmation", async () => {
    apiRequestMock.mockImplementation(async (path: string, options?: { method?: string; params?: Record<string, unknown> }) => {
      if (path === "/files" && !options?.method) {
        return {
          data: {
            path: ".",
            files: [{ name: "report.txt", type: "file", path: "report.txt", size_bytes: 24 }],
          },
        }
      }
      if (path === "/files" && options?.method === "DELETE") {
        return { data: null }
      }
      throw new Error(`Unexpected request: ${path}`)
    })

    render(<WorkspacePanel />)

    await userEvent.click(await screen.findByRole("button", { name: /report.txt/i }))
    await userEvent.click(screen.getByRole("button", { name: "Delete" }))

    expect(toastWarningMock).toHaveBeenCalled()
    const toastPayload = toastWarningMock.mock.calls[0]?.[1] as {
      action?: { onClick?: () => Promise<void> | void }
    }
    await toastPayload.action?.onClick?.()

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith("/files", {
        method: "DELETE",
        params: { project_id: "project-1", path: "report.txt" },
      })
    })
  })
})

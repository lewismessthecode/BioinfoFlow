import * as React from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { screen, waitFor } from "@testing-library/react"

import { FileBrowserDialog } from "@/components/bioinfoflow/file-browser-dialog"
import { apiRequest } from "@/lib/api"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return { ...actual, apiRequest: vi.fn() }
})

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({
    open,
    children,
  }: {
    open: boolean
    onOpenChange?: (open: boolean) => void
    children: React.ReactNode
  }) => (open ? <div>{children}</div> : null),
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

describe("FileBrowserDialog", () => {
  const apiMock = vi.mocked(apiRequest)

  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockImplementation(async (path) => {
      if (path === "/storage/sources") {
        return {
          data: [
            { id: "project", label: "Project", kind: "project", upload_allowed: true },
            { id: "results", label: "Results", kind: "results", upload_allowed: false },
            { id: "deliveries", label: "Deliveries", kind: "deliveries", upload_allowed: false },
            { id: "reference", label: "Reference", kind: "reference", upload_allowed: false },
            { id: "database", label: "Database", kind: "database", upload_allowed: false },
          ],
        }
      }
      if (path === "/storage/browse") {
        return {
          data: { path: ".", files: [] },
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })
  })

  it("shows only the allowed storage sources", async () => {
    renderWithProviders(
      <FileBrowserDialog
        open={true}
        onOpenChange={vi.fn()}
        projectId="proj-1"
        basePath="."
        title="Reads"
        allowedSourceKinds={["project", "deliveries"]}
        preferredSourceKind="deliveries"
        onSelect={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Project" })).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "Deliveries" })).toBeInTheDocument()
    })

    expect(screen.queryByRole("button", { name: "Reference" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Results" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Database" })).not.toBeInTheDocument()
  })
})

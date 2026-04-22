import * as React from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { fireEvent, screen, waitFor } from "@testing-library/react"

import { RunSubmissionWizard } from "@/app/(app)/workflows/components/run-submission-wizard"
import { apiRequest } from "@/lib/api"
import { renderWithProviders } from "@/tests/test-utils"
import type { Workflow } from "@/lib/types"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
    if (!values) return key
    return Object.entries(values).reduce(
      (s, [k, v]) => s.replaceAll(`{${k}}`, String(v)),
      key,
    )
  },
}))

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return { ...actual, apiRequest: vi.fn() }
})

vi.mock("@/components/bioinfoflow/file-browser-dialog", () => ({
  FileBrowserDialog: () => null,
}))

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: { open: boolean; children: React.ReactNode }) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}))

const WORKFLOW: Workflow = {
  id: "wf-1",
  name: "Demo",
  source: "local",
  engine: "wdl",
  version: "1.0.0",
}

const apiMock = apiRequest as unknown as ReturnType<typeof vi.fn>

beforeEach(() => {
  apiMock.mockReset()
  apiMock.mockImplementation((path: string) => {
    if (path.endsWith("/form-spec")) {
      return Promise.resolve({
        data: {
          fields: [
            {
              id: "reads",
              label: "Reads",
              section: "data",
              kind: "string",
              required: true,
              default: null,
              platform_managed: false,
            },
          ],
        },
      })
    }
    if (path === "/runs") {
      return Promise.resolve({ data: { run_id: "r-1" } })
    }
    return Promise.resolve({ data: {} })
  })
})

describe("RunSubmissionWizard (new envelope)", () => {
  it("loads form spec and submits the new envelope payload", async () => {
    renderWithProviders(
      <RunSubmissionWizard
        open={true}
        onOpenChange={vi.fn()}
        projectId="proj-1"
        initialWorkflowId="wf-1"
        availableWorkflows={[WORKFLOW]}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText("Reads")).toBeInTheDocument()
    })

    const inputs = await screen.findAllByRole("textbox")
    const input = inputs[0]
    expect(input).toBeDefined()
    fireEvent.change(input, { target: { value: "/data/reads.fastq" } })

    fireEvent.click(screen.getByText("submitRun"))

    await waitFor(() => {
      const runsCall = apiMock.mock.calls.find(([path]) => path === "/runs")
      expect(runsCall).toBeDefined()
      const body = JSON.parse((runsCall![1] as { body: string }).body)
      expect(body).toMatchObject({
        project_id: "proj-1",
        workflow_id: "wf-1",
        values: { reads: "/data/reads.fastq" },
      })
    })
  })
})

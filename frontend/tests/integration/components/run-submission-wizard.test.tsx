import * as React from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { toast } from "sonner"

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
  vi.mocked(toast.error).mockReset()
  vi.mocked(toast.success).mockReset()
  vi.mocked(toast.info).mockReset()
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

  it("imports a WDL inputs JSON file into the canonical run values", async () => {
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith("/form-spec")) {
        return Promise.resolve({
          data: {
            fields: [
              {
                id: "sample_name",
                label: "Sample name",
                section: "params",
                kind: "string",
                required: true,
                default: null,
                platform_managed: false,
              },
              {
                id: "fastq_r1",
                label: "Fastq r1",
                section: "data",
                kind: "file",
                required: true,
                default: null,
                platform_managed: false,
                allow_roots: ["shared_data", "reference", "database", "project_data"],
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

    const { container } = renderWithProviders(
      <RunSubmissionWizard
        open={true}
        onOpenChange={vi.fn()}
        projectId="proj-1"
        initialWorkflowId="wf-1"
        availableWorkflows={[WORKFLOW]}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText("Sample name")).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText("workbench.inputFileTab"))
    const importInput = container.querySelector(
      'input[type="file"][accept*=".json"]',
    ) as HTMLInputElement | null
    expect(importInput).not.toBeNull()
    const file = new File(
      [
        JSON.stringify({
          "Demo.sample_name": "S1",
          "Demo.fastq_r1": "asset://deliveries/S1_R1.fastq.gz",
        }),
      ],
      "inputs.json",
      { type: "application/json" },
    )
    fireEvent.change(importInput as HTMLInputElement, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByDisplayValue("S1")).toBeInTheDocument()
      expect(screen.getByDisplayValue("asset://deliveries/S1_R1.fastq.gz")).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText("submitRun"))

    await waitFor(() => {
      const runsCall = apiMock.mock.calls.find(([path]) => path === "/runs")
      expect(runsCall).toBeDefined()
      const body = JSON.parse((runsCall![1] as { body: string }).body)
      expect(body.values).toMatchObject({
        sample_name: "S1",
        fastq_r1: "asset://deliveries/S1_R1.fastq.gz",
      })
    })
  })

  it("imports a Nextflow params JSON file into values and run profile", async () => {
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith("/form-spec")) {
        return Promise.resolve({
          data: {
            fields: [
              {
                id: "input",
                label: "Input",
                section: "data",
                kind: "file",
                required: true,
                default: null,
                platform_managed: false,
                allow_roots: ["shared_data", "reference", "database", "project_data"],
              },
              {
                id: "genome",
                label: "Genome",
                section: "params",
                kind: "select",
                required: false,
                default: "GRCh38",
                platform_managed: false,
                options: [
                  { value: "GRCh37", label: "GRCh37" },
                  { value: "GRCh38", label: "GRCh38" },
                ],
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

    const nfcoreWorkflow: Workflow = {
      id: "wf-nfcore",
      name: "nf-core/rnaseq",
      source: "nf-core",
      engine: "nextflow",
      version: "3.24.0",
    }

    const { container } = renderWithProviders(
      <RunSubmissionWizard
        open={true}
        onOpenChange={vi.fn()}
        projectId="proj-1"
        initialWorkflowId="wf-nfcore"
        availableWorkflows={[nfcoreWorkflow]}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText("Input")).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText("workbench.inputFileTab"))
    const importInput = container.querySelector(
      'input[type="file"][accept*=".json"]',
    ) as HTMLInputElement | null
    expect(importInput).not.toBeNull()
    const file = new File(
      [
        JSON.stringify({
          pipeline: "nf-core/rnaseq",
          revision: "9.9.9",
          profile: "test,docker",
          input: "asset://project/samplesheet.csv",
          genome: "GRCh37",
        }),
      ],
      "params.json",
      { type: "application/json" },
    )
    fireEvent.change(importInput as HTMLInputElement, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByDisplayValue("asset://project/samplesheet.csv")).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText("preview"))

    await waitFor(() => {
      expect(screen.getByText(/"profile": "test,docker"/)).toBeInTheDocument()
      expect(screen.getByText(/"input": "asset:\/\/project\/samplesheet.csv"/)).toBeInTheDocument()
      expect(screen.queryByText(/"revision": "9.9.9"/)).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByText("submitRun"))

    await waitFor(() => {
      const runsCall = apiMock.mock.calls.find(([path]) => path === "/runs")
      expect(runsCall).toBeDefined()
      const body = JSON.parse((runsCall![1] as { body: string }).body)
      expect(body.values).toMatchObject({
        input: "asset://project/samplesheet.csv",
        genome: "GRCh37",
      })
      expect(body.options.profile).toBe("test,docker")
    })
  })

  it("shows an import failure toast when JSON has no matching fields or options", async () => {
    const { container } = renderWithProviders(
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

    fireEvent.click(screen.getByText("workbench.inputFileTab"))
    const importInput = container.querySelector(
      'input[type="file"][accept*=".json"]',
    ) as HTMLInputElement | null
    expect(importInput).not.toBeNull()
    const file = new File(
      [JSON.stringify({ pipeline: "nf-core/rnaseq", revision: "3.24.0", unknown: true })],
      "params.json",
      { type: "application/json" },
    )
    fireEvent.change(importInput as HTMLInputElement, { target: { files: [file] } })

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("workbench.inputFileNoTarget")
    })
    expect(toast.success).not.toHaveBeenCalled()
  })

  it("uploads a prepared CSV input file into a materialized file field", async () => {
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith("/form-spec")) {
        return Promise.resolve({
          data: {
            fields: [
              {
                id: "samplesheet",
                label: "Samplesheet",
                section: "data",
                kind: "file",
                required: true,
                default: null,
                platform_managed: false,
                materialize_to_run: true,
                allow_roots: ["shared_data", "reference", "database", "project_data"],
              },
            ],
          },
        })
      }
      if (path === "/runs/uploads") {
        return Promise.resolve({
          data: { uri: "asset://run_upload/upload-1/samplesheet.csv" },
        })
      }
      if (path === "/runs") {
        return Promise.resolve({ data: { run_id: "r-1" } })
      }
      return Promise.resolve({ data: {} })
    })

    const { container } = renderWithProviders(
      <RunSubmissionWizard
        open={true}
        onOpenChange={vi.fn()}
        projectId="proj-1"
        initialWorkflowId="wf-1"
        availableWorkflows={[WORKFLOW]}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText("Samplesheet")).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText("workbench.inputFileTab"))
    const importInput = container.querySelector(
      'input[type="file"][accept*=".csv"]',
    ) as HTMLInputElement | null
    expect(importInput).not.toBeNull()
    const file = new File(["sample,fastq_1\nS1,S1_R1.fastq.gz\n"], "samplesheet.csv", {
      type: "text/csv",
    })
    fireEvent.change(importInput as HTMLInputElement, { target: { files: [file] } })

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith(
        "/runs/uploads",
        expect.objectContaining({
          method: "POST",
          body: expect.any(FormData),
        }),
      )
      expect(screen.getByDisplayValue("asset://run_upload/upload-1/samplesheet.csv")).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText("submitRun"))

    await waitFor(() => {
      const runsCall = apiMock.mock.calls.find(([path]) => path === "/runs")
      expect(runsCall).toBeDefined()
      const body = JSON.parse((runsCall![1] as { body: string }).body)
      expect(body.values).toMatchObject({
        samplesheet: "asset://run_upload/upload-1/samplesheet.csv",
      })
    })
  })
})

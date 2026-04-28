import * as React from "react"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { RunForm } from "@/app/(app)/workflows/components/run-form/run-form"
import type { FormSpec } from "@/lib/form-spec"
import { apiRequest } from "@/lib/api"
import { renderWithProviders } from "@/tests/test-utils"

const { fileBrowserDialogMock } = vi.hoisted(() => ({
  fileBrowserDialogMock: vi.fn(),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
    if (!values) return key
    return Object.entries(values).reduce(
      (s, [k, v]) => s.replaceAll(`{${k}}`, String(v)),
      key,
    )
  },
}))

vi.mock("@/components/bioinfoflow/file-browser-dialog", () => ({
  FileBrowserDialog: (props: Record<string, unknown>) => {
    fileBrowserDialogMock(props)
    return props.open ? <div data-testid="file-browser-dialog" /> : null
  },
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return { ...actual, apiRequest: vi.fn() }
})

const SPEC: FormSpec = {
  fields: [
    {
      id: "reads",
      label: "Reads",
      section: "data",
      kind: "file",
      required: true,
      default: null,
      help: "Input reads",
      platform_managed: false,
      allow_roots: ["project_data"],
    },
    {
      id: "threads",
      label: "Threads",
      section: "params",
      kind: "int",
      required: false,
      default: 8,
      platform_managed: false,
    },
    {
      id: "skip",
      label: "Skip",
      section: "params",
      kind: "bool",
      required: false,
      default: false,
      platform_managed: false,
    },
    {
      id: "outdir",
      label: "Output dir",
      section: "advanced",
      kind: "string",
      required: false,
      default: "results",
      platform_managed: true,
    },
  ],
}

describe("RunForm", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  beforeEach(() => {
    apiRequestMock.mockReset()
  })

  it("passes every browsable input source kind to file and table pickers", () => {
    fileBrowserDialogMock.mockClear()
    const spec: FormSpec = {
      fields: [
        {
          id: "reads",
          label: "Reads",
          section: "data",
          kind: "file",
          required: true,
          default: null,
          platform_managed: false,
          allow_roots: ["shared_data", "reference", "database", "project_data"],
        },
        {
          id: "sheet",
          label: "Sheet",
          section: "data",
          kind: "table",
          required: false,
          default: null,
          platform_managed: false,
          allow_roots: ["reference", "shared_data", "database", "project_data"],
          columns: [
            { name: "sample", required: true, kind: "string" },
            { name: "reference_path", required: true, kind: "path" },
          ],
        },
      ],
    }

    renderWithProviders(
      <RunForm
        spec={spec}
        projectId="proj-1"
        values={{
          reads: "",
          sheet: { filename: "sheet.csv", rows: [{ sample: "S1", reference_path: "" }] },
        }}
        onChange={vi.fn()}
      />,
    )

    fireEvent.click(screen.getAllByRole("button", { name: "browse" })[0])
    expect(fileBrowserDialogMock.mock.calls.at(-1)?.[0]).toMatchObject({
      allowedSourceKinds: ["deliveries", "reference", "database", "project"],
      preferredSourceKind: "deliveries",
    })

    fireEvent.click(screen.getAllByRole("button", { name: "browse" })[1])
    expect(fileBrowserDialogMock.mock.calls.at(-1)?.[0]).toMatchObject({
      allowedSourceKinds: ["reference", "deliveries", "database", "project"],
      preferredSourceKind: "reference",
    })
  })

  it("renders fields grouped by section and surfaces required-field affordances", () => {
    renderWithProviders(
      <RunForm
        spec={SPEC}
        projectId="proj-1"
        values={{ threads: 8, skip: false }}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByText("section.data")).toBeInTheDocument()
    expect(screen.getByText("section.params")).toBeInTheDocument()
    expect(screen.getByText("Reads")).toBeInTheDocument()
    expect(screen.getByText("Threads")).toBeInTheDocument()
    // platform_managed field never renders
    expect(screen.queryByText("Output dir")).not.toBeInTheDocument()
    // required marker
    expect(screen.getAllByText("*").length).toBeGreaterThan(0)
  })

  it("emits onChange for scalar inputs", () => {
    const onChange = vi.fn()
    renderWithProviders(
      <RunForm
        spec={SPEC}
        projectId="proj-1"
        values={{ threads: 8, skip: false }}
        onChange={onChange}
      />,
    )
    const numberInput = screen.getByDisplayValue("8")
    fireEvent.change(numberInput, { target: { value: "16" } })
    expect(onChange).toHaveBeenCalledWith("threads", 16)
  })

  it("renders inline issue messages tied to a field", () => {
    renderWithProviders(
      <RunForm
        spec={SPEC}
        projectId="proj-1"
        values={{}}
        onChange={vi.fn()}
        issues={[{ fieldId: "reads", message: "Reads is required" }]}
      />,
    )
    expect(screen.getByRole("alert")).toHaveTextContent("Reads is required")
  })

  it("uploads manifest-style file inputs and emits the returned run-upload uri", async () => {
    apiRequestMock.mockResolvedValue({
      data: { uri: "asset://run_upload/upload-1/samplesheet.csv" },
      meta: undefined,
    })
    const onChange = vi.fn()
    const spec: FormSpec = {
      fields: [
        {
          id: "samplesheet",
          label: "Samplesheet",
          section: "data",
          kind: "file",
          required: true,
          default: null,
          platform_managed: false,
          allow_roots: ["project_data", "shared_data"],
          materialize_to_run: true,
        },
      ],
    }

    const { container } = renderWithProviders(
      <RunForm
        spec={spec}
        projectId="proj-1"
        values={{ samplesheet: "" }}
        onChange={onChange}
      />,
    )

    const uploadInput = container.querySelector('input[type="file"]') as HTMLInputElement | null
    expect(uploadInput).not.toBeNull()
    const file = new File(["sample,fastq_1\n"], "samplesheet.csv", { type: "text/csv" })
    fireEvent.change(uploadInput as HTMLInputElement, { target: { files: [file] } })

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/runs/uploads",
        expect.objectContaining({
          method: "POST",
          body: expect.any(FormData),
        }),
      )
      expect(onChange).toHaveBeenCalledWith(
        "samplesheet",
        "asset://run_upload/upload-1/samplesheet.csv",
      )
    })
  })
})

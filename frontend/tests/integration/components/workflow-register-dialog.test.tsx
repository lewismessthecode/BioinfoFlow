import * as React from "react"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { WorkflowRegisterDialog } from "@/app/(app)/workflows/components/workflow-register-dialog"
import { apiRequest } from "@/lib/api"
import { renderAppPage } from "@/tests/app-test-utils"

const { toastErrorMock, toastSuccessMock } = vi.hoisted(() => ({
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
}))

const translationMocks = new Map<
  string,
  (key: string, values?: Record<string, unknown>) => string
>()

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => {
    if (!translationMocks.has(namespace)) {
      translationMocks.set(
        namespace,
        (key: string, values?: Record<string, unknown>) => {
          const suffix = values
            ? Object.values(values)
                .filter((value) => value !== undefined && value !== null)
                .join(":")
            : ""
          return suffix ? `${namespace}.${key}:${suffix}` : `${namespace}.${key}`
        }
      )
    }
    return translationMocks.get(namespace)!
  },
}))

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}))

vi.mock("@uiw/react-codemirror", () => ({
  default: ({
    value,
    onChange,
  }: {
    value: string
    onChange: (value: string) => void
  }) => (
    <textarea
      aria-label="workflow-editor"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({
    open,
    children,
  }: {
    open: boolean
    children: React.ReactNode
  }) => (open ? <div>{children}</div> : null),
  DialogContent: ({
    children,
    className,
    ...props
  }: React.HTMLAttributes<HTMLDivElement>) => (
    <div className={className} {...props}>
      {children}
    </div>
  ),
  DialogHeader: ({
    children,
    className,
    ...props
  }: React.HTMLAttributes<HTMLDivElement>) => (
    <div className={className} {...props}>
      {children}
    </div>
  ),
  DialogTitle: ({
    children,
    className,
    ...props
  }: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h2 className={className} {...props}>
      {children}
    </h2>
  ),
  DialogDescription: ({
    children,
    className,
    ...props
  }: React.HTMLAttributes<HTMLParagraphElement>) => (
    <p className={className} {...props}>
      {children}
    </p>
  ),
  DialogFooter: ({
    children,
    className,
    ...props
  }: React.HTMLAttributes<HTMLDivElement>) => (
    <div className={className} {...props}>
      {children}
    </div>
  ),
}))

describe("WorkflowRegisterDialog", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  const latestWorkflowJsonPayload = () => {
    const createCall = [...apiRequestMock.mock.calls]
      .reverse()
      .find(([path]) => path === "/workflows")
    expect(createCall).toBeDefined()
    const options = createCall?.[1] as { body?: string } | undefined
    expect(options?.body).toBeTruthy()
    return JSON.parse(options?.body ?? "{}") as Record<string, unknown>
  }

  const latestBundleUpload = () => {
    const createCall = [...apiRequestMock.mock.calls]
      .reverse()
      .find(([path]) => path === "/workflows/local-bundle")
    expect(createCall).toBeDefined()
    const options = createCall?.[1] as { body?: FormData } | undefined
    expect(options?.body).toBeInstanceOf(FormData)
    return options?.body as FormData
  }

  const fileWithRelativePath = (
    contents: string,
    name: string,
    relativePath: string,
    type = "text/plain",
  ) => {
    const file = new File([contents], name, { type })
    Object.defineProperty(file, "webkitRelativePath", {
      configurable: true,
      value: relativePath,
    })
    return file
  }

  beforeEach(() => {
    apiRequestMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("shows a compact local WDL registration preview without the legacy production warning copy", async () => {
    renderAppPage(
      <WorkflowRegisterDialog
        open
        onOpenChange={() => {}}
        onRegistered={() => {}}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "workflows.registerDialog.sourceTypes.local" }))
    fireEvent.click(screen.getByRole("button", { name: "workflows.registerDialog.localModes.singleFile" }))

    const fileInput = screen.getByLabelText("workflows.registerDialog.fields.workflowFile")
    fireEvent.change(fileInput, {
      target: {
        files: [
          new File(
            [
              "version 1.0\nworkflow Deaf_20 {\n  input {\n    File sequence_list\n  }\n}\n",
            ],
            "Deaf_20.wdl",
            { type: "text/plain" }
          ),
        ],
      },
    })

    expect(
      await screen.findByText("workflows.registerDialog.preview.title")
    ).toBeInTheDocument()
    expect(
      screen.getByText("workflows.registerDialog.preview.nameLabel")
    ).toBeInTheDocument()
    expect(screen.getByText("Deaf_20")).toBeInTheDocument()
    expect(
      screen.getByText("workflows.registerDialog.preview.fileName:Deaf_20.wdl")
    ).toBeInTheDocument()
    expect(
      screen.getByText("workflows.registerDialog.preview.detectedEngine:wdl")
    ).toBeInTheDocument()
    expect(
      screen.getByText("workflows.registerDialog.preview.dagPreviewEmpty")
    ).toBeInTheDocument()
    expect(
      screen.queryByText("workflows.registerDialog.preview.imageRegistry")
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText("workflows.registerDialog.preview.productionWdlTitle")
    ).not.toBeInTheDocument()
  })

  it("renders workflow registration actions in a dedicated dialog footer", async () => {
    renderAppPage(
      <WorkflowRegisterDialog
        open
        onOpenChange={() => {}}
        onRegistered={() => {}}
      />
    )

    const footer = screen.getByTestId("workflow-register-actions")
    expect(footer).toHaveClass("shrink-0")
    expect(footer).toHaveClass("justify-end")
    expect(footer).toContainElement(screen.getByRole("button", { name: "common.cancel" }))
    expect(footer).toContainElement(screen.getByRole("button", { name: "workflows.register" }))
    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledWith("/container-registries"))
  })

  it("submits the inferred local WDL metadata when the user registers", async () => {
    const onRegistered = vi.fn()
    const onOpenChange = vi.fn()

    apiRequestMock.mockResolvedValue({
      data: {
        id: "workflow-local-1",
        name: "Deaf_20",
        source: "local",
        engine: "wdl",
        version: "draft",
      },
      meta: undefined,
    })

    renderAppPage(
      <WorkflowRegisterDialog
        open
        onOpenChange={onOpenChange}
        onRegistered={onRegistered}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "workflows.registerDialog.sourceTypes.local" }))
    fireEvent.click(screen.getByRole("button", { name: "workflows.registerDialog.localModes.singleFile" }))
    fireEvent.change(screen.getByLabelText("workflows.registerDialog.fields.workflowFile"), {
      target: {
        files: [
          new File(
            ["version 1.0\nworkflow Deaf_20 {}\n"],
            "Deaf_20.wdl",
            { type: "text/plain" }
          ),
        ],
      },
    })

    fireEvent.click(screen.getByRole("button", { name: "workflows.register" }))

    await waitFor(() => {
      expect(latestWorkflowJsonPayload()).toEqual({
        source: "local",
        engine: "wdl",
        file_name: "Deaf_20.wdl",
        content: "version 1.0\nworkflow Deaf_20 {}\n",
        name: "Deaf_20",
      })
    })

    expect(onRegistered).toHaveBeenCalledWith(
      expect.objectContaining({ id: "workflow-local-1", name: "Deaf_20" })
    )
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(toastSuccessMock).toHaveBeenCalledWith('workflows.toasts.registered:Deaf_20')
  })

  it("registers an nf-core workflow through the real source selector and trims the catalog prefix", async () => {
    const onRegistered = vi.fn()

    apiRequestMock.mockResolvedValue({
      data: {
        id: "workflow-nfcore-1",
        name: "rnaseq",
        source: "nf-core",
        engine: "nextflow",
        version: "3.18.0",
      },
      meta: undefined,
    })

    renderAppPage(
      <WorkflowRegisterDialog
        open
        onOpenChange={() => {}}
        onRegistered={onRegistered}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "nf-core" }))
    fireEvent.change(screen.getByLabelText("workflows.registerDialog.fields.pipelineName"), {
      target: { value: "nf-core/rnaseq" },
    })
    fireEvent.change(screen.getByLabelText("workflows.version"), {
      target: { value: "3.18.0" },
    })
    fireEvent.change(screen.getByLabelText("workflows.registerDialog.fields.description"), {
      target: { value: "RNA-seq main path" },
    })

    fireEvent.click(screen.getByRole("button", { name: "workflows.register" }))

    await waitFor(() => {
      expect(latestWorkflowJsonPayload()).toEqual({
        source: "nf-core",
        engine: "nextflow",
        name: "rnaseq",
        version: "3.18.0",
        description: "RNA-seq main path",
      })
    })

    expect(onRegistered).toHaveBeenCalledWith(
      expect.objectContaining({ id: "workflow-nfcore-1", name: "rnaseq" })
    )
    expect(toastSuccessMock).toHaveBeenCalledWith("workflows.toasts.registered:rnaseq")
  })

  it("registers a GitHub workflow through the real source selector using source_ref", async () => {
    const onRegistered = vi.fn()

    apiRequestMock.mockResolvedValue({
      data: {
        id: "workflow-github-1",
        name: "nf-core/rnaseq",
        source: "github",
        engine: "nextflow",
        version: "main",
      },
      meta: undefined,
    })

    renderAppPage(
      <WorkflowRegisterDialog
        open
        onOpenChange={() => {}}
        onRegistered={onRegistered}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "GitHub" }))
    fireEvent.change(screen.getByLabelText("workflows.registerDialog.fields.repoUrl"), {
      target: { value: "https://github.com/nf-core/rnaseq" },
    })
    fireEvent.change(screen.getByLabelText("workflows.version"), {
      target: { value: "main" },
    })
    fireEvent.change(screen.getByLabelText("workflows.registerDialog.fields.description"), {
      target: { value: "GitHub registration path" },
    })

    fireEvent.click(screen.getByRole("button", { name: "workflows.register" }))

    await waitFor(() => {
      expect(latestWorkflowJsonPayload()).toEqual({
        source: "github",
        engine: "nextflow",
        source_ref: "https://github.com/nf-core/rnaseq",
        version: "main",
        description: "GitHub registration path",
      })
    })

    expect(onRegistered).toHaveBeenCalledWith(
      expect.objectContaining({ id: "workflow-github-1", source: "github" })
    )
    expect(toastSuccessMock).toHaveBeenCalledWith("workflows.toasts.registered:nf-core/rnaseq")
  })

  it("lets the user choose a configured image registry for workflow registration", async () => {
    const onRegistered = vi.fn()

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/container-registries") {
        return {
          data: [
            {
              id: "registry-harbor",
              name: "Lab Harbor",
              endpoint: "harbor.local:5000",
              provider: "harbor",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/workflows" && options?.method === "POST") {
        return {
          data: {
            id: "workflow-nfcore-1",
            name: "rnaseq",
            source: "nf-core",
            engine: "nextflow",
            version: "3.18.0",
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(
      <WorkflowRegisterDialog
        open
        onOpenChange={() => {}}
        onRegistered={onRegistered}
      />
    )

    const registrySelect = await screen.findByLabelText(
      "workflows.registerDialog.fields.imageRegistry"
    )
    expect(registrySelect).toHaveValue("")
    expect(screen.getAllByText("workflows.registerDialog.registry.automatic").length).toBeGreaterThanOrEqual(1)

    fireEvent.change(registrySelect, { target: { value: "registry-harbor" } })

    expect(screen.getByText("workflows.registerDialog.preview.imageRegistry")).toBeInTheDocument()
    expect(screen.getAllByText("Lab Harbor (harbor.local:5000)").length).toBeGreaterThanOrEqual(1)

    fireEvent.change(screen.getByLabelText("workflows.registerDialog.fields.pipelineName"), {
      target: { value: "nf-core/rnaseq" },
    })
    fireEvent.change(screen.getByLabelText("workflows.version"), {
      target: { value: "3.18.0" },
    })

    fireEvent.click(screen.getByRole("button", { name: "workflows.register" }))

    await waitFor(() => {
      expect(latestWorkflowJsonPayload()).toEqual({
        source: "nf-core",
        engine: "nextflow",
        name: "rnaseq",
        version: "3.18.0",
        container_registry_id: "registry-harbor",
      })
    })

    expect(onRegistered).toHaveBeenCalledWith(
      expect.objectContaining({ id: "workflow-nfcore-1", name: "rnaseq" })
    )
  })

  it("submits a selected local bundle as multipart data and lets the user choose the entrypoint", async () => {
    const onRegistered = vi.fn()

    apiRequestMock.mockResolvedValue({
      data: {
        id: "workflow-local-bundle-1",
        name: "rnaseq-quant-mini",
        source: "local",
        engine: "nextflow",
        version: "local",
        entrypoint_relpath: "rnaseq_quant.nf",
      },
      meta: undefined,
    })

    renderAppPage(
      <WorkflowRegisterDialog
        open
        onOpenChange={() => {}}
        onRegistered={onRegistered}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "workflows.registerDialog.sourceTypes.local" }))
    const bundleInput = screen.getByLabelText("workflows.registerDialog.fields.bundleUpload")
    fireEvent.change(bundleInput, {
      target: {
        files: [
          fileWithRelativePath(
            "nextflow.enable.dsl=2\nincludeConfig 'nextflow.config'\nworkflow { }\n",
            "rnaseq_quant.nf",
            "rnaseq-quant-mini/rnaseq_quant.nf",
            "application/octet-stream",
          ),
          fileWithRelativePath(
            "process.shell = ['/bin/bash', '-euo', 'pipefail']\n",
            "nextflow.config",
            "rnaseq-quant-mini/nextflow.config",
            "application/octet-stream",
          ),
          fileWithRelativePath(
            "sample,fastq_1,fastq_2\n",
            "samplesheet.csv",
            "rnaseq-quant-mini/data/samplesheet.csv",
            "text/csv",
          ),
        ],
      },
    })

    fireEvent.click(screen.getByRole("button", { name: "workflows.registerDialog.actions.chooseEntrypoint" }))
    const [entrypointOption] = await screen.findAllByText("rnaseq_quant.nf")
    fireEvent.click(entrypointOption.closest("button") ?? entrypointOption)

    fireEvent.change(screen.getByLabelText("workflows.registerDialog.fields.workflowNameOptional"), {
      target: { value: "rnaseq-quant-mini" },
    })

    fireEvent.click(screen.getByRole("button", { name: "workflows.register" }))

    await waitFor(() => {
      const formData = latestBundleUpload()
      expect(formData.get("engine")).toBe("nextflow")
      expect(formData.get("name")).toBe("rnaseq-quant-mini")
      expect(formData.get("entrypoint_relpath")).toBe("rnaseq_quant.nf")
      const bundlePaths = JSON.parse(String(formData.get("bundle_paths"))) as string[]
      expect(bundlePaths).toHaveLength(3)
      expect([...bundlePaths].sort()).toEqual([
        "data/samplesheet.csv",
        "nextflow.config",
        "rnaseq_quant.nf",
      ])
      expect(formData.getAll("bundle_files")).toHaveLength(3)
    })

    expect(onRegistered).toHaveBeenCalledWith(
      expect.objectContaining({ id: "workflow-local-bundle-1", name: "rnaseq-quant-mini" })
    )
  })

  it("uses a local-workflow specific fallback message when registration fails", async () => {
    apiRequestMock.mockRejectedValue(new Error())

    renderAppPage(
      <WorkflowRegisterDialog
        open
        onOpenChange={() => {}}
        onRegistered={() => {}}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "workflows.registerDialog.sourceTypes.local" }))
    fireEvent.click(screen.getByRole("button", { name: "workflows.registerDialog.localModes.singleFile" }))
    fireEvent.change(screen.getByLabelText("workflows.registerDialog.fields.workflowFile"), {
      target: {
        files: [
          new File(
            ["version 1.0\nworkflow Deaf_20 {}\n"],
            "Deaf_20.wdl",
            { type: "text/plain" }
          ),
        ],
      },
    })

    fireEvent.click(screen.getByRole("button", { name: "workflows.register" }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("workflows.errors.registerLocalFailed")
    })
  })
})

import { act, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import ImagesPage from "@/app/(app)/images/page"
import { ApiError, apiRequest } from "@/lib/api"
import { renderAppPage } from "@/tests/app-test-utils"

const {
  toastErrorMock,
  toastInfoMock,
  toastSuccessMock,
  toastWarningMock,
  clipboardWriteTextMock,
} = vi.hoisted(() => ({
  toastErrorMock: vi.fn(),
  toastInfoMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastWarningMock: vi.fn(),
  clipboardWriteTextMock: vi.fn(),
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
    info: toastInfoMock,
    success: toastSuccessMock,
    warning: toastWarningMock,
  },
}))

vi.mock("@/hooks/use-events", () => ({
  useEvents: vi.fn(() => ({ connectionState: "connected" })),
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuItem: ({ children, onClick, className, ...props }: React.ComponentProps<"button">) => (
    <button className={className} onClick={onClick} {...props}>
      {children}
    </button>
  ),
}))

vi.mock("@/components/ui/sheet", () => ({
  Sheet: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock("@/app/(app)/images/components/images-skeleton", () => ({
  ImagesGridSkeleton: () => <div data-testid="images-grid-skeleton" />,
  ImagesTableSkeleton: () => <div data-testid="images-table-skeleton" />,
}))

vi.mock("@/app/(app)/images/components/image-upload-dialog", () => ({
  ImageUploadDialog: ({
    open,
    importMethod,
    imageName,
    onOpenChange,
    onImportMethodChange,
    onImageNameChange,
    onTarballFileChange,
    onPull,
  }: {
    open: boolean
    importMethod: "registry" | "tarball"
    imageName: string
    onOpenChange: (open: boolean) => void
    onImportMethodChange: (value: "registry" | "tarball") => void
    onImageNameChange: (value: string) => void
    onTarballFileChange: (event: { target: { files: File[] } }) => void
    onPull: () => void
  }) =>
    open ? (
      <div data-testid="image-upload-dialog">
        <div>method:{importMethod}</div>
        <input
          aria-label="image-name"
          value={imageName}
          onChange={(event) => onImageNameChange(event.target.value)}
        />
        <button onClick={() => onImportMethodChange("registry")}>set registry</button>
        <button onClick={() => onImportMethodChange("tarball")}>set tarball</button>
        <button
          onClick={() =>
            onTarballFileChange({
              target: {
                files: [new File(["tar"], "image.tar", { type: "application/x-tar" })],
              },
            })
          }
        >
          attach tarball
        </button>
        <button onClick={onPull}>submit upload</button>
        <button onClick={() => onOpenChange(false)}>close upload</button>
      </div>
    ) : null,
}))

describe("ImagesPage", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  const makeImage = (overrides: Record<string, unknown> = {}) => ({
    id: String(overrides.id ?? "img-1"),
    name: String(overrides.name ?? "ghcr.io/demo/tool"),
    tag: String(overrides.tag ?? "1.0.0"),
    full_name: String(overrides.full_name ?? "ghcr.io/demo/tool:1.0.0"),
    description: String(overrides.description ?? "demo image"),
    size_bytes: overrides.size_bytes === undefined ? 1024 : overrides.size_bytes,
    status: String(overrides.status ?? "remote"),
    registry: String(overrides.registry ?? "ghcr.io"),
    pull_progress: overrides.pull_progress ?? null,
    error_message: overrides.error_message ?? null,
    labels: overrides.labels ?? { maintainer: "Bioinfoflow" },
    env: overrides.env ?? ["PATH=/usr/bin"],
    entrypoint: overrides.entrypoint ?? ["/bin/sh"],
    created_at: String(overrides.created_at ?? "2026-04-08T08:00:00.000Z"),
    updated_at: String(overrides.updated_at ?? "2026-04-08T08:05:00.000Z"),
  })

  const statusMeta = (overrides: Record<string, unknown> = {}) => ({
    docker: "available",
    images_stale: false,
    last_synced_at: "2026-04-08T08:05:00+00:00",
    ...overrides,
  })

  beforeEach(() => {
    apiRequestMock.mockReset()
    toastErrorMock.mockReset()
    toastInfoMock.mockReset()
    toastSuccessMock.mockReset()
    toastWarningMock.mockReset()
    clipboardWriteTextMock.mockReset()
    vi.useRealTimers()
    Object.assign(navigator, {
      clipboard: {
        writeText: clipboardWriteTextMock,
      },
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("renders onboarding empty state with pull, tarball, and recommended CTAs when docker is available and there are no images", async () => {
    apiRequestMock.mockResolvedValue({
      data: [],
      meta: { status: statusMeta() },
    })

    renderAppPage(<ImagesPage />)

    expect(await screen.findByText("images.empty.availableTitle")).toBeInTheDocument()
    expect(screen.getByText("images.empty.actions.pull")).toBeInTheDocument()
    expect(screen.getByText("images.empty.actions.tarball")).toBeInTheDocument()
    expect(screen.getByText("images.empty.actions.recommended")).toBeInTheDocument()
    expect(screen.queryByText("images.usedByProject")).not.toBeInTheDocument()
  })

  it("renders blocking empty state and a refresh action when docker is unavailable with no images", async () => {
    apiRequestMock
      .mockResolvedValueOnce({
        data: [],
        meta: { status: statusMeta({ docker: "unavailable", last_synced_at: null }) },
      })
      .mockResolvedValueOnce({
        data: [],
        meta: { status: statusMeta({ docker: "available" }) },
      })

    renderAppPage(<ImagesPage />)

    expect(await screen.findByText("images.empty.unavailableTitle")).toBeInTheDocument()
    expect(screen.queryByText("images.empty.availableTitle")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "images.actions.refresh" }))

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenLastCalledWith("/images", {
        params: { limit: 100, force_sync: true },
      })
    })
  })

  it("shows stale images with refresh and disabled import controls when docker is unavailable but cached images exist", async () => {
    apiRequestMock.mockResolvedValue({
      data: [makeImage({ status: "local" })],
      meta: { status: statusMeta({ docker: "unavailable", images_stale: true }) },
    })

    renderAppPage(<ImagesPage />)

    expect(await screen.findByText("images.errors.dockerUnavailableBanner")).toBeInTheDocument()
    expect(screen.getByText("ghcr.io/demo/tool")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "images.actions.refresh" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "images.upload" })).toBeDisabled()
  })

  it("opens the details sheet with copy and pull actions instead of a toast", async () => {
    const failedImage = makeImage({
      name: "demo/tool",
      full_name: "ghcr.io/demo/tool:1.0.0",
      status: "failed",
      error_message: "pull exploded",
    })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/images") {
        return {
          data: [failedImage],
          meta: { status: statusMeta() },
        }
      }
      if (path === "/images/pull" && options?.method === "POST") {
        return { data: { ...failedImage, status: "pulling" }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<ImagesPage />)

    expect(await screen.findByText("demo/tool")).toBeInTheDocument()
    fireEvent.click(screen.getByTestId("image-card-view-details"))

    expect(screen.getByText("images.details.title")).toBeInTheDocument()
    expect(screen.getAllByText("ghcr.io/demo/tool:1.0.0").length).toBeGreaterThan(0)
    expect(screen.getByText("docker pull ghcr.io/demo/tool:1.0.0")).toBeInTheDocument()
    expect(screen.getAllByText("pull exploded")).toHaveLength(2)
    expect(toastInfoMock).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId("image-details-copy-name"))
    expect(clipboardWriteTextMock).toHaveBeenCalledWith("ghcr.io/demo/tool:1.0.0")

    fireEvent.click(screen.getByTestId("image-details-copy-pull-command"))
    expect(clipboardWriteTextMock).toHaveBeenCalledWith("docker pull ghcr.io/demo/tool:1.0.0")

    fireEvent.click(screen.getByTestId("image-details-pull"))
    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith("/images/pull", {
        method: "POST",
        body: JSON.stringify({
          name: "demo/tool",
          tag: "1.0.0",
          project_id: undefined,
        }),
      })
    })
  })

  it("fills the upload dialog from the recommended images panel", async () => {
    apiRequestMock.mockResolvedValue({
      data: [],
      meta: { status: statusMeta() },
    })

    renderAppPage(<ImagesPage />)

    expect(await screen.findByText("images.empty.availableTitle")).toBeInTheDocument()
    fireEvent.click(screen.getByText("images.empty.actions.recommended"))
    fireEvent.click(screen.getByRole("button", { name: "biocontainers/fastqc" }))

    expect(await screen.findByTestId("image-upload-dialog")).toBeInTheDocument()
    expect(screen.getByText("method:registry")).toBeInTheDocument()
    expect(screen.getByLabelText("image-name")).toHaveValue("biocontainers/fastqc")
  })

  it("supports registry inputs with ports when pulling from the dialog", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/images") {
        return {
          data: [],
          meta: { status: statusMeta() },
        }
      }
      if (path === "/images/pull" && options?.method === "POST") {
        return { data: makeImage({ status: "pulling" }), meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<ImagesPage />)

    expect(await screen.findByText("images.empty.availableTitle")).toBeInTheDocument()
    fireEvent.click(screen.getByText("images.empty.actions.pull"))
    fireEvent.change(screen.getByLabelText("image-name"), {
      target: { value: "localhost:5000/demo/tool:2.0.0" },
    })
    fireEvent.click(screen.getByText("submit upload"))

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith("/images/pull", {
        method: "POST",
        body: JSON.stringify({
          name: "localhost:5000/demo/tool",
          tag: "2.0.0",
          project_id: undefined,
        }),
      })
    })
  })

  it("shows targeted delete conflict messages for images in use", async () => {
    const deleteActions: Array<() => Promise<void>> = []

    toastWarningMock.mockImplementation((_message, options) => {
      if (options?.action?.onClick) {
        deleteActions.push(options.action.onClick)
      }
    })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/images") {
        return {
          data: [makeImage({ status: "local" })],
          meta: { status: statusMeta() },
        }
      }
      if (path === "/images/img-1" && options?.method === "DELETE") {
        throw new ApiError("image in use", { code: "IMAGE_IN_USE", status: 409 })
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<ImagesPage />)

    expect(await screen.findByText("ghcr.io/demo/tool")).toBeInTheDocument()
    fireEvent.click(screen.getByText("images.actions.deleteLocal"))

    await deleteActions[0]()

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("image in use")
    })
  })

  it("batch deletes selected local images from browsing cards", async () => {
    const batchDeleteActions: Array<() => Promise<void>> = []
    const localImage = makeImage({
      id: "img-local",
      name: "demo/local",
      full_name: "ghcr.io/demo/local:1.0.0",
      status: "local",
      size_bytes: 2048,
    })
    const remoteImage = makeImage({
      id: "img-remote",
      name: "demo/remote",
      full_name: "ghcr.io/demo/remote:1.0.0",
      status: "remote",
    })

    toastWarningMock.mockImplementation((_message, options) => {
      if (options?.action?.onClick) {
        batchDeleteActions.push(options.action.onClick)
      }
    })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/images") {
        return {
          data: [localImage, remoteImage],
          meta: { status: statusMeta() },
        }
      }
      if (path === "/images/img-local" && options?.method === "DELETE") {
        return { data: null, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<ImagesPage />)

    expect(await screen.findByText("demo/local")).toBeInTheDocument()
    expect(screen.queryByLabelText("images.selection.selectImage:demo/local:1.0.0")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "images.actions.select" }))
    fireEvent.click(screen.getByLabelText("images.selection.selectImage:demo/local:1.0.0"))

    expect(screen.queryByLabelText("images.selection.selectImage:demo/remote:1.0.0")).not.toBeInTheDocument()
    expect(screen.getByText("images.selection.selectedCount:1")).toBeInTheDocument()
    expect(screen.getByText(/images\.selection\.selectedSize:2/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "images.actions.deleteSelectedLocal" }))
    await act(async () => {
      await batchDeleteActions[0]()
    })

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith("/images/img-local", { method: "DELETE" })
      expect(screen.queryByText("demo/local")).not.toBeInTheDocument()
    })
    expect(screen.getByText("demo/remote")).toBeInTheDocument()
  })

  it("does not batch delete a selected image after search hides it", async () => {
    const localImage = makeImage({
      id: "img-local",
      name: "demo/local",
      full_name: "ghcr.io/demo/local:1.0.0",
      status: "local",
      size_bytes: null,
    })
    const remoteImage = makeImage({
      id: "img-remote",
      name: "demo/remote",
      full_name: "ghcr.io/demo/remote:1.0.0",
      status: "remote",
    })

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/images") {
        return {
          data: [localImage, remoteImage],
          meta: { status: statusMeta() },
        }
      }
      if (path === "/images/img-local" && options?.method === "DELETE") {
        throw new Error("Hidden image should not be deleted")
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<ImagesPage />)

    expect(await screen.findByText("demo/local")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "images.actions.select" }))
    fireEvent.click(screen.getByLabelText("images.selection.selectImage:demo/local:1.0.0"))
    expect(screen.getByText("images.selection.selectedCount:1")).toBeInTheDocument()
    expect(screen.getByText(/images\.selection\.selectedSize:0/)).toBeInTheDocument()

    fireEvent.change(screen.getByRole("textbox", { name: "common.search images.title" }), {
      target: { value: "remote" },
    })

    expect(screen.queryByText("demo/local")).not.toBeInTheDocument()
    expect(screen.getByText("images.selection.selectedCount:0")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "images.actions.deleteSelectedLocal" })).toBeDisabled()
  })

  it("closes image details after deleting the local image from the sheet", async () => {
    const deleteActions: Array<() => Promise<void>> = []
    const localImage = makeImage({
      id: "img-local",
      name: "demo/local",
      full_name: "ghcr.io/demo/local:1.0.0",
      status: "local",
    })

    toastWarningMock.mockImplementation((_message, options) => {
      if (options?.action?.onClick) {
        deleteActions.push(options.action.onClick)
      }
    })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/images") {
        return {
          data: [localImage],
          meta: { status: statusMeta() },
        }
      }
      if (path === "/images/img-local" && options?.method === "DELETE") {
        return { data: null, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<ImagesPage />)

    expect(await screen.findByText("demo/local")).toBeInTheDocument()
    fireEvent.click(screen.getByTestId("image-card-view-details"))
    expect(screen.getAllByText("ghcr.io/demo/local:1.0.0").length).toBeGreaterThan(0)

    fireEvent.click(screen.getAllByRole("button", { name: "images.actions.deleteLocal" })[0])
    await act(async () => {
      await deleteActions[0]()
    })

    await waitFor(() => {
      expect(screen.queryByText("ghcr.io/demo/local:1.0.0")).not.toBeInTheDocument()
    })
  })

  it("closes image details after batch deleting the open local image", async () => {
    const batchDeleteActions: Array<() => Promise<void>> = []
    const localImage = makeImage({
      id: "img-local",
      name: "demo/local",
      full_name: "ghcr.io/demo/local:1.0.0",
      status: "local",
    })

    toastWarningMock.mockImplementation((_message, options) => {
      if (options?.action?.onClick) {
        batchDeleteActions.push(options.action.onClick)
      }
    })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/images") {
        return {
          data: [localImage],
          meta: { status: statusMeta() },
        }
      }
      if (path === "/images/img-local" && options?.method === "DELETE") {
        return { data: null, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<ImagesPage />)

    expect(await screen.findByText("demo/local")).toBeInTheDocument()
    fireEvent.click(screen.getByTestId("image-card-view-details"))
    expect(screen.getAllByText("ghcr.io/demo/local:1.0.0").length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole("button", { name: "images.actions.select" }))
    fireEvent.click(screen.getByLabelText("images.selection.selectImage:demo/local:1.0.0"))
    fireEvent.click(screen.getByRole("button", { name: "images.actions.deleteSelectedLocal" }))
    await act(async () => {
      await batchDeleteActions[0]()
    })

    await waitFor(() => {
      expect(screen.queryByText("ghcr.io/demo/local:1.0.0")).not.toBeInTheDocument()
    })
  })

  it("auto-retries when docker is unavailable and the list is empty", async () => {
    vi.useFakeTimers()
    apiRequestMock.mockResolvedValue({
      data: [],
      meta: { status: statusMeta({ docker: "unavailable", last_synced_at: null }) },
    })

    renderAppPage(<ImagesPage />)

    await Promise.resolve()
    await Promise.resolve()
    expect(apiRequestMock).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(15000)

    expect(apiRequestMock).toHaveBeenCalledTimes(2)
    expect(apiRequestMock).toHaveBeenLastCalledWith("/images", {
      params: { limit: 100, force_sync: true },
    })
  })
})

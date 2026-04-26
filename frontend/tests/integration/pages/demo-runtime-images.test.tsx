import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import ImagesPage from "@/app/(app)/images/page"
import { createDemoRuntime, setActiveRuntimeForTests } from "@/lib/runtime"
import { renderAppPage } from "@/tests/app-test-utils"

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
        },
      )
    }

    return translationMocks.get(namespace)!
  },
}))

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuItem: ({
    children,
    onClick,
    className,
  }: {
    children: React.ReactNode
    onClick?: () => void
    className?: string
  }) => (
    <button className={className} onClick={onClick}>
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

vi.mock("@/app/(app)/images/components/image-upload-dialog", () => ({
  ImageUploadDialog: ({
    open,
    imageName,
    onImageNameChange,
    onOpenChange,
    onPull,
  }: {
    open: boolean
    imageName: string
    onImageNameChange: (value: string) => void
    onOpenChange: (open: boolean) => void
    onPull: () => void
  }) =>
    open ? (
      <div data-testid="image-upload-dialog">
        <input
          aria-label="image-name"
          value={imageName}
          onChange={(event) => onImageNameChange(event.target.value)}
        />
        <button onClick={onPull}>submit upload</button>
        <button onClick={() => onOpenChange(false)}>close upload</button>
      </div>
    ) : null,
}))

describe("ImagesPage under demo runtime", () => {
  beforeEach(() => {
    vi.stubEnv("APP_RUNTIME", "demo")
    vi.stubEnv("DEPLOY_MODE", "demo")
    setActiveRuntimeForTests(createDemoRuntime())
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    setActiveRuntimeForTests(null)
  })

  it("renders seeded demo images and can add a new mocked image", async () => {
    renderAppPage(<ImagesPage />)

    expect(
      await screen.findByText("ghcr.io/demo/rnaseq-toolkit"),
    ).toBeInTheDocument()
    expect(screen.getByText("biocontainers/fastqc")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "images.upload" }))
    fireEvent.change(screen.getByLabelText("image-name"), {
      target: { value: "ghcr.io/demo/custom-qc:2.0.0" },
    })
    fireEvent.click(screen.getByRole("button", { name: "submit upload" }))

    await waitFor(() => {
      expect(screen.getByText("ghcr.io/demo/custom-qc")).toBeInTheDocument()
    })
  })
})

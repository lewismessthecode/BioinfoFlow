import { fireEvent, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ImageUploadDialog } from "@/app/(app)/images/components/image-upload-dialog"
import { renderAppPage } from "@/tests/app-test-utils"

const translationMocks = new Map<
  string,
  (key: string, values?: Record<string, unknown>) => string
>()

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => {
    if (!translationMocks.has(namespace)) {
      translationMocks.set(namespace, (key: string, values?: Record<string, unknown>) => {
        const suffix = values
          ? Object.values(values)
              .filter((value) => value !== undefined && value !== null)
              .join(":")
          : ""
        return suffix ? `${namespace}.${key}:${suffix}` : `${namespace}.${key}`
      })
    }
    return translationMocks.get(namespace)!
  },
}))

describe("ImageUploadDialog", () => {
  const baseProps = {
    open: true,
    onOpenChange: vi.fn(),
    importMethod: "registry" as const,
    onImportMethodChange: vi.fn(),
    imageName: "",
    onImageNameChange: vi.fn(),
    tarballFile: null,
    onTarballFileChange: vi.fn(),
    isSubmitting: false,
    onPull: vi.fn(),
  }

  it("shows a minimal optional registry selector when registries are configured", () => {
    const onSelectedRegistryChange = vi.fn()

    renderAppPage(
      <ImageUploadDialog
        {...baseProps}
        registries={[
          {
            id: "registry-harbor",
            name: "Lab Harbor",
            endpoint: "harbor.local:5000",
            provider: "harbor",
          },
        ]}
        selectedRegistry=""
        onSelectedRegistryChange={onSelectedRegistryChange}
      />,
    )

    const select = screen.getByLabelText("images.uploadDialog.registry")
    expect(select).toHaveValue("")
    expect(screen.getByText("images.uploadDialog.registryAutomatic")).toBeInTheDocument()
    expect(screen.getByText("Lab Harbor (harbor.local:5000)")).toBeInTheDocument()

    fireEvent.change(select, { target: { value: "registry-harbor" } })

    expect(onSelectedRegistryChange).toHaveBeenCalledWith("registry-harbor")
  })

  it("keeps the upload card uncluttered when no registries are configured", () => {
    renderAppPage(
      <ImageUploadDialog
        {...baseProps}
        registries={[]}
        selectedRegistry=""
        onSelectedRegistryChange={vi.fn()}
      />,
    )

    expect(screen.queryByLabelText("images.uploadDialog.registry")).not.toBeInTheDocument()
  })
})

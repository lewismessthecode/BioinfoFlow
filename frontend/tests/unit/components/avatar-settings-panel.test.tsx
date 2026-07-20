import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AvatarSettingsPanel } from "@/components/bioinfoflow/settings/avatar-settings-panel"
import { DEV_AVATAR_STORAGE_KEY } from "@/lib/avatar/avatar-preference"
import { parsePixelPersonaReference } from "@/lib/avatar/pixel-personas"

const refreshMock = vi.fn()
const successToastMock = vi.fn()
const errorToastMock = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock }),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (
    key: string,
    values?: Record<string, string | number>,
  ) => {
    const copy: Record<string, string> = {
      "account.avatar.title": "Profile image",
      "account.avatar.description": "Choose a Bioinfoflow pixel identity or upload your own image.",
      "account.avatar.showAnotherSet": "Show another set",
      "account.avatar.upload": "Upload image",
      "account.avatar.restoreDefault": "Restore default",
      "account.avatar.saving": "Saving avatar...",
      "account.avatar.saved": "Avatar updated.",
      "account.avatar.reset": "Default avatar restored.",
      "account.avatar.saveFailed": "Couldn't update your avatar.",
      "account.avatar.unsupportedType": "Choose a PNG, JPEG, or WebP image.",
      "account.avatar.tooLarge": "Choose an image smaller than 5 MB.",
    }
    if (key === "account.avatar.optionLabel") {
      return `Pixel avatar ${values?.number}`
    }
    return copy[key] ?? key
  },
}))

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => successToastMock(...args),
    error: (...args: unknown[]) => errorToastMock(...args),
  },
}))

function viewer(overrides: Partial<React.ComponentProps<typeof AvatarSettingsPanel>["viewer"]> = {}) {
  return {
    id: "viewer-1",
    name: "Alice Example",
    image: null,
    authEnabled: true,
    ...overrides,
  }
}

describe("AvatarSettingsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, data: { image: null } }),
      }),
    )
  })

  it("shows six candidates and pages without changing the active avatar", () => {
    render(<AvatarSettingsPanel viewer={viewer()} />)

    const firstBatch = screen.getAllByRole("radio", { name: /Pixel avatar/ })
    expect(firstBatch).toHaveLength(6)
    const firstKey = firstBatch[0].getAttribute("data-avatar-key")

    fireEvent.click(screen.getByRole("button", { name: "Show another set" }))

    const secondBatch = screen.getAllByRole("radio", { name: /Pixel avatar/ })
    expect(secondBatch).toHaveLength(6)
    expect(secondBatch[0]).not.toHaveAttribute("data-avatar-key", firstKey)
    expect(fetch).not.toHaveBeenCalled()
  })

  it("saves an authenticated built-in avatar selection", async () => {
    render(<AvatarSettingsPanel viewer={viewer()} />)

    const option = screen.getAllByRole("radio", { name: /Pixel avatar/ })[0]
    const key = option.getAttribute("data-avatar-key")
    fireEvent.click(option)

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/profile/avatar",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ avatarKey: key }),
        }),
      )
    })
    expect(successToastMock).toHaveBeenCalledWith("Avatar updated.")
    expect(refreshMock).toHaveBeenCalled()
  })

  it("persists a development-mode selection in browser storage", () => {
    render(<AvatarSettingsPanel viewer={viewer({ id: "dev", authEnabled: false })} />)

    const option = screen.getAllByRole("radio", { name: /Pixel avatar/ })[0]
    fireEvent.click(option)

    expect(
      parsePixelPersonaReference(
        window.localStorage.getItem(DEV_AVATAR_STORAGE_KEY),
      ),
    ).toBe(option.getAttribute("data-avatar-key"))
    expect(fetch).not.toHaveBeenCalled()
  })

  it("restores the deterministic default through the profile route", async () => {
    render(
      <AvatarSettingsPanel
        viewer={viewer({ image: "bioinfoflow-avatar:pixel-persona-03" })}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Restore default" }))

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/profile/avatar",
        expect.objectContaining({ method: "DELETE" }),
      )
    })
    expect(successToastMock).toHaveBeenCalledWith("Default avatar restored.")
  })

  it("rejects unsupported upload files before opening the crop dialog", () => {
    render(<AvatarSettingsPanel viewer={viewer()} />)

    const input = screen.getByLabelText("Upload image")
    fireEvent.change(input, {
      target: {
        files: [new File(["gif"], "avatar.gif", { type: "image/gif" })],
      },
    })

    expect(errorToastMock).toHaveBeenCalledWith(
      "Choose a PNG, JPEG, or WebP image.",
    )
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})

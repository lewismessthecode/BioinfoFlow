import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it } from "vitest"
import { UserAvatar } from "@/components/bioinfoflow/user-avatar"
import {
  clearDevAvatarPreference,
  writeDevAvatarPreference,
} from "@/lib/avatar/avatar-preference"
import {
  resolveDefaultPixelPersona,
  toPixelPersonaReference,
} from "@/lib/avatar/pixel-personas"

describe("UserAvatar", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it("renders an explicitly selected built-in pixel persona", () => {
    render(
      <UserAvatar
        viewerId="viewer-1"
        name="Alice"
        image={toPixelPersonaReference("pixel-persona-03")}
      />,
    )

    expect(screen.getByTestId("pixel-persona-03")).toBeInTheDocument()
  })

  it("renders an ordinary profile image URL", () => {
    render(
      <UserAvatar
        viewerId="viewer-1"
        name="Alice"
        image="/api/profile/avatar/file?v=1"
        alt="Alice avatar"
      />,
    )

    expect(screen.getByRole("img", { name: "Alice avatar" })).toHaveAttribute(
      "src",
      "/api/profile/avatar/file?v=1",
    )
  })

  it("recovers from a failed image when the profile URL changes", () => {
    const { rerender } = render(
      <UserAvatar
        viewerId="viewer-1"
        name="Alice"
        image="/api/profile/avatar/file?v=1"
        alt="Alice avatar"
      />,
    )

    fireEvent.error(screen.getByRole("img", { name: "Alice avatar" }))
    expect(
      screen.getByTestId(resolveDefaultPixelPersona("viewer-1").key),
    ).toBeInTheDocument()

    rerender(
      <UserAvatar
        viewerId="viewer-1"
        name="Alice"
        image="/api/profile/avatar/file?v=2"
        alt="Alice avatar"
      />,
    )

    expect(screen.getByRole("img", { name: "Alice avatar" })).toHaveAttribute(
      "src",
      "/api/profile/avatar/file?v=2",
    )
  })

  it("uses a deterministic persona when no explicit image exists", () => {
    render(<UserAvatar viewerId="viewer-1" name="Alice" />)

    expect(
      screen.getByTestId(resolveDefaultPixelPersona("viewer-1").key),
    ).toBeInTheDocument()
  })

  it("reacts to development-mode avatar preference changes", () => {
    render(
      <UserAvatar
        viewerId="dev"
        name="Local User"
        authEnabled={false}
      />,
    )

    act(() => {
      writeDevAvatarPreference(toPixelPersonaReference("pixel-persona-17"))
    })
    expect(screen.getByTestId("pixel-persona-17")).toBeInTheDocument()

    act(() => {
      clearDevAvatarPreference()
    })
    expect(
      screen.getByTestId(resolveDefaultPixelPersona("dev").key),
    ).toBeInTheDocument()
  })
})

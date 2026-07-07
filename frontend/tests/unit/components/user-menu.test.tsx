import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { ViewerIdentity } from "@/lib/auth-config"

const signOutMock = vi.fn()
const replaceMock = vi.fn()
const refreshMock = vi.fn()
const successToastMock = vi.fn()
const errorToastMock = vi.fn()
const setModeMock = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: replaceMock,
    refresh: refreshMock,
    push: vi.fn(),
  }),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const copy: Record<string, string> = {
      signOut: "Sign out",
      defaultName: "User",
      "toasts.loggedOut": "Logged out",
      "toasts.logoutFailed": "Logout failed",
      userMenu: "User menu",
      lightMode: "Light mode",
      darkMode: "Dark mode",
      settings: "settings",
      "roles.owner": "roles.owner",
    }
    return copy[key] ?? key
  },
}))

vi.mock("@/lib/appearance/use-appearance", () => ({
  getNextAppearanceMode: () => "dark",
  useAppearance: () => ({
    mode: "light",
    resolvedMode: "light",
    lightPreset: "workbench",
    darkPreset: "workbench",
    activePreset: "workbench",
    setMode: setModeMock,
    setLightPreset: vi.fn(),
    setDarkPreset: vi.fn(),
  }),
}))

vi.mock("@/lib/auth-client", () => ({
  authClient: {
    signOut: (...args: unknown[]) => signOutMock(...args),
  },
}))

vi.mock("@/lib/auth-config", () => ({
  buildAnonymousViewer: () => ({
    id: "dev",
    name: "Local User",
    email: "local@bioinfoflow",
    role: "owner",
    mode: "dev",
    canManageMembers: false,
    disabled: false,
    authEnabled: false,
    workspaceName: "Bioinfoflow Team",
  }),
}))

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => successToastMock(...args),
    error: (...args: unknown[]) => errorToastMock(...args),
  },
}))

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({
    children,
    onClick,
  }: {
    children: React.ReactNode
    onClick?: () => void
  }) => <button onClick={onClick}>{children}</button>,
  DropdownMenuSeparator: () => <hr />,
}))

import { UserMenu } from "@/components/bioinfoflow/user-menu"

const ALICE_VIEWER: ViewerIdentity = {
  id: "u1",
  name: "Alice Example",
  email: "alice@example.com",
  image: null,
  role: "owner",
  mode: "personal",
  canManageMembers: false,
  disabled: false,
  authEnabled: true,
  workspaceName: "Bioinfoflow Team",
}

describe("UserMenu", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("routes the theme toggle through the appearance hook", async () => {
    const user = userEvent.setup()

    render(<UserMenu collapsed={false} viewer={ALICE_VIEWER} />)

    await user.click(screen.getByRole("button", { name: "Dark mode" }))

    expect(setModeMock).toHaveBeenCalledWith("dark")
  })

  it("redirects to /auth and refreshes after a successful sign out", async () => {
    const user = userEvent.setup()
    signOutMock.mockImplementation(async (options?: { fetchOptions?: { onSuccess?: () => void } }) => {
      options?.fetchOptions?.onSuccess?.()
    })

    render(<UserMenu collapsed={false} viewer={ALICE_VIEWER} />)

    await user.click(screen.getByRole("button", { name: "Sign out" }))

    expect(signOutMock).toHaveBeenCalled()
    expect(successToastMock).toHaveBeenCalledWith("Logged out")
    expect(replaceMock).toHaveBeenCalledWith("/auth")
    expect(refreshMock).toHaveBeenCalled()
  })

  it("centers the avatar trigger when collapsed", () => {
    render(<UserMenu collapsed viewer={ALICE_VIEWER} />)

    const trigger = screen.getByRole("button", { name: "Alice Example — User menu" })
    expect(trigger.className).toContain("justify-center")
  })

  it("avoids a hard white collapsed trigger shell", () => {
    render(<UserMenu collapsed viewer={ALICE_VIEWER} />)

    const trigger = screen.getByRole("button", { name: "Alice Example — User menu" })
    expect(trigger.className).not.toContain("bg-white/92")
    expect(trigger.className).toContain("bg-card/90")
  })

  it("does not render the email in the sidebar trigger", () => {
    render(<UserMenu collapsed={false} viewer={ALICE_VIEWER} />)

    const trigger = screen.getByRole("button", { name: "Alice Example — User menu" })
    expect(trigger).not.toHaveTextContent("alice@example.com")
  })
})

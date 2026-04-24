import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { ViewerIdentity } from "@/lib/auth-config"

const {
  pushMock,
  replaceMock,
  refreshMock,
  setModeMock,
  signOutMock,
  openInNewTabMock,
  toastInfoMock,
  toastSuccessMock,
  toastErrorMock,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
  refreshMock: vi.fn(),
  setModeMock: vi.fn(),
  signOutMock: vi.fn(),
  openInNewTabMock: vi.fn(),
  toastInfoMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastErrorMock: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
    refresh: refreshMock,
  }),
}))

vi.mock("@/lib/appearance/use-appearance", () => ({
  getNextAppearanceMode: () => "dark",
  useAppearance: () => ({
    mode: "light",
    resolvedMode: "light",
    lightPreset: "codex",
    darkPreset: "codex",
    activePreset: "codex",
    setMode: setModeMock,
    setLightPreset: vi.fn(),
    setDarkPreset: vi.fn(),
  }),
}))

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => {
    const copy: Record<string, Record<string, string>> = {
      userMenu: {
        "toasts.signingOut": "Signing out",
        "toasts.loggedOut": "Logged out",
        "toasts.logoutFailed": "Logout failed",
        "toasts.openingDocs": "Opening docs",
        "toasts.keyboardShortcutsHint": "Keyboard shortcuts",
        keyboardShortcuts: "Keyboard Shortcuts",
        helpDocs: "Help Docs",
        signOut: "Sign Out",
        "roles.owner": "Owner",
      },
      accessibility: {
        openSidebar: "Open sidebar",
        toggleTheme: "Toggle theme",
        openMenu: "Open menu",
        hidePanel: "Hide panel",
      },
    }
    return copy[namespace]?.[key] ?? key
  },
}))

vi.mock("@/lib/auth-client", () => ({
  authClient: {
    signOut: (...args: unknown[]) => signOutMock(...args),
  },
}))

vi.mock("@/lib/window-utils", () => ({
  openInNewTab: (...args: unknown[]) => openInNewTabMock(...args),
}))

vi.mock("sonner", () => ({
  toast: {
    info: (...args: unknown[]) => toastInfoMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}))

vi.mock("@/components/bioinfoflow/breadcrumbs", () => ({
  Breadcrumbs: ({ projectName, conversationTitle }: { projectName?: string; conversationTitle?: string }) => (
    <div>{projectName}:{conversationTitle}</div>
  ),
}))

vi.mock("@/components/bioinfoflow/connection-status", () => ({
  ConnectionStatus: ({ state }: { state: string }) => <div>{state}</div>,
}))

vi.mock("@/components/language-switcher", () => ({
  LanguageSwitcher: () => <div data-testid="language-switcher" />,
}))

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuItem: ({
    children,
    onClick,
  }: {
    children: React.ReactNode
    onClick?: () => void
  }) => <button onClick={onClick}>{children}</button>,
}))

import { Navbar } from "@/components/bioinfoflow/navbar"

const AUTH_VIEWER: ViewerIdentity = {
  id: "viewer-1",
  name: "Alice Example",
  email: "alice@example.com",
  image: null,
  role: "owner",
  mode: "team",
  canManageMembers: true,
  disabled: false,
  authEnabled: true,
  workspaceName: "Bioinfoflow Team",
}

describe("Navbar", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("opens the docs link from the help action", async () => {
    const user = userEvent.setup()
    render(<Navbar viewer={AUTH_VIEWER} />)

    await user.click(screen.getByRole("button", { name: "Help Docs" }))

    expect(toastInfoMock).toHaveBeenCalledWith("Opening docs")
    expect(openInNewTabMock).toHaveBeenCalledWith("https://docs.bioinfoflow.io")
  })

  it("toggles the theme from light to dark", async () => {
    const user = userEvent.setup()
    render(<Navbar viewer={AUTH_VIEWER} />)

    await user.click(screen.getByRole("button", { name: "Toggle theme" }))

    expect(setModeMock).toHaveBeenCalledWith("dark")
  })

  it("signs out authenticated viewers and redirects to /auth on success", async () => {
    const user = userEvent.setup()
    signOutMock.mockImplementation(async (options?: { fetchOptions?: { onSuccess?: () => void } }) => {
      options?.fetchOptions?.onSuccess?.()
    })
    render(<Navbar viewer={AUTH_VIEWER} />)

    await user.click(screen.getByRole("button", { name: "Sign Out" }))

    expect(signOutMock).toHaveBeenCalled()
    expect(toastSuccessMock).toHaveBeenCalledWith("Logged out")
    expect(replaceMock).toHaveBeenCalledWith("/auth")
    expect(refreshMock).toHaveBeenCalled()
  })

  it("calls the sidebar toggle when the hamburger button is shown", async () => {
    const user = userEvent.setup()
    const onSidebarToggle = vi.fn()
    render(<Navbar viewer={AUTH_VIEWER} showHamburger onSidebarToggle={onSidebarToggle} />)

    await user.click(screen.getByRole("button", { name: "Open sidebar" }))

    expect(onSidebarToggle).toHaveBeenCalledTimes(1)
  })
})

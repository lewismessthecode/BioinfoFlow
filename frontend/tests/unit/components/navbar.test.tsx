import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
import type { ViewerIdentity } from "@/lib/auth-config"
import { createCelebrationsPreferenceMock } from "@/tests/support/mock-celebrations-preference"

const {
  pushMock,
  replaceMock,
  refreshMock,
  setModeMock,
  celebratePreviewMock,
  setCelebrationsEnabledMock,
  reducedMotionState,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
  refreshMock: vi.fn(),
  setModeMock: vi.fn(),
  celebratePreviewMock: vi.fn(),
  setCelebrationsEnabledMock: vi.fn(),
  reducedMotionState: { value: false },
}))

const celebrationsPreference = createCelebrationsPreferenceMock()

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
  useTranslations: (namespace: string) => (key: string, values?: Record<string, string>) => {
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
        celebrationsOn: "Milestone confetti on",
        celebrationsOff: "Milestone confetti off",
        celebrationsPaused: "Milestone confetti paused by reduced motion",
        celebrationsMenuState: `Quiet celebrations: ${values?.state ?? ""}`,
      },
      celebrations: {
        title: "Quiet celebrations",
        toggle: "Milestone confetti",
        preview: "Preview",
        reducedMotion: "Reduced motion is on, so confetti is paused.",
      },
    }
    return copy[namespace]?.[key] ?? key
  },
}))

vi.mock("@/lib/celebrations", () => ({
  celebratePreview: (...args: unknown[]) => celebratePreviewMock(...args),
  isCelebrationsEnabled: () => celebrationsPreference.getEnabled(),
  useCelebrationsEnabledPreference: () =>
    celebrationsPreference.useCelebrationsEnabledPreference(),
  useReducedMotionPreference: () => reducedMotionState.value,
  setCelebrationsEnabled: (enabled: boolean) => {
    celebrationsPreference.setEnabled(enabled)
    setCelebrationsEnabledMock(enabled)
  },
  subscribeToCelebrationsPreference: (listener: (enabled: boolean) => void) =>
    celebrationsPreference.subscribeToCelebrationsPreference(listener),
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
  DropdownMenuCheckboxItem: ({
    children,
    checked,
    onCheckedChange,
  }: {
    children: React.ReactNode
    checked?: boolean
    onCheckedChange?: (checked: boolean) => void
  }) => (
    <button
      role="menuitemcheckbox"
      aria-checked={checked}
      onClick={() => onCheckedChange?.(!checked)}
    >
      {children}
    </button>
  ),
  DropdownMenuItem: ({
    children,
    disabled,
    onClick,
  }: {
    children: React.ReactNode
    disabled?: boolean
    onClick?: () => void
  }) => <button disabled={disabled} onClick={onClick}>{children}</button>,
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
    celebrationsPreference.reset()
    reducedMotionState.value = false
  })

  it("toggles the theme from light to dark", async () => {
    const user = userEvent.setup()
    render(<Navbar viewer={AUTH_VIEWER} />)

    await user.click(screen.getByRole("button", { name: "Toggle theme" }))

    expect(setModeMock).toHaveBeenCalledWith("dark")
  })

  it("calls the sidebar toggle when the hamburger button is shown", async () => {
    const user = userEvent.setup()
    const onSidebarToggle = vi.fn()
    render(<Navbar viewer={AUTH_VIEWER} showHamburger onSidebarToggle={onSidebarToggle} />)

    await user.click(screen.getByRole("button", { name: "Open sidebar" }))

    expect(onSidebarToggle).toHaveBeenCalledTimes(1)
  })

  it("keeps injected workspace actions at the far right of the top action row", () => {
    render(
      <Navbar viewer={AUTH_VIEWER}>
        <button type="button">Open run panel</button>
      </Navbar>,
    )

    const actionRow = screen.getByTestId("navbar-action-row")
    const buttons = Array.from(actionRow.querySelectorAll("button"))

    expect(buttons.at(-1)).toHaveTextContent("Open run panel")
  })

  it("removes the redundant top-right user menu trigger", () => {
    render(<Navbar viewer={AUTH_VIEWER} />)

    expect(screen.queryByRole("button", { name: "Open menu" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Sign Out" })).not.toBeInTheDocument()
  })

  it("toggles celebrations from the top-right control and updates the trigger state", async () => {
    const user = userEvent.setup()
    render(<Navbar viewer={AUTH_VIEWER} />)

    expect(screen.getByRole("button", { name: "Quiet celebrations: Milestone confetti on" })).toBeInTheDocument()

    await user.click(screen.getByRole("menuitemcheckbox", { name: "Milestone confetti" }))

    expect(setCelebrationsEnabledMock).toHaveBeenCalledWith(false)
    expect(screen.getByRole("button", { name: "Quiet celebrations: Milestone confetti off" })).toBeInTheDocument()
  })

  it("fires preview confetti from the top-right control", async () => {
    const user = userEvent.setup()
    render(<Navbar viewer={AUTH_VIEWER} />)

    await user.click(screen.getByRole("button", { name: "Preview" }))

    expect(celebratePreviewMock).toHaveBeenCalledTimes(1)
  })

  it("pauses navbar preview while reduced motion is active", async () => {
    const user = userEvent.setup()
    reducedMotionState.value = true
    render(<Navbar viewer={AUTH_VIEWER} />)

    expect(
      screen.getByRole("button", { name: "Quiet celebrations: Milestone confetti paused by reduced motion" }),
    ).toBeInTheDocument()
    expect(screen.getByText("Reduced motion is on, so confetti is paused.")).toBeInTheDocument()

    const preview = screen.getByRole("button", { name: "Preview" })
    expect(preview).toBeDisabled()
    await user.click(preview)

    expect(celebratePreviewMock).not.toHaveBeenCalled()
  })
})

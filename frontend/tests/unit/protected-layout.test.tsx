import * as React from "react"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach } from "vitest"

const mockRedirect = vi.fn()
const mockGetSession = vi.fn()
const mockHeaders = vi.fn()
const mockEnsureAuthReady = vi.fn()
const mockGetServerAuthConfig = vi.fn()
const mockGetAuth = vi.fn()
const mockBuildAnonymousViewer = vi.fn(() => ({
  id: "dev",
  name: "Local User",
  email: "local@bioinfoflow",
  role: "owner",
  mode: "dev",
  canManageMembers: false,
  disabled: false,
  authEnabled: false,
  workspaceName: "Bioinfoflow Team",
}))

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    mockRedirect(url)
    throw new Error(`NEXT_REDIRECT: ${url}`)
  },
  usePathname: () => "/dashboard",
}))

vi.mock("next/headers", () => ({
  headers: () => mockHeaders(),
}))

vi.mock("@/lib/auth", () => ({
  ensureAuthReady: () => mockEnsureAuthReady(),
  getAuth: () => mockGetAuth(),
}))

vi.mock("@/lib/auth-config", () => ({
  getServerAuthConfig: () => mockGetServerAuthConfig(),
  buildAnonymousViewer: () => mockBuildAnonymousViewer(),
  buildViewerIdentity: (user: {
    id: string
    name: string
    email: string
    image?: string | null
  }) => ({
    id: user.id,
    name: user.name,
    email: user.email,
    image: user.image,
    role: "member",
    mode: "team",
    canManageMembers: false,
    disabled: false,
    authEnabled: true,
    workspaceName: "Bioinfoflow Team",
  }),
}))

vi.mock("@/app/(app)/app-layout", () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="app-layout">{children}</div>
  ),
}))

import ProtectedLayout from "@/app/(app)/layout"

describe("ProtectedLayout", () => {
  const fakeHeaders = new Headers({ cookie: "better-auth.session_token=abc" })

  beforeEach(() => {
    vi.clearAllMocks()
    mockHeaders.mockResolvedValue(fakeHeaders)
    mockEnsureAuthReady.mockResolvedValue(undefined)
    mockGetAuth.mockResolvedValue({
      api: {
        getSession: (opts: unknown) => mockGetSession(opts),
      },
    })
    mockGetServerAuthConfig.mockReturnValue({
      mode: "team",
      authEnabled: true,
      workspaceName: "Bioinfoflow Team",
    })
  })

  it("skips auth lookup when auth is disabled", async () => {
    mockGetServerAuthConfig.mockReturnValue({
      mode: "dev",
      authEnabled: false,
      workspaceName: "Bioinfoflow Team",
    })

    const Layout = await ProtectedLayout({ children: <div>child content</div> })
    render(Layout as React.ReactElement)

    expect(mockEnsureAuthReady).not.toHaveBeenCalled()
    expect(mockGetSession).not.toHaveBeenCalled()
    expect(screen.getByTestId("app-layout")).toBeInTheDocument()
  })

  it("redirects to /auth when session is null", async () => {
    mockGetSession.mockResolvedValue(null)

    await expect(
      ProtectedLayout({ children: <div>child</div> })
    ).rejects.toThrow("NEXT_REDIRECT: /auth")
    expect(mockRedirect).toHaveBeenCalledWith("/auth")
  })

  it("renders children via AppLayout when session exists", async () => {
    mockGetSession.mockResolvedValue({
      user: { id: "u1", name: "Test", email: "test@example.com" },
      session: { id: "s1", token: "abc" },
    })

    const Layout = await ProtectedLayout({ children: <div>child content</div> })
    render(Layout as React.ReactElement)
    expect(screen.getByTestId("app-layout")).toBeInTheDocument()
    expect(screen.getByText("child content")).toBeInTheDocument()
  })

  it("passes request headers to getSession", async () => {
    mockGetSession.mockResolvedValue({
      user: { id: "u1", name: "Test", email: "test@example.com" },
      session: { id: "s1", token: "abc" },
    })

    await ProtectedLayout({ children: <div>child</div> })
    expect(mockEnsureAuthReady).toHaveBeenCalled()
    expect(mockGetSession).toHaveBeenCalledWith({ headers: fakeHeaders })
  })
})

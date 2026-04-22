import * as React from "react"
import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mockRedirect = vi.fn()
const mockGetSession = vi.fn()
const mockHeaders = vi.fn()
const mockEnsureAuthReady = vi.fn()
const mockGetServerAuthConfig = vi.fn()
const mockGetAuth = vi.fn()

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    mockRedirect(url)
    throw new Error(`NEXT_REDIRECT: ${url}`)
  },
}))

vi.mock("next/headers", () => ({
  headers: () => mockHeaders(),
}))

vi.mock("next-intl/server", () => ({
  getTranslations: async () => (key: string) => {
    const labels: Record<string, string> = {
      title: "Sign in to continue",
      description: "Sign in to your shared workspace.",
      "badges.localReady": "Local accounts enabled",
      "badges.oauthOnly": "OAuth only",
      "badges.personal": "Personal secure",
      "badges.team": "Team workspace",
      "badges.dev": "Development mode",
      "teamCard.title": "Workspace",
      "teamCard.access": "Access",
      "teamCard.adminCreated": "Accounts are created by an admin.",
      "local.adminProvisioned": "Use the credentials provided by your administrator.",
      oauthDivider: "or continue with",
      noProviders: "No sign-in providers are configured.",
      terms: "Protected workspace access only.",
      "preview.eyebrow": "Team workspace",
      "preview.title": "Shared bioinformatics operations",
      "preview.description": "Projects, runs, and conversations stay visible to the team.",
      "preview.chatLabel": "Session",
      "preview.chatTitle": "Analysis thread",
      "preview.workspaceShared": "Shared",
      "preview.chatExample": "Can you compare the latest RNA-seq batches?",
      "preview.planningWorkflow": "Differential expression plan",
      "preview.audit": "audit",
      "preview.membersLabel": "Roles",
      "preview.tagline": "Owner and admins manage members. Everyone works in one space.",
      "preview.roles.owner.name": "Owner",
      "preview.roles.owner.description": "Keeps the instance safe and recoverable.",
      "preview.roles.admin.name": "Admin",
      "preview.roles.admin.description": "Manages people and daily operations.",
      "preview.roles.member.name": "Member",
      "preview.roles.member.description": "Uses projects, runs, and conversations.",
    }
    return labels[key] ?? key
  },
}))

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string
    children: React.ReactNode
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock("@/components/auth/email-sign-in-form", () => ({
  EmailSignInForm: () => <div data-testid="email-sign-in-form" />,
}))

vi.mock("@/lib/auth", () => ({
  ensureAuthReady: () => mockEnsureAuthReady(),
  getAuth: () => mockGetAuth(),
}))

vi.mock("@/lib/auth-config", () => ({
  getServerAuthConfig: () => mockGetServerAuthConfig(),
  authProviderStatus: { github: false, google: false },
}))

import AuthPage from "@/app/auth/page"

describe("AuthPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockHeaders.mockResolvedValue(new Headers())
    mockEnsureAuthReady.mockResolvedValue(undefined)
    mockGetAuth.mockResolvedValue({
      api: {
        getSession: (opts: unknown) => mockGetSession(opts),
      },
    })
    mockGetServerAuthConfig.mockReturnValue({
      mode: "team",
      authEnabled: true,
      authLocalEnabled: true,
      authSelfSignupEnabled: false,
      workspaceName: "Bioinfoflow Team",
    })
  })

  it("redirects to /agent when auth is disabled", async () => {
    mockGetServerAuthConfig.mockReturnValue({
      mode: "dev",
      authEnabled: false,
      authLocalEnabled: false,
      authSelfSignupEnabled: false,
      workspaceName: "Bioinfoflow Team",
    })

    await expect(AuthPage()).rejects.toThrow("NEXT_REDIRECT: /agent")
    expect(mockEnsureAuthReady).not.toHaveBeenCalled()
    expect(mockGetSession).not.toHaveBeenCalled()
  })

  it("redirects authenticated users to /agent", async () => {
    mockGetSession.mockResolvedValue({
      user: { id: "u1", name: "Owner", email: "owner@example.com" },
      session: { id: "s1" },
    })

    await expect(AuthPage()).rejects.toThrow("NEXT_REDIRECT: /agent")
    expect(mockEnsureAuthReady).toHaveBeenCalled()
    expect(mockGetSession).toHaveBeenCalled()
  })

  it("renders the local sign-in entry when local auth is enabled", async () => {
    mockGetSession.mockResolvedValue(null)

    const page = await AuthPage()
    render(page as React.ReactElement)

    expect(screen.getByText("Sign in to continue")).toBeInTheDocument()
    expect(screen.getByTestId("email-sign-in-form")).toBeInTheDocument()
    expect(
      screen.getByText("Use the credentials provided by your administrator."),
    ).toBeInTheDocument()
  })

  it("renders a personal-mode auth page without the team preview panel", async () => {
    mockGetSession.mockResolvedValue(null)
    mockGetServerAuthConfig.mockReturnValue({
      mode: "personal",
      authEnabled: true,
      authLocalEnabled: true,
      authSelfSignupEnabled: false,
      workspaceName: "Bioinfoflow Team",
    })

    const page = await AuthPage()
    render(page as React.ReactElement)

    expect(screen.getByText("Personal secure")).toBeInTheDocument()
    expect(screen.queryByText("Team workspace")).not.toBeInTheDocument()
  })
})

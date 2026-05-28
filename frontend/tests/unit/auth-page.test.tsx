import * as React from "react"
import { render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mockRedirect = vi.fn()
const mockGetSession = vi.fn()
const mockHeaders = vi.fn()
const mockCookies = vi.fn()
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
  cookies: () => mockCookies(),
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
      "demo.badge": "Public demo",
      "demo.description": "Pick a demo sign-in option to enter the scripted product tour.",
      "demo.continueAsGuest": "Continue as guest",
      "demo.oauthHint": "No real account is required. These buttons start a mock demo session.",
      continueWithGithub: "Continue with GitHub",
      continueWithGoogle: "Continue with Google",
      "demo.eyebrow": "Scripted walkthrough",
      "demo.title": "Sign in once, then explore the real app shell.",
      "demo.subtitle": "The demo keeps the production pages, but every workflow, run, and chat response is mocked.",
      "demo.previewLabel": "What happens next",
      "demo.previewBadge": "Zero setup",
      "demo.previewTitle": "You land directly inside the seeded RNA-seq workspace.",
      "demo.previewResponse": "I can kick off the seeded RNA-seq run and narrate every step live.",
      "teamCard.title": "Workspace",
      "teamCard.access": "Access",
      "teamCard.adminCreated": "Accounts are created by an admin.",
      "local.adminProvisioned": "Use the credentials provided by your administrator.",
      "local.personalProvisioned": "Use your local credentials to continue.",
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
      "preview.personalTitle": "Private workstation, protected by password",
      "preview.personalDescription": "Personal mode keeps the full app behind login.",
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

vi.mock("@/components/auth/auth-actions", () => ({
  AuthActions: () => <div data-testid="auth-actions" />,
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
    mockCookies.mockReturnValue({ get: () => undefined })
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

  afterEach(() => {
    delete process.env.DEPLOY_MODE
    delete process.env.APP_RUNTIME
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

  it("renders the demo auth entry even when Better Auth is disabled in demo mode", async () => {
    process.env.DEPLOY_MODE = "demo"
    mockGetServerAuthConfig.mockReturnValue({
      mode: "dev",
      authEnabled: false,
      authLocalEnabled: false,
      authSelfSignupEnabled: false,
      workspaceName: "Bioinfoflow Team",
    })

    const page = await AuthPage()
    render(page as React.ReactElement)

    expect(mockRedirect).not.toHaveBeenCalled()
    expect(mockEnsureAuthReady).not.toHaveBeenCalled()
    expect(mockGetSession).not.toHaveBeenCalled()
    expect(screen.getByText("Sign in to continue")).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: /continue with github/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: /continue with google/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: /continue as guest/i }),
    ).toBeInTheDocument()
  })

  it("renders the demo auth entry when APP_RUNTIME is demo", async () => {
    process.env.APP_RUNTIME = "demo"
    mockGetServerAuthConfig.mockReturnValue({
      mode: "dev",
      authEnabled: false,
      authLocalEnabled: false,
      authSelfSignupEnabled: false,
      workspaceName: "Bioinfoflow Team",
    })

    const page = await AuthPage()
    render(page as React.ReactElement)

    expect(mockRedirect).not.toHaveBeenCalled()
    expect(screen.getByRole("link", { name: /continue as guest/i })).toBeInTheDocument()
  })

  it("keeps the demo auth screen intentionally minimal", async () => {
    process.env.DEPLOY_MODE = "demo"
    mockGetServerAuthConfig.mockReturnValue({
      mode: "dev",
      authEnabled: false,
      authLocalEnabled: false,
      authSelfSignupEnabled: false,
      workspaceName: "Bioinfoflow Team",
    })

    const page = await AuthPage()
    render(page as React.ReactElement)

    expect(screen.queryByText("Scripted walkthrough")).not.toBeInTheDocument()
    expect(
      screen.queryByText("You land directly inside the seeded RNA-seq workspace."),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText("I can kick off the seeded RNA-seq run and narrate every step live."),
    ).not.toBeInTheDocument()
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
      screen.queryByText("Use your local credentials to continue."),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText("Private workstation, protected by password"),
    ).not.toBeInTheDocument()
    expect(screen.queryByText("Shared bioinformatics operations")).not.toBeInTheDocument()
  })

  it("renders personal mode with the same simplified login card", async () => {
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
    expect(screen.getByTestId("email-sign-in-form")).toBeInTheDocument()
    expect(screen.queryByText("Team workspace")).not.toBeInTheDocument()
    expect(
      screen.queryByText("Private workstation, protected by password"),
    ).not.toBeInTheDocument()
  })
})

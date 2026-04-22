import type { SocialProviders } from "better-auth/social-providers"

export const DEFAULT_WORKSPACE_NAME = "Bioinfoflow Team"

export type AuthMode = "personal" | "team" | "dev"
export type TeamRole = "owner" | "admin" | "member"

export type ViewerIdentity = {
  id: string
  name: string
  email: string
  image?: string | null
  role: TeamRole
  mode: AuthMode
  canManageMembers: boolean
  disabled: boolean
  authEnabled: boolean
  workspaceName: string
}

function parseBoolean(value: string | undefined, defaultValue: boolean): boolean {
  if (value == null || value.trim() === "") {
    return defaultValue
  }

  const normalized = value.trim().toLowerCase()
  if (["1", "true", "yes", "on"].includes(normalized)) {
    return true
  }
  if (["0", "false", "no", "off"].includes(normalized)) {
    return false
  }
  return defaultValue
}

function parseAuthMode(value: string | undefined): AuthMode | null {
  if (!value) {
    return null
  }

  const normalized = value.trim().toLowerCase()
  if (
    normalized === "personal" ||
    normalized === "team" ||
    normalized === "dev"
  ) {
    return normalized
  }

  return null
}

function resolveAuthMode(
  explicitMode: string | undefined,
  legacyAuthEnabledValue: string | undefined,
): AuthMode {
  const parsedMode = parseAuthMode(explicitMode)
  if (parsedMode) {
    return parsedMode
  }

  return parseBoolean(legacyAuthEnabledValue, true) ? "personal" : "dev"
}

export function canManageMembers(
  mode: AuthMode,
  role: TeamRole,
  authEnabled = true,
): boolean {
  return authEnabled && mode === "team" && ["owner", "admin"].includes(role)
}

export function getServerAuthConfig() {
  const mode = resolveAuthMode(
    process.env.AUTH_MODE ?? process.env.NEXT_PUBLIC_AUTH_MODE,
    process.env.AUTH_ENABLED ?? process.env.NEXT_PUBLIC_AUTH_ENABLED,
  )
  const authEnabled = mode !== "dev"
  const authLocalEnabled = parseBoolean(
    process.env.AUTH_LOCAL_ENABLED ?? process.env.NEXT_PUBLIC_AUTH_LOCAL_ENABLED,
    true,
  )
  const authSelfSignupEnabled = parseBoolean(
    process.env.AUTH_SELF_SIGNUP_ENABLED ??
      process.env.NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED,
    false,
  )

  // OAuth social providers are only available in the Vercel demo deployment.
  // Local dev and Docker Compose instances use email/password auth only.
  const isDemo = process.env.DEPLOY_MODE === "demo"

  const githubEnabled = isDemo && Boolean(
    process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET,
  )
  const googleEnabled = isDemo && Boolean(
    process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET,
  )

  return {
    mode,
    authEnabled,
    authLocalEnabled,
    authSelfSignupEnabled,
    githubEnabled,
    googleEnabled,
    workspaceName:
      process.env.DEFAULT_WORKSPACE_NAME ||
      process.env.NEXT_PUBLIC_DEFAULT_WORKSPACE_NAME ||
      DEFAULT_WORKSPACE_NAME,
    bootstrapOwnerEmail: process.env.AUTH_BOOTSTRAP_OWNER_EMAIL ?? "",
    bootstrapOwnerPassword: process.env.AUTH_BOOTSTRAP_OWNER_PASSWORD ?? "",
  }
}

const clientMode = resolveAuthMode(
  process.env.NEXT_PUBLIC_AUTH_MODE,
  process.env.NEXT_PUBLIC_AUTH_ENABLED,
)

export const clientAuthConfig = {
  mode: clientMode,
  authEnabled: clientMode !== "dev",
  authLocalEnabled: parseBoolean(
    process.env.NEXT_PUBLIC_AUTH_LOCAL_ENABLED,
    true,
  ),
  authSelfSignupEnabled: parseBoolean(
    process.env.NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED,
    false,
  ),
  workspaceName:
    process.env.NEXT_PUBLIC_DEFAULT_WORKSPACE_NAME || DEFAULT_WORKSPACE_NAME,
}

export function resolveTeamRole(user: {
  teamRole?: string | null
  role?: string | null
} | null | undefined): TeamRole {
  if (user?.teamRole === "owner" || user?.teamRole === "admin") {
    return user.teamRole
  }
  if (user?.role === "admin") {
    return "admin"
  }
  return "member"
}

export function toBetterAuthRole(teamRole: TeamRole): "admin" | "user" {
  return teamRole === "member" ? "user" : "admin"
}

export function buildAnonymousViewer(): ViewerIdentity {
  return {
    id: "dev",
    name: "Local User",
    email: "local@bioinfoflow",
    role: "owner",
    mode: "dev",
    canManageMembers: false,
    disabled: false,
    authEnabled: false,
    workspaceName: clientAuthConfig.workspaceName,
  }
}

export function buildViewerIdentity(
  user: {
    id: string
    name?: string | null
    email?: string | null
    image?: string | null
    role?: string | null
    teamRole?: string | null
    banned?: boolean | null
  },
  authConfig = getServerAuthConfig(),
): ViewerIdentity {
  const role = resolveTeamRole(user)

  return {
    id: user.id,
    name: user.name || "Bioinfoflow User",
    email: user.email || "",
    image: user.image,
    role,
    mode: authConfig.mode,
    canManageMembers: canManageMembers(
      authConfig.mode,
      role,
      authConfig.authEnabled,
    ),
    disabled: Boolean(user.banned),
    authEnabled: authConfig.authEnabled,
    workspaceName: authConfig.workspaceName,
  }
}

// ---------------------------------------------------------------------------
// OAuth social providers (conditional on env vars)
// ---------------------------------------------------------------------------

const serverAuthConfig = getServerAuthConfig()

export const authProviderStatus = {
  github: serverAuthConfig.githubEnabled,
  google: serverAuthConfig.googleEnabled,
}

export const authSocialProviders = {
  ...(serverAuthConfig.githubEnabled
    ? {
        github: {
          clientId: process.env.GITHUB_CLIENT_ID!,
          clientSecret: process.env.GITHUB_CLIENT_SECRET!,
        },
      }
    : {}),
  ...(serverAuthConfig.googleEnabled
    ? {
        google: {
          clientId: process.env.GOOGLE_CLIENT_ID!,
          clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
          prompt: "select_account" as const,
        },
      }
    : {}),
} satisfies SocialProviders

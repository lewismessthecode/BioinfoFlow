import "server-only"

import { createHash } from "node:crypto"
import { mkdirSync } from "node:fs"
import { hostname } from "node:os"
import path from "node:path"
import { countOwnerUsers, guardAdminOperation } from "@/lib/auth-admin-guards"
import { planBootstrapOwner } from "@/lib/auth-bootstrap"
import { authSocialProviders, getServerAuthConfig, resolveTeamRole, toBetterAuthRole } from "@/lib/auth-config"

const authConfig = getServerAuthConfig()

let warnedAboutDerivedSecret = false
let authPromise: Promise<Awaited<ReturnType<typeof createAuthInstance>> | null> | null =
  null
let authReadyPromise: Promise<void> | null = null

const LEGACY_FRONTEND_BETTER_AUTH_PATHS = new Set(["better-auth.db", "./better-auth.db"])

function resolveBioinfoflowHome() {
  const configured = process.env.BIOINFOFLOW_HOME?.trim()
  if (configured) {
    return path.resolve(process.cwd(), configured)
  }

  // Local frontend dev runs from <repo>/frontend; default to the shared repo data root.
  return path.resolve(process.cwd(), "..", "data")
}

export function resolveBetterAuthDbPath() {
  const configured = process.env.BETTER_AUTH_DB_PATH?.trim()
  if (configured && !LEGACY_FRONTEND_BETTER_AUTH_PATHS.has(configured)) {
    return path.resolve(process.cwd(), configured)
  }

  return path.join(resolveBioinfoflowHome(), "state", "auth", "better-auth.db")
}

export function resolveBetterAuthSecret() {
  if (process.env.BETTER_AUTH_SECRET) {
    return process.env.BETTER_AUTH_SECRET
  }

  if (process.env.NODE_ENV === "production") {
    throw new Error("BETTER_AUTH_SECRET must be set in production")
  }

  if (!warnedAboutDerivedSecret) {
    warnedAboutDerivedSecret = true
    console.warn(
      "BETTER_AUTH_SECRET is not set. Falling back to a local instance secret derived from host and workspace paths. Set BETTER_AUTH_SECRET for shared or production deployments.",
    )
  }

  return createHash("sha256")
    .update(
      [
        hostname(),
        process.cwd(),
        resolveBetterAuthDbPath(),
      ].join(":"),
    )
    .digest("hex")
}

async function createAuthInstance() {
  if (!authConfig.authEnabled) {
    return null
  }

  const [
    { betterAuth },
    { nextCookies },
    { admin },
    { APIError, createAuthMiddleware },
    betterSqliteModule,
  ] = await Promise.all([
    import("better-auth"),
    import("better-auth/next-js"),
    import("better-auth/plugins/admin"),
    import("better-auth/api"),
    import("better-sqlite3"),
  ])

  const Database = betterSqliteModule.default
  const betterAuthDbPath = resolveBetterAuthDbPath()
  mkdirSync(path.dirname(betterAuthDbPath), { recursive: true })
  const database = new Database(betterAuthDbPath)

  // Enable WAL mode for safe concurrent reads from backend container
  database.pragma("journal_mode = WAL")

  const trustedOrigins = [process.env.BETTER_AUTH_URL].filter(
    (value): value is string => Boolean(value),
  )

  return betterAuth({
    appName: "Bioinfoflow",
    baseURL: process.env.BETTER_AUTH_URL,
    trustedOrigins,
    secret: resolveBetterAuthSecret(),
    database,
    emailAndPassword: {
      enabled: authConfig.authLocalEnabled,
      disableSignUp: !authConfig.authSelfSignupEnabled,
    },
    user: {
      additionalFields: {
        teamRole: {
          type: "string",
          required: false,
          input: false,
          defaultValue: "member",
        },
      },
    },
    hooks: {
      before: createAuthMiddleware(async (ctx) => {
        if (!ctx.path.startsWith("/admin/")) {
          return
        }

        const session = ctx.context.session
        if (!session) {
          throw new APIError("UNAUTHORIZED")
        }

        const targetUserId =
          typeof ctx.body?.userId === "string" ? ctx.body.userId : null
        const targetUser = targetUserId
          ? await ctx.context.internalAdapter.findUserById(targetUserId)
          : null

        const requiresOwnerCount =
          ctx.path === "/admin/ban-user" ||
          ctx.path === "/admin/remove-user" ||
          ctx.path === "/admin/update-user"
        const users = requiresOwnerCount
          ? await ctx.context.internalAdapter.listUsers()
          : []

        const error = guardAdminOperation({
          mode: authConfig.mode,
          actorRole: resolveTeamRole(
            session.user as { teamRole?: string | null; role?: string | null },
          ),
          path: ctx.path,
          body: ctx.body,
          targetUser,
          ownerCount: countOwnerUsers(users),
        })

        if (error) {
          throw new APIError("FORBIDDEN", { message: error })
        }
      }),
    },
    socialProviders: authSocialProviders,
    plugins: [admin(), nextCookies()],
  })
}

export async function getAuth() {
  if (!authPromise) {
    authPromise = createAuthInstance()
  }

  return authPromise
}

function ownerNameFromEmail(email: string): string {
  const [local] = email.split("@")
  const cleaned = local
    .replace(/[._-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase())
  return cleaned || "Bioinfoflow Owner"
}

async function bootstrapOwnerIfNeeded() {
  const auth = await getAuth()

  if (
    !auth ||
    !authConfig.authEnabled ||
    !authConfig.authLocalEnabled ||
    !authConfig.bootstrapOwnerEmail ||
    !authConfig.bootstrapOwnerPassword
  ) {
    return
  }

  const ctx = await auth.$context
  const email = authConfig.bootstrapOwnerEmail.trim().toLowerCase()
  const passwordHash = await ctx.password.hash(
    authConfig.bootstrapOwnerPassword,
  )

  const existingUser = await ctx.internalAdapter.findUserByEmail(email, {
    includeAccounts: true,
  })
  const plan = planBootstrapOwner({
    email,
    existingUser: existingUser
      ? {
          id: existingUser.user.id,
          hasCredentialAccount: existingUser.accounts.some(
            (account) => account.providerId === "credential",
          ),
        }
      : null,
  })

  if (plan.type === "recover") {
    await ctx.internalAdapter.updateUser(plan.userId, {
      role: toBetterAuthRole("owner"),
      teamRole: "owner",
      emailVerified: true,
      banned: false,
      banReason: null,
      banExpires: null,
    })

    if (!plan.hasCredentialAccount) {
      await ctx.internalAdapter.createAccount({
        userId: plan.userId,
        providerId: "credential",
        accountId: plan.userId,
        password: passwordHash,
      })
      return
    }

    await ctx.internalAdapter.updatePassword(plan.userId, passwordHash)
    return
  }

  const owner = await ctx.internalAdapter.createUser({
    email: plan.email,
    name: ownerNameFromEmail(plan.email),
    emailVerified: true,
    role: toBetterAuthRole("owner"),
    teamRole: "owner",
  })

  await ctx.internalAdapter.linkAccount({
    accountId: owner.id,
    providerId: "credential",
    userId: owner.id,
    password: passwordHash,
  })
}

export async function ensureAuthReady() {
  if (!authConfig.authEnabled) {
    return
  }

  if (!authReadyPromise) {
    authReadyPromise = (async () => {
      const auth = await getAuth()
      if (!auth) {
        return
      }

      const ctx = await auth.$context
      await ctx.runMigrations()
      await bootstrapOwnerIfNeeded()
    })()
  }

  await authReadyPromise
}

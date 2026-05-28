import { headers } from "next/headers"
import { ensureAuthReady, getAuth } from "@/lib/auth"
import { guardAdminOperation } from "@/lib/auth-admin-guards"
import {
  getServerAuthConfig,
  resolveTeamRole,
  toBetterAuthRole,
  type TeamRole,
} from "@/lib/auth-config"

type TeamMember = {
  id: string
  name?: string | null
  email?: string | null
  role?: string | null
  teamRole?: string | null
  banned?: boolean | null
}

const TEAM_ROLES = new Set<TeamRole>(["owner", "admin", "member"])

function success(data: unknown, status = 200) {
  return Response.json({ success: true, data }, { status })
}

function failure(message: string, status: number) {
  return Response.json(
    {
      success: false,
      error: { message },
    },
    { status },
  )
}

function normalizeString(value: unknown) {
  return typeof value === "string" ? value.trim() : ""
}

function normalizeRole(value: unknown): TeamRole {
  return TEAM_ROLES.has(value as TeamRole) ? (value as TeamRole) : "member"
}

async function requireMemberManager() {
  const authConfig = getServerAuthConfig()
  if (!authConfig.authEnabled || authConfig.mode !== "team") {
    return {
      error: failure("Member management is only available in team mode.", 403),
    }
  }

  await ensureAuthReady()
  const auth = await getAuth()
  if (!auth) {
    return { error: failure("Authentication is not available.", 404) }
  }

  const session = await auth.api.getSession({
    headers: await headers(),
  })
  if (!session?.user) {
    return { error: failure("Sign in to manage members.", 401) }
  }

  const actorRole = resolveTeamRole(
    session.user as { teamRole?: string | null; role?: string | null },
  )
  const guardError = guardAdminOperation({
    mode: authConfig.mode,
    actorRole,
    path: "/admin/create-user",
    ownerCount: 0,
    body: { data: { teamRole: "member" } },
  })
  if (guardError) {
    return { error: failure(guardError, 403) }
  }

  const ctx = await auth.$context
  return { authConfig, actorRole, ctx }
}

export async function GET() {
  const manager = await requireMemberManager()
  if ("error" in manager) {
    return manager.error
  }

  const users = (await manager.ctx.internalAdapter.listUsers()) as TeamMember[]
  return success({ users })
}

export async function POST(request: Request) {
  const manager = await requireMemberManager()
  if ("error" in manager) {
    return manager.error
  }

  let body: Record<string, unknown>
  try {
    body = (await request.json()) as Record<string, unknown>
  } catch {
    return failure("Invalid member payload.", 400)
  }

  const name = normalizeString(body.name)
  const email = normalizeString(body.email).toLowerCase()
  const password = normalizeString(body.password)
  const teamRole = normalizeRole(body.teamRole)

  if (!name) {
    return failure("Name is required.", 400)
  }
  if (!email || !email.includes("@")) {
    return failure("A valid email is required.", 400)
  }
  if (manager.authConfig.authLocalEnabled && password.length < 8) {
    return failure("Password must be at least 8 characters.", 400)
  }

  const roleGuardError = guardAdminOperation({
    mode: manager.authConfig.mode,
    actorRole: manager.actorRole,
    path: "/admin/create-user",
    ownerCount: 0,
    body: {
      role: toBetterAuthRole(teamRole),
      data: { teamRole },
    },
  })
  if (roleGuardError) {
    return failure(roleGuardError, 403)
  }

  const existing = await manager.ctx.internalAdapter.findUserByEmail(email, {
    includeAccounts: false,
  })
  if (existing) {
    return failure("A member with this email already exists.", 409)
  }

  try {
    const user = (await manager.ctx.internalAdapter.createUser({
      email,
      name,
      emailVerified: true,
      role: toBetterAuthRole(teamRole),
      teamRole,
    })) as TeamMember

    if (manager.authConfig.authLocalEnabled) {
      const passwordHash = await manager.ctx.password.hash(password)
      await manager.ctx.internalAdapter.linkAccount({
        accountId: user.id,
        providerId: "credential",
        userId: user.id,
        password: passwordHash,
      })
    }

    return success({ user }, 201)
  } catch {
    return failure("Could not create that member. Check the account details and try again.", 500)
  }
}

export async function PATCH(request: Request) {
  const manager = await requireMemberManager()
  if ("error" in manager) {
    return manager.error
  }

  let body: Record<string, unknown>
  try {
    body = (await request.json()) as Record<string, unknown>
  } catch {
    return failure("Invalid member payload.", 400)
  }

  const userId = normalizeString(body.userId)
  const action = normalizeString(body.action)
  if (!userId) {
    return failure("Member id is required.", 400)
  }

  const targetUser = (await manager.ctx.internalAdapter.findUserById(
    userId,
  )) as TeamMember | null
  if (!targetUser) {
    return failure("Member not found.", 404)
  }

  const users = (await manager.ctx.internalAdapter.listUsers()) as TeamMember[]
  const ownerCount = users.filter((user) => resolveTeamRole(user) === "owner").length

  if (action === "role") {
    const teamRole = normalizeRole(body.teamRole)
    const guardError = guardAdminOperation({
      mode: manager.authConfig.mode,
      actorRole: manager.actorRole,
      path: "/admin/update-user",
      ownerCount,
      body: {
        role: toBetterAuthRole(teamRole),
        data: { teamRole },
      },
      targetUser,
    })
    if (guardError) {
      return failure(guardError, 403)
    }

    const user = await manager.ctx.internalAdapter.updateUser(userId, {
      role: toBetterAuthRole(teamRole),
      teamRole,
    })
    return success({ user })
  }

  if (action === "disabled") {
    const disabled = Boolean(body.disabled)
    const guardError = guardAdminOperation({
      mode: manager.authConfig.mode,
      actorRole: manager.actorRole,
      path: disabled ? "/admin/ban-user" : "/admin/unban-user",
      ownerCount,
      body: { userId },
      targetUser,
    })
    if (guardError) {
      return failure(guardError, 403)
    }

    const user = await manager.ctx.internalAdapter.updateUser(userId, {
      banned: disabled,
      banReason: disabled ? "Disabled by administrator" : null,
      banExpires: null,
    })
    return success({ user })
  }

  if (action === "password") {
    if (!manager.authConfig.authLocalEnabled) {
      return failure("Password reset is only available for local auth.", 400)
    }
    const password = normalizeString(body.password)
    if (password.length < 8) {
      return failure("Password must be at least 8 characters.", 400)
    }
    if (resolveTeamRole(targetUser) === "owner" && manager.actorRole !== "owner") {
      return failure("Only owners can reset owner passwords.", 403)
    }

    const passwordHash = await manager.ctx.password.hash(password)
    await manager.ctx.internalAdapter.updatePassword(userId, passwordHash)
    return success({ user: targetUser })
  }

  return failure("Unsupported member update.", 400)
}

import { resolveTeamRole, type AuthMode, type TeamRole } from "@/lib/auth-config"

type GuardBody =
  | {
      userId?: string
      role?: string
      data?: {
        role?: string
        teamRole?: string
      }
    }
  | null
  | undefined

type GuardUser = {
  id: string
  role?: string | null
  teamRole?: string | null
}

type GuardInput = {
  mode: AuthMode
  actorRole: TeamRole
  path: string
  ownerCount: number
  body?: GuardBody
  targetUser?: GuardUser | null
}

const DISABLED_ADMIN_PATHS = new Set([
  "/admin/remove-user",
  "/admin/impersonate-user",
  "/admin/stop-impersonating",
  "/admin/set-role",
])

function isAdminPath(path: string): boolean {
  return path.startsWith("/admin/")
}

function resolveRequestedTeamRole(body?: GuardBody): TeamRole | null {
  const explicitTeamRole = body?.data?.teamRole
  if (
    explicitTeamRole === "owner" ||
    explicitTeamRole === "admin" ||
    explicitTeamRole === "member"
  ) {
    return explicitTeamRole
  }

  const roleValue = body?.data?.role ?? body?.role
  if (roleValue === "admin") {
    return "admin"
  }
  if (roleValue === "user") {
    return "member"
  }

  return null
}

export function countOwnerUsers(users: GuardUser[]): number {
  return users.filter((user) => resolveTeamRole(user) === "owner").length
}

export function guardAdminOperation({
  mode,
  actorRole,
  path,
  ownerCount,
  body,
  targetUser,
}: GuardInput): string | null {
  if (!isAdminPath(path)) {
    return null
  }

  if (DISABLED_ADMIN_PATHS.has(path)) {
    if (path === "/admin/remove-user") {
      return "Deleting accounts is not available in Auth v1.1."
    }
    return "This admin action is disabled in Auth v1.1."
  }

  if (mode !== "team") {
    return "Member management is only available in team mode."
  }

  if (!["owner", "admin"].includes(actorRole)) {
    return "Only owners and admins can manage members."
  }

  const requestedRole = resolveRequestedTeamRole(body)
  if (requestedRole === "owner" && actorRole !== "owner") {
    return "Only owners can assign the owner role."
  }

  if (targetUser && resolveTeamRole(targetUser) === "owner") {
    const isBanOperation = path === "/admin/ban-user"
    const isDemotion =
      path === "/admin/update-user" &&
      requestedRole !== null &&
      requestedRole !== "owner"

    if ((isBanOperation || isDemotion) && ownerCount <= 1) {
      return "At least one owner must remain active."
    }
  }

  return null
}

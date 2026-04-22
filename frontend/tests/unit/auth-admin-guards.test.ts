import { describe, expect, it } from "vitest"

import { guardAdminOperation } from "@/lib/auth-admin-guards"

describe("auth admin guards", () => {
  it("blocks member management endpoints outside team mode", () => {
    const error = guardAdminOperation({
      mode: "personal",
      actorRole: "owner",
      path: "/admin/create-user",
      ownerCount: 1,
      body: {
        data: {
          teamRole: "member",
        },
      },
    })

    expect(error).toBe("Member management is only available in team mode.")
  })

  it("prevents admins from assigning the owner role", () => {
    const error = guardAdminOperation({
      mode: "team",
      actorRole: "admin",
      path: "/admin/update-user",
      ownerCount: 2,
      body: {
        data: {
          teamRole: "owner",
        },
      },
      targetUser: {
        id: "user-2",
        teamRole: "member",
        role: "user",
      },
    })

    expect(error).toBe("Only owners can assign the owner role.")
  })

  it("prevents disabling the last remaining owner", () => {
    const error = guardAdminOperation({
      mode: "team",
      actorRole: "owner",
      path: "/admin/ban-user",
      ownerCount: 1,
      body: {
        userId: "owner-1",
      },
      targetUser: {
        id: "owner-1",
        teamRole: "owner",
        role: "admin",
      },
    })

    expect(error).toBe("At least one owner must remain active.")
  })

  it("prevents deleting accounts in auth v1.1", () => {
    const error = guardAdminOperation({
      mode: "team",
      actorRole: "owner",
      path: "/admin/remove-user",
      ownerCount: 2,
      body: {
        userId: "member-1",
      },
      targetUser: {
        id: "member-1",
        teamRole: "member",
        role: "user",
      },
    })

    expect(error).toBe("Deleting accounts is not available in Auth v1.1.")
  })

  it("allows owners to create non-owner users in team mode", () => {
    const error = guardAdminOperation({
      mode: "team",
      actorRole: "owner",
      path: "/admin/create-user",
      ownerCount: 1,
      body: {
        role: "admin",
        data: {
          teamRole: "admin",
        },
      },
    })

    expect(error).toBeNull()
  })
})

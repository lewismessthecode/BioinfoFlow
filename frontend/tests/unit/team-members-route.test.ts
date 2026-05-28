import { beforeEach, describe, expect, it, vi } from "vitest"

const {
  getAuthMock,
  getServerAuthConfigMock,
  headersMock,
  findUserByEmailMock,
  findUserByIdMock,
  listUsersMock,
  createUserMock,
  linkAccountMock,
  updateUserMock,
  updatePasswordMock,
} = vi.hoisted(() => ({
  getAuthMock: vi.fn(),
  getServerAuthConfigMock: vi.fn(),
  headersMock: vi.fn(),
  findUserByEmailMock: vi.fn(),
  findUserByIdMock: vi.fn(),
  listUsersMock: vi.fn(),
  createUserMock: vi.fn(),
  linkAccountMock: vi.fn(),
  updateUserMock: vi.fn(),
  updatePasswordMock: vi.fn(),
}))

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
}))

vi.mock("@/lib/auth", () => ({
  getAuth: () => getAuthMock(),
  ensureAuthReady: vi.fn(),
}))

vi.mock("@/lib/auth-config", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth-config")>(
    "@/lib/auth-config",
  )
  return {
    ...actual,
    getServerAuthConfig: () => getServerAuthConfigMock(),
  }
})

function request(body: unknown, method = "POST") {
  return new Request("http://localhost/api/team/members", {
    method,
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  })
}

async function json(response: Response) {
  return response.json() as Promise<{
    success: boolean
    data?: unknown
    error?: { message: string }
  }>
}

describe("team members route", () => {
  beforeEach(() => {
    vi.resetModules()
    getAuthMock.mockReset()
    getServerAuthConfigMock.mockReset()
    headersMock.mockReset()
    findUserByEmailMock.mockReset()
    findUserByIdMock.mockReset()
    listUsersMock.mockReset()
    createUserMock.mockReset()
    linkAccountMock.mockReset()
    updateUserMock.mockReset()
    updatePasswordMock.mockReset()

    headersMock.mockResolvedValue(new Headers())
    getServerAuthConfigMock.mockReturnValue({
      mode: "team",
      authEnabled: true,
      authLocalEnabled: true,
    })
    getAuthMock.mockResolvedValue({
      api: {
        getSession: vi.fn().mockResolvedValue({
          user: {
            id: "owner-1",
            role: "admin",
            teamRole: "owner",
          },
        }),
      },
      $context: Promise.resolve({
        password: {
          hash: vi.fn().mockResolvedValue("hashed-password"),
        },
        internalAdapter: {
          findUserByEmail: findUserByEmailMock,
          findUserById: findUserByIdMock,
          listUsers: listUsersMock,
          createUser: createUserMock,
          linkAccount: linkAccountMock,
          updateUser: updateUserMock,
          updatePassword: updatePasswordMock,
        },
      }),
    })
  })

  it("creates a local-auth team member with teamRole and credential account", async () => {
    findUserByEmailMock.mockResolvedValue(null)
    createUserMock.mockResolvedValue({
      id: "member-1",
      email: "new@example.com",
      name: "New Member",
      role: "user",
      teamRole: "member",
    })

    const { POST } = await import("@/app/api/team/members/route")
    const response = await POST(
      request({
        name: "New Member",
        email: "NEW@example.com",
        password: "secret123",
        teamRole: "member",
      }),
    )
    const payload = await json(response)

    expect(response.status).toBe(201)
    expect(payload.success).toBe(true)
    expect(createUserMock).toHaveBeenCalledWith(
      expect.objectContaining({
        email: "new@example.com",
        name: "New Member",
        role: "user",
        teamRole: "member",
        emailVerified: true,
      }),
    )
    expect(linkAccountMock).toHaveBeenCalledWith(
      expect.objectContaining({
        userId: "member-1",
        providerId: "credential",
        password: "hashed-password",
      }),
    )
  })

  it("maps duplicate emails to a readable conflict response", async () => {
    findUserByEmailMock.mockResolvedValue({ user: { id: "existing" } })

    const { POST } = await import("@/app/api/team/members/route")
    const response = await POST(
      request({
        name: "Existing",
        email: "existing@example.com",
        password: "secret123",
        teamRole: "member",
      }),
    )
    const payload = await json(response)

    expect(response.status).toBe(409)
    expect(payload.success).toBe(false)
    expect(payload.error?.message).toBe("A member with this email already exists.")
    expect(createUserMock).not.toHaveBeenCalled()
  })

  it("prevents admins from creating owner accounts", async () => {
    getAuthMock.mockResolvedValueOnce({
      api: {
        getSession: vi.fn().mockResolvedValue({
          user: {
            id: "admin-1",
            role: "admin",
            teamRole: "admin",
          },
        }),
      },
      $context: Promise.resolve({
        password: { hash: vi.fn() },
        internalAdapter: {
          findUserByEmail: findUserByEmailMock,
          findUserById: findUserByIdMock,
          listUsers: listUsersMock,
          createUser: createUserMock,
          linkAccount: linkAccountMock,
          updateUser: updateUserMock,
          updatePassword: updatePasswordMock,
        },
      }),
    })

    const { POST } = await import("@/app/api/team/members/route")
    const response = await POST(
      request({
        name: "New Owner",
        email: "owner@example.com",
        password: "secret123",
        teamRole: "owner",
      }),
    )
    const payload = await json(response)

    expect(response.status).toBe(403)
    expect(payload.error?.message).toBe("Only owners can assign the owner role.")
    expect(createUserMock).not.toHaveBeenCalled()
  })

  it("prevents admins from resetting owner passwords", async () => {
    getAuthMock.mockResolvedValueOnce({
      api: {
        getSession: vi.fn().mockResolvedValue({
          user: {
            id: "admin-1",
            role: "admin",
            teamRole: "admin",
          },
        }),
      },
      $context: Promise.resolve({
        password: {
          hash: vi.fn().mockResolvedValue("hashed-password"),
        },
        internalAdapter: {
          findUserByEmail: findUserByEmailMock,
          findUserById: findUserByIdMock,
          listUsers: listUsersMock,
          createUser: createUserMock,
          linkAccount: linkAccountMock,
          updateUser: updateUserMock,
          updatePassword: updatePasswordMock,
        },
      }),
    })
    findUserByIdMock.mockResolvedValue({
      id: "owner-1",
      role: "admin",
      teamRole: "owner",
    })
    listUsersMock.mockResolvedValue([
      { id: "owner-1", role: "admin", teamRole: "owner" },
      { id: "admin-1", role: "admin", teamRole: "admin" },
    ])

    const { PATCH } = await import("@/app/api/team/members/route")
    const response = await PATCH(
      request(
        {
          action: "password",
          userId: "owner-1",
          password: "newsecret123",
        },
        "PATCH",
      ),
    )
    const payload = await json(response)

    expect(response.status).toBe(403)
    expect(payload.error?.message).toBe("Only owners can reset owner passwords.")
    expect(updatePasswordMock).not.toHaveBeenCalled()
  })

  it("authorizes account re-enabling before updating the user", async () => {
    findUserByIdMock.mockResolvedValue({
      id: "member-1",
      role: "user",
      teamRole: "member",
      banned: true,
    })
    listUsersMock.mockResolvedValue([
      { id: "owner-1", role: "admin", teamRole: "owner" },
      { id: "member-1", role: "user", teamRole: "member", banned: true },
    ])
    updateUserMock.mockResolvedValue({
      id: "member-1",
      role: "user",
      teamRole: "member",
      banned: false,
    })

    const { PATCH } = await import("@/app/api/team/members/route")
    const response = await PATCH(
      request(
        {
          action: "disabled",
          userId: "member-1",
          disabled: false,
        },
        "PATCH",
      ),
    )
    const payload = await json(response)

    expect(response.status).toBe(200)
    expect(payload.success).toBe(true)
    expect(updateUserMock).toHaveBeenCalledWith("member-1", {
      banned: false,
      banReason: null,
      banExpires: null,
    })
  })
})

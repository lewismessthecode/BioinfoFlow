import { beforeEach, describe, expect, it, vi } from "vitest"

const {
  getAuthMock,
  headersMock,
  getSessionMock,
  updateUserMock,
  validateAvatarUploadMock,
  writeAvatarFileMock,
  deleteAvatarFilesMock,
  deleteAvatarVersionMock,
  readAvatarFileMock,
} = vi.hoisted(() => ({
  getAuthMock: vi.fn(),
  headersMock: vi.fn(),
  getSessionMock: vi.fn(),
  updateUserMock: vi.fn(),
  validateAvatarUploadMock: vi.fn(),
  writeAvatarFileMock: vi.fn(),
  deleteAvatarFilesMock: vi.fn(),
  deleteAvatarVersionMock: vi.fn(),
  readAvatarFileMock: vi.fn(),
}))

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
}))

vi.mock("@/lib/auth", () => ({
  ensureAuthReady: vi.fn(),
  getAuth: () => getAuthMock(),
}))

vi.mock("@/lib/avatar/avatar-storage", () => ({
  validateAvatarUpload: (...args: unknown[]) => validateAvatarUploadMock(...args),
  writeAvatarFile: (...args: unknown[]) => writeAvatarFileMock(...args),
  deleteAvatarFiles: (...args: unknown[]) => deleteAvatarFilesMock(...args),
  deleteAvatarVersion: (...args: unknown[]) => deleteAvatarVersionMock(...args),
  readAvatarFile: (...args: unknown[]) => readAvatarFileMock(...args),
}))

function authenticated() {
  getSessionMock.mockResolvedValue({ user: { id: "viewer-1" } })
}

function jsonRequest(body: unknown, method = "PATCH") {
  return new Request("http://localhost/api/profile/avatar", {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

async function payload(response: Response) {
  return response.json() as Promise<{
    success: boolean
    data?: { image?: string | null }
    error?: { message: string }
  }>
}

describe("profile avatar route", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.resetAllMocks()
    vi.spyOn(Date, "now").mockReturnValue(123456789)
    headersMock.mockResolvedValue(new Headers())
    getSessionMock.mockResolvedValue(null)
    updateUserMock.mockResolvedValue({ id: "viewer-1" })
    getAuthMock.mockResolvedValue({
      api: { getSession: getSessionMock },
      $context: Promise.resolve({
        internalAdapter: { updateUser: updateUserMock },
      }),
    })
    validateAvatarUploadMock.mockResolvedValue(Buffer.from("avatar"))
    writeAvatarFileMock.mockResolvedValue(undefined)
    deleteAvatarFilesMock.mockResolvedValue(undefined)
    deleteAvatarVersionMock.mockResolvedValue(undefined)
    readAvatarFileMock.mockResolvedValue(Buffer.from("stored-avatar"))
  })

  it("rejects unauthenticated profile changes", async () => {
    const { PATCH } = await import("@/app/api/profile/avatar/route")
    const response = await PATCH(jsonRequest({ avatarKey: "pixel-persona-03" }))

    expect(response.status).toBe(401)
    expect(updateUserMock).not.toHaveBeenCalled()
  })

  it("rejects an unknown built-in avatar key", async () => {
    authenticated()
    const { PATCH } = await import("@/app/api/profile/avatar/route")
    const response = await PATCH(jsonRequest({ avatarKey: "pixel-persona-99" }))

    expect(response.status).toBe(400)
    expect(updateUserMock).not.toHaveBeenCalled()
  })

  it("stores a built-in reference only for the current user", async () => {
    authenticated()
    const { PATCH } = await import("@/app/api/profile/avatar/route")
    const response = await PATCH(jsonRequest({ avatarKey: "pixel-persona-03" }))
    const data = await payload(response)

    expect(response.status).toBe(200)
    expect(updateUserMock).toHaveBeenCalledWith("viewer-1", {
      image: "bioinfoflow-avatar:pixel-persona-03",
    })
    expect(data.data?.image).toBe("bioinfoflow-avatar:pixel-persona-03")
  })

  it("writes a validated upload before updating the profile and cleans old versions", async () => {
    authenticated()
    const formData = new FormData()
    const file = new File(["webp"], "avatar.webp", { type: "image/webp" })
    formData.set("file", file)

    const { POST } = await import("@/app/api/profile/avatar/route")
    const response = await POST(
      new Request("http://localhost/api/profile/avatar", {
        method: "POST",
        body: formData,
      }),
    )

    expect(response.status).toBe(200)
    expect(validateAvatarUploadMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: "image/webp" }),
    )
    expect(writeAvatarFileMock).toHaveBeenCalledWith(
      "viewer-1",
      "123456789",
      Buffer.from("avatar"),
    )
    expect(updateUserMock).toHaveBeenCalledWith("viewer-1", {
      image: "/api/profile/avatar/file?v=123456789",
    })
    expect(deleteAvatarFilesMock).toHaveBeenCalledWith("viewer-1", "123456789")
    expect(
      writeAvatarFileMock.mock.invocationCallOrder[0],
    ).toBeLessThan(updateUserMock.mock.invocationCallOrder[0])
  })

  it("removes a newly written upload when the profile update fails", async () => {
    authenticated()
    updateUserMock.mockRejectedValueOnce(new Error("database unavailable"))
    const formData = new FormData()
    formData.set("file", new File(["webp"], "avatar.webp", { type: "image/webp" }))

    const { POST } = await import("@/app/api/profile/avatar/route")
    const response = await POST(
      new Request("http://localhost/api/profile/avatar", {
        method: "POST",
        body: formData,
      }),
    )

    expect(response.status).toBe(500)
    expect(deleteAvatarVersionMock).toHaveBeenCalledWith("viewer-1", "123456789")
  })

  it("restores the default before deleting stored uploads", async () => {
    authenticated()
    const { DELETE } = await import("@/app/api/profile/avatar/route")
    const response = await DELETE()

    expect(response.status).toBe(200)
    expect(updateUserMock).toHaveBeenCalledWith("viewer-1", { image: null })
    expect(deleteAvatarFilesMock).toHaveBeenCalledWith("viewer-1")
    expect(updateUserMock.mock.invocationCallOrder[0]).toBeLessThan(
      deleteAvatarFilesMock.mock.invocationCallOrder[0],
    )
  })

  it("serves only the authenticated user's validated avatar version", async () => {
    authenticated()
    const { GET } = await import("@/app/api/profile/avatar/file/route")
    const response = await GET(
      new Request("http://localhost/api/profile/avatar/file?v=123456789"),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get("Content-Type")).toBe("image/webp")
    expect(readAvatarFileMock).toHaveBeenCalledWith("viewer-1", "123456789")
    expect(Buffer.from(await response.arrayBuffer())).toEqual(
      Buffer.from("stored-avatar"),
    )
  })
})

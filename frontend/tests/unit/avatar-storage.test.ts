import { mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import sharp from "sharp"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  avatarUserDigest,
  deleteAvatarFiles,
  deleteAvatarVersion,
  readAvatarFile,
  resolveAvatarStorageDir,
  validateAvatarUpload,
  writeAvatarFile,
} from "@/lib/avatar/avatar-storage"

vi.mock("server-only", () => ({}))

describe("avatar storage", () => {
  let home: string

  beforeEach(async () => {
    home = await mkdtemp(path.join(tmpdir(), "bioinfoflow-avatar-"))
    process.env.BIOINFOFLOW_HOME = home
  })

  afterEach(async () => {
    delete process.env.BIOINFOFLOW_HOME
    await rm(home, { recursive: true, force: true })
  })

  it("stores avatars beside the Better Auth database", () => {
    expect(resolveAvatarStorageDir()).toBe(
      path.join(home, "state", "auth", "avatars"),
    )
  })

  it("derives a path-safe fixed-length user digest", () => {
    expect(avatarUserDigest("../unsafe/user")).toMatch(/^[a-f0-9]{32}$/)
    expect(avatarUserDigest("../unsafe/user")).toBe(
      avatarUserDigest("../unsafe/user"),
    )
  })

  it("accepts only a normalized 256 by 256 WebP payload", async () => {
    const valid = await sharp({
      create: {
        width: 256,
        height: 256,
        channels: 4,
        background: { r: 42, g: 88, b: 73, alpha: 1 },
      },
    }).webp().toBuffer()

    await expect(
      validateAvatarUpload(new Blob([valid], { type: "image/webp" })),
    ).resolves.toEqual(valid)
    await expect(
      validateAvatarUpload(new Blob(["not-webp"], { type: "image/png" })),
    ).rejects.toThrow("WebP")

    const wrongSize = await sharp({
      create: {
        width: 128,
        height: 128,
        channels: 4,
        background: { r: 42, g: 88, b: 73, alpha: 1 },
      },
    }).webp().toBuffer()
    await expect(
      validateAvatarUpload(new Blob([wrongSize], { type: "image/webp" })),
    ).rejects.toThrow("256")
  })

  it("writes versions atomically and removes superseded files", async () => {
    const first = Buffer.from("first")
    const second = Buffer.from("second")

    await writeAvatarFile("viewer-1", "100", first)
    await writeAvatarFile("viewer-1", "101", second)

    await expect(readAvatarFile("viewer-1", "100")).resolves.toEqual(first)
    await expect(readAvatarFile("viewer-1", "101")).resolves.toEqual(second)

    await deleteAvatarFiles("viewer-1", "101")

    await expect(readAvatarFile("viewer-1", "100")).resolves.toBeNull()
    await expect(readAvatarFile("viewer-1", "101")).resolves.toEqual(second)
  })

  it("can remove one failed version without deleting the previous avatar", async () => {
    await writeAvatarFile("viewer-1", "100", Buffer.from("previous"))
    await writeAvatarFile("viewer-1", "101", Buffer.from("failed"))

    await deleteAvatarVersion("viewer-1", "101")

    await expect(readAvatarFile("viewer-1", "100")).resolves.toEqual(
      Buffer.from("previous"),
    )
    await expect(readAvatarFile("viewer-1", "101")).resolves.toBeNull()
  })

  it("rejects non-numeric versions before accessing the filesystem", async () => {
    await expect(readAvatarFile("viewer-1", "../secret")).resolves.toBeNull()
  })
})

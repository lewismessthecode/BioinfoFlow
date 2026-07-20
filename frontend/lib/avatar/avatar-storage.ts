import "server-only"

import { createHash, randomBytes } from "node:crypto"
import {
  mkdir,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises"
import path from "node:path"
import sharp, { type Metadata } from "sharp"
import { resolveBioinfoflowHome } from "@/lib/auth"

const MAX_STORED_AVATAR_BYTES = 512 * 1024
const AVATAR_VERSION_PATTERN = /^\d{1,20}$/

export function resolveAvatarStorageDir(): string {
  return path.join(resolveBioinfoflowHome(), "state", "auth", "avatars")
}

export function avatarUserDigest(userId: string): string {
  return createHash("sha256").update(userId).digest("hex").slice(0, 32)
}

function avatarFileName(userId: string, version: string): string | null {
  if (!AVATAR_VERSION_PATTERN.test(version)) return null
  return `${avatarUserDigest(userId)}-${version}.webp`
}

function avatarFilePath(userId: string, version: string): string | null {
  const fileName = avatarFileName(userId, version)
  return fileName ? path.join(resolveAvatarStorageDir(), fileName) : null
}

export async function validateAvatarUpload(blob: Blob): Promise<Buffer> {
  if (blob.type !== "image/webp") {
    throw new Error("Avatar upload must be a WebP image.")
  }
  if (blob.size <= 0 || blob.size > MAX_STORED_AVATAR_BYTES) {
    throw new Error("Avatar WebP must be smaller than 512 KiB.")
  }

  const buffer = Buffer.from(await blob.arrayBuffer())
  let metadata: Metadata
  try {
    metadata = await sharp(buffer).metadata()
  } catch {
    throw new Error("Avatar upload is not a valid WebP image.")
  }

  if (metadata.format !== "webp") {
    throw new Error("Avatar upload must be a valid WebP image.")
  }
  if (metadata.width !== 256 || metadata.height !== 256) {
    throw new Error("Avatar WebP must be exactly 256 by 256 pixels.")
  }
  return buffer
}

export async function writeAvatarFile(
  userId: string,
  version: string,
  buffer: Buffer,
): Promise<void> {
  const destination = avatarFilePath(userId, version)
  if (!destination) throw new Error("Invalid avatar version.")

  const directory = resolveAvatarStorageDir()
  await mkdir(directory, { recursive: true, mode: 0o700 })
  const temporary = `${destination}.${randomBytes(6).toString("hex")}.tmp`
  await writeFile(temporary, buffer, { mode: 0o600 })
  try {
    await rename(temporary, destination)
  } catch (error) {
    await rm(temporary, { force: true })
    throw error
  }
}

export async function readAvatarFile(
  userId: string,
  version: string,
): Promise<Buffer | null> {
  const filePath = avatarFilePath(userId, version)
  if (!filePath) return null

  try {
    return await readFile(filePath)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null
    throw error
  }
}

export async function deleteAvatarFiles(
  userId: string,
  keepVersion?: string,
): Promise<void> {
  const directory = resolveAvatarStorageDir()
  const prefix = `${avatarUserDigest(userId)}-`
  let entries: string[]
  try {
    entries = await readdir(directory)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return
    throw error
  }

  await Promise.all(
    entries
      .filter((entry) => {
        if (!entry.startsWith(prefix) || !entry.endsWith(".webp")) return false
        if (!keepVersion) return true
        return entry !== `${prefix}${keepVersion}.webp`
      })
      .map((entry) => rm(path.join(directory, entry), { force: true })),
  )
}

export async function deleteAvatarVersion(
  userId: string,
  version: string,
): Promise<void> {
  const filePath = avatarFilePath(userId, version)
  if (!filePath) return
  await rm(filePath, { force: true })
}

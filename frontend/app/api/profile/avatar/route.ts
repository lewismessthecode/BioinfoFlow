import { headers } from "next/headers"
import { ensureAuthReady, getAuth } from "@/lib/auth"
import {
  deleteAvatarFiles,
  deleteAvatarVersion,
  validateAvatarUpload,
  writeAvatarFile,
} from "@/lib/avatar/avatar-storage"
import {
  findPixelPersona,
  toPixelPersonaReference,
  type PixelPersonaKey,
} from "@/lib/avatar/pixel-personas"

function success(data: unknown) {
  return Response.json({ success: true, data })
}

function failure(message: string, status: number) {
  return Response.json(
    { success: false, error: { message } },
    { status },
  )
}

function isBlobLike(value: unknown): value is Blob {
  return Boolean(
    value &&
      typeof value === "object" &&
      typeof (value as Blob).arrayBuffer === "function" &&
      typeof (value as Blob).type === "string" &&
      typeof (value as Blob).size === "number",
  )
}

async function requireCurrentUser() {
  await ensureAuthReady()
  const auth = await getAuth()
  if (!auth) {
    return {
      ok: false as const,
      response: failure("Authentication is not available.", 404),
    }
  }

  const session = await auth.api.getSession({ headers: await headers() })
  if (!session?.user?.id) {
    return {
      ok: false as const,
      response: failure("Sign in to update your avatar.", 401),
    }
  }

  return {
    ok: true as const,
    userId: session.user.id,
    context: await auth.$context,
  }
}

export async function PATCH(request: Request) {
  const current = await requireCurrentUser()
  if (!current.ok) return current.response

  let body: { avatarKey?: unknown }
  try {
    body = (await request.json()) as { avatarKey?: unknown }
  } catch {
    return failure("Invalid avatar selection.", 400)
  }

  const key = typeof body.avatarKey === "string" ? body.avatarKey : ""
  const persona = findPixelPersona(key)
  if (!persona) {
    return failure("Choose a valid Bioinfoflow avatar.", 400)
  }

  const image = toPixelPersonaReference(persona.key as PixelPersonaKey)
  try {
    await current.context.internalAdapter.updateUser(current.userId, { image })
    await deleteAvatarFiles(current.userId)
    return success({ image })
  } catch {
    return failure("Could not update your avatar.", 500)
  }
}

export async function POST(request: Request) {
  const current = await requireCurrentUser()
  if (!current.ok) return current.response

  let file: Blob
  try {
    const formData = await request.formData()
    const candidate = formData.get("file")
    if (!isBlobLike(candidate)) {
      return failure("Choose an avatar image to upload.", 400)
    }
    file = candidate
  } catch {
    return failure("Invalid avatar upload.", 400)
  }

  let buffer: Buffer
  try {
    buffer = await validateAvatarUpload(file)
  } catch (error) {
    return failure(
      error instanceof Error ? error.message : "Invalid avatar upload.",
      400,
    )
  }

  const version = String(Date.now())
  const image = `/api/profile/avatar/file?v=${version}`
  try {
    await writeAvatarFile(current.userId, version, buffer)
  } catch {
    return failure("Could not store your avatar.", 500)
  }

  try {
    await current.context.internalAdapter.updateUser(current.userId, { image })
  } catch {
    await deleteAvatarVersion(current.userId, version)
    return failure("Could not update your avatar.", 500)
  }

  await deleteAvatarFiles(current.userId, version)
  return success({ image })
}

export async function DELETE() {
  const current = await requireCurrentUser()
  if (!current.ok) return current.response

  try {
    await current.context.internalAdapter.updateUser(current.userId, { image: null })
  } catch {
    return failure("Could not restore your default avatar.", 500)
  }

  await deleteAvatarFiles(current.userId)
  return success({ image: null })
}

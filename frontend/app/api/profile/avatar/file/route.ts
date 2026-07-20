import { headers } from "next/headers"
import { ensureAuthReady, getAuth } from "@/lib/auth"
import { readAvatarFile } from "@/lib/avatar/avatar-storage"

function failure(message: string, status: number) {
  return Response.json(
    { success: false, error: { message } },
    { status },
  )
}

export async function GET(request: Request) {
  await ensureAuthReady()
  const auth = await getAuth()
  if (!auth) {
    return failure("Authentication is not available.", 404)
  }

  const session = await auth.api.getSession({ headers: await headers() })
  if (!session?.user?.id) {
    return failure("Sign in to view this avatar.", 401)
  }

  const version = new URL(request.url).searchParams.get("v") ?? ""
  const avatar = await readAvatarFile(session.user.id, version)
  if (!avatar) {
    return failure("Avatar not found.", 404)
  }

  return new Response(new Uint8Array(avatar), {
    headers: {
      "Content-Type": "image/webp",
      "Cache-Control": "private, max-age=31536000, immutable",
      "X-Content-Type-Options": "nosniff",
    },
  })
}

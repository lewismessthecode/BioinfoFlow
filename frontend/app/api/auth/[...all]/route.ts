import { toNextJsHandler } from "better-auth/next-js"
import { ensureAuthReady, getAuth } from "@/lib/auth"

export const runtime = "nodejs"

async function resolveAuthHandler() {
  const auth = await getAuth()
  if (!auth) {
    return null
  }
  return toNextJsHandler(auth)
}

function disabledAuthResponse() {
  return Response.json(
    {
      success: false,
      error: "Auth is disabled in dev mode.",
    },
    { status: 404 },
  )
}

export async function GET(request: Request) {
  const authHandler = await resolveAuthHandler()
  if (!authHandler) {
    return disabledAuthResponse()
  }
  await ensureAuthReady()
  return authHandler.GET(request)
}

export async function POST(request: Request) {
  const authHandler = await resolveAuthHandler()
  if (!authHandler) {
    return disabledAuthResponse()
  }
  await ensureAuthReady()
  return authHandler.POST(request)
}

export async function PUT(request: Request) {
  const authHandler = await resolveAuthHandler()
  if (!authHandler) {
    return disabledAuthResponse()
  }
  await ensureAuthReady()
  return authHandler.PUT(request)
}

export async function PATCH(request: Request) {
  const authHandler = await resolveAuthHandler()
  if (!authHandler) {
    return disabledAuthResponse()
  }
  await ensureAuthReady()
  return authHandler.PATCH(request)
}

export async function DELETE(request: Request) {
  const authHandler = await resolveAuthHandler()
  if (!authHandler) {
    return disabledAuthResponse()
  }
  await ensureAuthReady()
  return authHandler.DELETE(request)
}

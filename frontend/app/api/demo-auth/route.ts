import { NextRequest, NextResponse } from "next/server"

import {
  DEMO_ACCESS_COOKIE,
  isDemoAuthProvider,
  normalizeDemoNextPath,
} from "@/lib/demo-auth"

export async function GET(request: NextRequest) {
  const action = request.nextUrl.searchParams.get("action")
  const nextPath = normalizeDemoNextPath(
    request.nextUrl.searchParams.get("next"),
  )

  if (action === "logout") {
    const response = NextResponse.redirect(new URL(nextPath, request.url))
    response.cookies.set(DEMO_ACCESS_COOKIE, "", {
      httpOnly: true,
      maxAge: 0,
      path: "/",
      sameSite: "lax",
      secure: request.nextUrl.protocol === "https:",
    })
    return response
  }

  const provider = request.nextUrl.searchParams.get("provider")

  if (!isDemoAuthProvider(provider)) {
    return NextResponse.redirect(new URL("/auth", request.url))
  }

  const response = NextResponse.redirect(new URL(nextPath, request.url))
  response.cookies.set(DEMO_ACCESS_COOKIE, provider, {
    httpOnly: true,
    maxAge: 60 * 60 * 12,
    path: "/",
    sameSite: "lax",
    secure: request.nextUrl.protocol === "https:",
  })
  return response
}

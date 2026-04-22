import { type NextRequest, NextResponse } from "next/server"

import { getServerAuthConfig } from "@/lib/auth-config"

// ---------------------------------------------------------------------------
// Deploy mode — controls which routes are accessible
// ---------------------------------------------------------------------------

const DEPLOY_MODE = process.env.DEPLOY_MODE || "app"

// Paths accessible in demo mode (no backend needed)
const DEMO_PATHS = new Set(["/", "/demo"])
const DEMO_PREFIXES = ["/auth", "/api/auth", "/demo"]

function isDemoAllowed(pathname: string): boolean {
  if (DEMO_PATHS.has(pathname)) return true
  return DEMO_PREFIXES.some((prefix) => pathname.startsWith(prefix))
}

// ---------------------------------------------------------------------------
// Auth — paths that bypass authentication
// ---------------------------------------------------------------------------

const PUBLIC_PATHS = new Set(["/"])
const PUBLIC_PREFIXES = ["/auth", "/api/auth", "/demo"]

function isPublicPath(pathname: string): boolean {
  if (PUBLIC_PATHS.has(pathname)) {
    return true
  }

  return PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix))
}

// ---------------------------------------------------------------------------
// Proxy
// ---------------------------------------------------------------------------

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Demo mode: only allow landing, demo, and auth routes
  if (DEPLOY_MODE === "demo") {
    if (!isDemoAllowed(pathname)) {
      return NextResponse.redirect(new URL("/", request.url))
    }
    // Demo mode still requires auth if configured
    const authConfig = getServerAuthConfig()
    if (!authConfig.authEnabled) {
      return NextResponse.next()
    }
    // Allow public demo paths without auth
    if (isPublicPath(pathname)) {
      return NextResponse.next()
    }
    const sessionToken = request.cookies.get("better-auth.session_token")
    if (!sessionToken?.value) {
      return NextResponse.redirect(new URL("/auth", request.url))
    }
    return NextResponse.next()
  }

  // App mode (default): standard auth flow
  if (!getServerAuthConfig().authEnabled) {
    return NextResponse.next()
  }

  if (isPublicPath(pathname)) {
    return NextResponse.next()
  }

  const sessionToken = request.cookies.get("better-auth.session_token")

  if (!sessionToken?.value) {
    const authUrl = new URL("/auth", request.url)
    return NextResponse.redirect(authUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)"],
}

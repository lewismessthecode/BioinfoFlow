/**
 * Secure cookie helpers.
 *
 * All preference cookies should use these helpers to ensure
 * SameSite and Secure attributes are consistently applied.
 */

export interface CookieOptions {
  maxAge?: number
  path?: string
  secure?: boolean
  sameSite?: "Strict" | "Lax" | "None"
}

/**
 * Build a cookie string with security attributes.
 *
 * Returns the string suitable for assigning to `document.cookie`.
 * By default, applies `SameSite=Lax` and `path=/`.
 * Set `secure: true` when running over HTTPS (production).
 */
export function setSecureCookie(
  name: string,
  value: string,
  options: CookieOptions = {},
): string {
  const {
    maxAge,
    path = "/",
    secure = typeof window !== "undefined" &&
      window.location.protocol === "https:",
    sameSite = "Lax",
  } = options

  const parts = [`${name}=${encodeURIComponent(value)}`, `path=${path}`, `SameSite=${sameSite}`]

  if (maxAge !== undefined) {
    parts.push(`max-age=${maxAge}`)
  }

  if (secure) {
    parts.push("Secure")
  }

  const cookie = parts.join("; ")
  if (typeof document !== "undefined") {
    document.cookie = cookie
  }
  return cookie
}

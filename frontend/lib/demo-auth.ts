import { isDemoDeployment as resolveIsDemoDeployment } from "@/lib/deploy-mode"

export const DEMO_ACCESS_COOKIE = "bioinfoflow_demo_access"

const DEMO_AUTH_PROVIDERS = ["github", "google", "guest"] as const

type DemoAuthProvider = (typeof DEMO_AUTH_PROVIDERS)[number]

export function isDemoDeployment() {
  return resolveIsDemoDeployment()
}

export function isDemoAuthProvider(
  value: string | null | undefined,
): value is DemoAuthProvider {
  return Boolean(value && DEMO_AUTH_PROVIDERS.includes(value as DemoAuthProvider))
}

export function normalizeDemoNextPath(value: string | null | undefined) {
  if (!value) return "/agent"
  if (!value.startsWith("/") || value.startsWith("//")) {
    return "/agent"
  }
  return value
}

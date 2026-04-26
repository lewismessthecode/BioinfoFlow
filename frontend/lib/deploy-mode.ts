export type DeployMode = "app" | "demo"

function normalizeEnvValue(value: string | undefined) {
  const normalized = value?.trim().toLowerCase()
  return normalized && normalized.length > 0 ? normalized : null
}

export function resolveDeployMode(): DeployMode {
  const explicitRuntime = normalizeEnvValue(process.env.APP_RUNTIME)
  if (explicitRuntime === "demo") {
    return "demo"
  }

  const deployMode =
    normalizeEnvValue(process.env.DEPLOY_MODE) ??
    normalizeEnvValue(process.env.NEXT_PUBLIC_DEPLOY_MODE)

  return deployMode === "demo" ? "demo" : "app"
}

export function isDemoDeployment() {
  return resolveDeployMode() === "demo"
}

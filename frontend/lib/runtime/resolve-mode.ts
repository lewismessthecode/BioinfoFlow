import { resolveDeployMode } from "@/lib/deploy-mode"
import type { RuntimeMode } from "./types"

export function resolveRuntimeMode(): RuntimeMode {
  const explicit = process.env.APP_RUNTIME?.trim().toLowerCase()
  if (explicit === "demo") return "demo"
  if (explicit === "live") return "live"

  if (resolveDeployMode() === "demo") return "demo"

  return "live"
}

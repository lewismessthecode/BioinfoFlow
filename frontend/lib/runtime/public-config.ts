const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1"

export type BioinfoflowRuntimeConfig = {
  apiBaseUrl: string
}

declare global {
  interface Window {
    __BIOINFOFLOW_RUNTIME_CONFIG__?: BioinfoflowRuntimeConfig
  }
}

export function serializePublicRuntimeConfig(
  config: BioinfoflowRuntimeConfig,
) {
  const serialized = JSON.stringify(config)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029")

  return `window.__BIOINFOFLOW_RUNTIME_CONFIG__=${serialized};`
}

export function resolvePublicApiBaseUrl() {
  if (typeof window !== "undefined") {
    const runtimeUrl = window.__BIOINFOFLOW_RUNTIME_CONFIG__?.apiBaseUrl?.trim()
    if (runtimeUrl) return runtimeUrl
  }

  return (
    process.env.BIOINFOFLOW_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    DEFAULT_API_BASE_URL
  )
}


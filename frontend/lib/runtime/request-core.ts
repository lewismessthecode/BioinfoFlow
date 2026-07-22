import type { ApiEnvelope, ApiMeta, ApiErrorPayload } from "@/lib/types"

import type {
  RequestParams,
  RuntimeRequestOptions,
  RuntimeRequestResult,
} from "./types"
import { resolvePublicApiBaseUrl } from "./public-config"

export class ApiError extends Error {
  code?: string
  details?: unknown
  status?: number
  meta?: ApiMeta

  constructor(
    message: string,
    options?: {
      code?: string
      details?: unknown
      status?: number
      meta?: ApiMeta
    },
  ) {
    super(message)
    this.name = "ApiError"
    this.code = options?.code
    this.details = options?.details
    this.status = options?.status
    this.meta = options?.meta
  }
}

export function buildLiveApiUrl(path: string, params?: RequestParams) {
  const normalized = path.startsWith("/") ? path : `/${path}`
  const url = new URL(`${resolvePublicApiBaseUrl()}${normalized}`)

  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return
      url.searchParams.set(key, String(value))
    })
  }

  return url.toString()
}

export function buildLiveWebSocketUrl(path: string, params?: RequestParams) {
  const url = new URL(buildLiveApiUrl(path, params))
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return url.toString()
}

async function parseEnvelope<T>(response: Response) {
  const text = await response.text()
  if (!text || !text.trim()) {
    return null as ApiEnvelope<T> | null
  }

  try {
    return JSON.parse(text) as ApiEnvelope<T>
  } catch {
    throw new ApiError("Invalid JSON response", { status: response.status })
  }
}

export async function liveRequest<T>(
  path: string,
  options: RuntimeRequestOptions = {},
): Promise<RuntimeRequestResult<T>> {
  const { params, headers, body, ...init } = options
  const url = buildLiveApiUrl(path, params)
  const isFormData =
    typeof FormData !== "undefined" && body instanceof FormData

  const response = await fetch(url, {
    ...init,
    credentials: "include",
    body,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...headers,
    },
  })

  const envelope = await parseEnvelope<T>(response)

  if (!response.ok) {
    if (envelope && !envelope.success) {
      const errorPayload = envelope.error as ApiErrorPayload
      throw new ApiError(errorPayload?.message || response.statusText, {
        code: errorPayload?.code,
        details: errorPayload?.details,
        status: response.status,
        meta: envelope.meta,
      })
    }
    throw new ApiError(response.statusText || "Request failed", {
      status: response.status,
    })
  }

  if (!envelope) {
    if (response.status === 204) {
      return { data: null as T, meta: undefined }
    }
    throw new ApiError("Empty response", { status: response.status })
  }

  if (!envelope.success) {
    throw new ApiError(envelope.error?.message || "Request failed", {
      code: envelope.error?.code,
      details: envelope.error?.details,
      status: response.status,
      meta: envelope.meta,
    })
  }

  return { data: envelope.data as T, meta: envelope.meta }
}

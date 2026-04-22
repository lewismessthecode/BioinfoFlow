import type { ApiEnvelope, ApiMeta, ApiErrorPayload } from "./types"

const DEFAULT_BASE_URL = "http://localhost:8000/api/v1"
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_BASE_URL

type RequestOptions = RequestInit & {
  params?: Record<string, string | number | boolean | null | undefined>
}

export class ApiError extends Error {
  code?: string
  details?: unknown
  status?: number
  meta?: ApiMeta

  constructor(message: string, options?: { code?: string; details?: unknown; status?: number; meta?: ApiMeta }) {
    super(message)
    this.name = "ApiError"
    this.code = options?.code
    this.details = options?.details
    this.status = options?.status
    this.meta = options?.meta
  }
}

export const buildApiUrl = (path: string, params?: RequestOptions["params"]) => {
  const normalized = path.startsWith("/") ? path : `/${path}`
  const url = new URL(`${API_BASE_URL}${normalized}`)

  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return
      url.searchParams.set(key, String(value))
    })
  }

  return url.toString()
}

export const buildWebSocketUrl = (
  path: string,
  params?: RequestOptions["params"]
) => {
  const url = new URL(buildApiUrl(path, params))
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return url.toString()
}

const parseEnvelope = async <T>(response: Response) => {
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

export const apiRequest = async <T>(path: string, options: RequestOptions = {}) => {
  const { params, headers, body, ...init } = options
  const url = buildApiUrl(path, params)
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData

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
    throw new ApiError(response.statusText || "Request failed", { status: response.status })
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

/** Extract a user-facing message from an unknown caught error. */
export const getApiErrorMessage = (error: unknown, fallback: string): string =>
  error instanceof ApiError ? error.message : fallback

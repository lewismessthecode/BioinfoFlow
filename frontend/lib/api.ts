import { getCurrentRuntime } from "@/lib/runtime"
import { ApiError } from "@/lib/runtime/request-core"
import type { RuntimeRequestOptions } from "@/lib/runtime"

type RequestOptions = RuntimeRequestOptions

export { ApiError }

export const buildApiUrl = (
  path: string,
  params?: RequestOptions["params"],
) => getCurrentRuntime().buildApiUrl(path, params)

export const buildWebSocketUrl = (
  path: string,
  params?: RequestOptions["params"],
) => getCurrentRuntime().buildWebSocketUrl(path, params)

export const apiRequest = async <T>(
  path: string,
  options: RequestOptions = {},
) => getCurrentRuntime().request<T>(path, options)

/** Extract a user-facing message from an unknown caught error. */
export const getApiErrorMessage = (error: unknown, fallback: string): string =>
  error instanceof ApiError ? error.message : fallback

import { renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { FormSpec } from "@/lib/form-spec"

const { apiRequestMock, getApiErrorMessageMock } = vi.hoisted(() => ({
  apiRequestMock: vi.fn(),
  getApiErrorMessageMock: vi.fn(),
}))

vi.mock("@/lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
  getApiErrorMessage: (...args: unknown[]) => getApiErrorMessageMock(...args),
}))

import { useFormSpec } from "@/hooks/use-form-spec"

describe("useFormSpec", () => {
  beforeEach(() => {
    apiRequestMock.mockReset()
    getApiErrorMessageMock.mockReset()
    getApiErrorMessageMock.mockReturnValue("Failed to load form")
  })

  it("stays idle and skips fetching when no workflow id is provided", () => {
    const { result } = renderHook(() => useFormSpec(null))

    expect(result.current).toEqual({ status: "idle" })
    expect(apiRequestMock).not.toHaveBeenCalled()
  })

  it("loads and returns the workflow form spec", async () => {
    const spec = {
      version: 1,
      fields: [{ id: "reads", label: "Reads", kind: "file", required: true }],
    } satisfies FormSpec
    apiRequestMock.mockResolvedValue({ data: spec })

    const { result } = renderHook(() => useFormSpec("workflow-1"))

    expect(result.current).toEqual({ status: "loading" })

    await waitFor(() =>
      expect(result.current).toEqual({ status: "ready", spec })
    )
    expect(apiRequestMock).toHaveBeenCalledWith("/workflows/workflow-1/form-spec")
  })

  it("surfaces a formatted error when loading fails", async () => {
    const error = new Error("network exploded")
    apiRequestMock.mockRejectedValue(error)

    const { result } = renderHook(() => useFormSpec("workflow-2"))

    await waitFor(() =>
      expect(result.current).toEqual({
        status: "error",
        message: "Failed to load form",
      })
    )
    expect(getApiErrorMessageMock).toHaveBeenCalledWith(
      error,
      "Failed to load workflow form"
    )
  })
})

import { StrictMode, type PropsWithChildren } from "react"
import { renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const apiRequestMock = vi.fn()

vi.mock("@/lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
}))

import { useFirstRun } from "@/hooks/use-first-run"
import { bootstrapFirstRun } from "@/lib/first-run"

const bootstrapResult = {
  ready: true,
  created: true,
  demo_project_id: "project-demo",
  workflow_id: "workflow-demo",
  starter_context: {
    project_id: "project-demo",
    workflow: {
      id: "workflow-demo",
      name: "bioinfoflow-quickstart",
      version: "1.0.0",
      source: "local",
      engine: "wdl",
      scope: "project",
      project_id: "project-demo",
    },
    values: {
      samples_tsv: "asset://project/samples.tsv",
      sample_a_fastq: "asset://project/sample-a.fastq",
      sample_b_fastq: "asset://project/sample-b.fastq",
    },
  },
} as const

describe("first-run bootstrap", () => {
  beforeEach(() => {
    apiRequestMock.mockReset()
    apiRequestMock.mockResolvedValue({ data: bootstrapResult })
  })

  it("posts to the current-user bootstrap endpoint", async () => {
    await expect(bootstrapFirstRun()).resolves.toEqual(bootstrapResult)
    expect(apiRequestMock).toHaveBeenCalledWith("/first-run/bootstrap", {
      method: "POST",
    })
  })

  it("loads the bootstrap once when enabled", async () => {
    const { result, rerender } = renderHook(
      ({ enabled }) => useFirstRun(enabled),
      { initialProps: { enabled: true } },
    )

    await waitFor(() => expect(result.current.data).toEqual(bootstrapResult))
    rerender({ enabled: true })

    expect(apiRequestMock).toHaveBeenCalledTimes(1)
    expect(result.current.isLoading).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it("retains the single bootstrap result across Strict Mode effect cleanup", async () => {
    let resolveRequest!: (value: { data: typeof bootstrapResult }) => void
    apiRequestMock.mockReturnValue(
      new Promise<{ data: typeof bootstrapResult }>((resolve) => {
        resolveRequest = resolve
      }),
    )

    const { result } = renderHook(() => useFirstRun(true), {
      wrapper: ({ children }: PropsWithChildren) => (
        <StrictMode>{children}</StrictMode>
      ),
    })

    expect(apiRequestMock).toHaveBeenCalledTimes(1)
    resolveRequest({ data: bootstrapResult })

    await waitFor(() => expect(result.current.data).toEqual(bootstrapResult))
  })

  it("reattaches to an in-flight bootstrap after effect cleanup", async () => {
    let resolveRequest!: (value: { data: typeof bootstrapResult }) => void
    apiRequestMock.mockReturnValue(
      new Promise<{ data: typeof bootstrapResult }>((resolve) => {
        resolveRequest = resolve
      }),
    )

    const { result, rerender } = renderHook(
      ({ enabled }) => useFirstRun(enabled),
      { initialProps: { enabled: true } },
    )
    rerender({ enabled: false })
    rerender({ enabled: true })
    resolveRequest({ data: bootstrapResult })

    await waitFor(() => expect(result.current.data).toEqual(bootstrapResult))
    expect(apiRequestMock).toHaveBeenCalledTimes(1)
  })

  it("retries a rejected bootstrap after the route is disabled and re-enabled", async () => {
    apiRequestMock
      .mockRejectedValueOnce(new Error("bootstrap unavailable"))
      .mockResolvedValueOnce({ data: bootstrapResult })

    const { result, rerender } = renderHook(
      ({ enabled }) => useFirstRun(enabled),
      { initialProps: { enabled: true } },
    )

    await waitFor(() =>
      expect(result.current.error).toEqual(new Error("bootstrap unavailable")),
    )
    rerender({ enabled: false })
    rerender({ enabled: true })

    await waitFor(() => expect(result.current.data).toEqual(bootstrapResult))
    expect(apiRequestMock).toHaveBeenCalledTimes(2)
    expect(result.current.error).toBeNull()
  })

  it("does not bootstrap outside the enabled route", () => {
    const { result } = renderHook(() => useFirstRun(false))

    expect(apiRequestMock).not.toHaveBeenCalled()
    expect(result.current.data).toBeNull()
    expect(result.current.isLoading).toBe(false)
  })
})

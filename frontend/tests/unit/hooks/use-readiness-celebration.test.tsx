import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useReadinessCelebration } from "@/hooks/use-readiness-celebration"
import { apiRequest } from "@/lib/api"
import { celebrateReadinessTransitions } from "@/lib/celebrations"
import { emitReadinessRefresh } from "@/lib/readiness-events"

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

vi.mock("@/lib/celebrations", async () => {
  const actual = await vi.importActual<typeof import("@/lib/celebrations")>(
    "@/lib/celebrations",
  )
  return {
    ...actual,
    celebrateReadinessTransitions: vi.fn(),
  }
})

describe("useReadinessCelebration", () => {
  const apiRequestMock = vi.mocked(apiRequest)
  const celebrateReadinessTransitionsMock = vi.mocked(celebrateReadinessTransitions)

  beforeEach(() => {
    apiRequestMock.mockReset()
    celebrateReadinessTransitionsMock.mockReset()
  })

  it("refreshes readiness after workspace actions and compares against the previous snapshot", async () => {
    apiRequestMock
      .mockResolvedValueOnce({
        data: {
          severity: "blocked",
          checks: [
            {
              id: "project",
              status: "fail",
              severity: "blocking",
              label: "Create a project",
            },
          ],
        },
        meta: undefined,
      })
      .mockResolvedValueOnce({
        data: {
          severity: "ready",
          checks: [
            {
              id: "project",
              status: "pass",
              severity: "blocking",
              label: "Create a project",
            },
          ],
        },
        meta: undefined,
      })

    renderHook(() => useReadinessCelebration())

    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledTimes(1))
    expect(celebrateReadinessTransitionsMock).toHaveBeenLastCalledWith(
      null,
      expect.arrayContaining([expect.objectContaining({ id: "project", status: "fail" })]),
    )

    act(() => {
      emitReadinessRefresh("project-created")
    })

    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledTimes(2))
    expect(celebrateReadinessTransitionsMock).toHaveBeenLastCalledWith(
      [{ id: "project", status: "fail" }],
      expect.arrayContaining([expect.objectContaining({ id: "project", status: "pass" })]),
    )
  })
})

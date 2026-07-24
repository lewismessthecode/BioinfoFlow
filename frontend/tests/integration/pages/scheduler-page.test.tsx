import { screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import SchedulerPage from "@/app/(app)/scheduler/page"
import { apiRequest } from "@/lib/api"
import { renderAppPage } from "@/tests/app-test-utils"

const toastErrorMock = vi.hoisted(() => vi.fn())

const translationMocks = new Map<
  string,
  (key: string, values?: Record<string, unknown>) => string
>()

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => {
    if (!translationMocks.has(namespace)) {
      translationMocks.set(
        namespace,
        (key: string, values?: Record<string, unknown>) => {
          const suffix = values
            ? Object.values(values)
                .filter((value) => value !== undefined && value !== null)
                .join(":")
            : ""
          return suffix ? `${namespace}.${key}:${suffix}` : `${namespace}.${key}`
        }
      )
    }
    return translationMocks.get(namespace)!
  },
}))

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
  },
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

// The real hook opens an EventSource, which jsdom doesn't provide.
// Integration tests only care that the simplified scheduler chrome renders.
vi.mock("@/hooks/use-resource-stream", () => ({
  useResourceStream: () => ({
    connectionState: "disconnected",
    frame: null,
    samples: [],
    events: [],
  }),
}))

describe("SchedulerPage", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  beforeEach(() => {
    apiRequestMock.mockReset()
    toastErrorMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("renders an operational scheduler dashboard when persistent scheduling is active", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/scheduler/status") {
        return {
          data: {
            mode: "persistent",
            effective_mode: "persistent",
            scheduler_available: true,
            resource_monitoring_enabled: true,
            workers: 4,
            queue_depth: 7,
            states: {
              queued: 2,
              dispatched: 1,
              completed: 3,
              failed: 1,
              cancelled: 0,
            },
            total_slots: 4,
            used_slots: 1,
            available_slots: 3,
            active_runs: [
              {
                run_id: "run_cf98a16392500148e90ae91cc55d1db",
                workflow_name: "rnaseq_quant",
                weight: 1,
              },
            ],
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<SchedulerPage />)

    await waitFor(() => {
      expect(screen.getByText("2")).toBeInTheDocument()
      expect(screen.getByText("3")).toBeInTheDocument()
      expect(screen.getByText("7")).toBeInTheDocument()
      expect(screen.getByText("4")).toBeInTheDocument()
      expect(screen.getAllByText("1")).toHaveLength(2)
      expect(screen.getByText("scheduler.status.activeTitle")).toBeInTheDocument()
      expect(screen.getByText("scheduler.status.activeBody")).toBeInTheDocument()
      // The live monitor waits for the first resource sample before showing pressure.
      expect(screen.getByText("scheduler.resourceSnapshotPending")).toBeInTheDocument()
      expect(screen.getByText("scheduler.activeRuns.title")).toBeInTheDocument()
      expect(screen.getByText("scheduler.advanced.button")).toBeInTheDocument()
      expect(screen.getByText("scheduler.activeRuns.cpuShare")).toBeInTheDocument()
      expect(screen.getByText("rnaseq_quant")).toBeInTheDocument()
      expect(screen.getByText(/UTC$/)).toBeInTheDocument()
    })
  })

  it("explains fallback when persistent mode is configured but scheduler is unavailable", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/scheduler/status") {
        return {
          data: {
            mode: "persistent",
            effective_mode: "legacy",
            scheduler_available: false,
            resource_monitoring_enabled: false,
            workers: 0,
            queue_depth: 0,
            states: {
              queued: 0,
              dispatched: 0,
              completed: 0,
              failed: 0,
              cancelled: 0,
            },
            total_slots: 0,
            used_slots: 0,
            available_slots: 0,
            active_runs: [],
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<SchedulerPage />)

    await waitFor(() => {
      expect(screen.getByText("scheduler.status.fallbackTitle")).toBeInTheDocument()
      expect(screen.getByText("scheduler.status.fallbackBody")).toBeInTheDocument()
      // Fallback mode should not present missing resource samples as healthy capacity.
      expect(screen.getByText("scheduler.resourcesUnavailable")).toBeInTheDocument()
    })
  })
})

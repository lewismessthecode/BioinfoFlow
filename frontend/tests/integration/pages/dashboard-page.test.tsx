import { screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import DashboardPage from "@/app/(app)/dashboard/page"
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

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string
    children: React.ReactNode
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
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

vi.mock("@/lib/auth-client", () => ({
  authClient: {
    useSession: () => ({
      data: {
        user: {
          name: "Lewis Liu",
        },
      },
    }),
  },
}))

vi.mock("@/app/(app)/dashboard/components/dashboard-skeleton", () => ({
  DashboardSkeleton: () => <div data-testid="dashboard-skeleton" />,
}))

describe("DashboardPage", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  beforeEach(() => {
    apiRequestMock.mockReset()
    toastErrorMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("links runs and workflows stat cards to their global views", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/stats") {
        return {
          data: {
            runs: {
              total: 14,
              running: 0,
              completed: 14,
              failed: 0,
              queued: 0,
              pending: 0,
              cancelled: 0,
            },
            workflows: {
              total: 16,
            },
            images: {
              total: 12,
              local: 12,
              remote: 0,
              pulling: 0,
            },
            projects: {
              total: 3,
            },
            recent_runs: [],
          },
          meta: undefined,
        }
      }
      if (path === "/system/health") {
        return {
          data: {
            status: "healthy",
            docker: { available: true, nvidia_runtime: false },
            gpu: { available: false, parabricks_compatible: false },
            parabricks: { image_available: false, image_name: null },
          },
          meta: undefined,
        }
      }
      if (path === "/system/gpu") {
        return {
          data: {
            available: false,
            parabricks_compatible: false,
            gpus: [],
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<DashboardPage />)

    const runsCard = await screen.findByRole("link", { name: /dashboard\.runs/i })
    const workflowsCard = screen.getByRole("link", { name: /dashboard\.workflows/i })

    expect(runsCard).toHaveAttribute("href", "/runs?scope=all")
    expect(workflowsCard).toHaveAttribute("href", "/workflows?scope=hub")
  })

  it("stretches each stat card to the full grid row height", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/stats") {
        return {
          data: {
            runs: {
              total: 20,
              running: 0,
              completed: 20,
              failed: 0,
              queued: 0,
              pending: 0,
              cancelled: 0,
            },
            workflows: {
              total: 16,
            },
            images: {
              total: 12,
              local: 12,
              remote: 0,
              pulling: 0,
            },
            projects: {
              total: 3,
            },
            recent_runs: [],
          },
          meta: undefined,
        }
      }
      if (path === "/system/health") {
        return {
          data: {
            status: "healthy",
            docker: { available: true, nvidia_runtime: false },
            gpu: { available: false, parabricks_compatible: false },
            parabricks: { image_available: false, image_name: null },
          },
          meta: undefined,
        }
      }
      if (path === "/system/gpu") {
        return {
          data: {
            available: false,
            parabricks_compatible: false,
            gpus: [],
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<DashboardPage />)

    const statCardLinks = [
      await screen.findByRole("link", { name: /dashboard\.runs/i }),
      screen.getByRole("link", { name: /dashboard\.workflows/i }),
      screen.getByRole("link", { name: /dashboard\.images/i }),
      screen.getByRole("link", { name: /dashboard\.projects/i }),
    ]

    for (const cardLink of statCardLinks) {
      expect(cardLink).toHaveClass("h-full")
      expect(cardLink.firstElementChild).toHaveClass("h-full")
    }
  })
})

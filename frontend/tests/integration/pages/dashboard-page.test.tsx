import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
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

  it("surfaces readiness guidance when first-run setup is blocked", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/stats") {
        return {
          data: {
            runs: {
              total: 0,
              running: 0,
              completed: 0,
              failed: 0,
              queued: 0,
              pending: 0,
              cancelled: 0,
            },
            workflows: { total: 0 },
            images: { total: 0, local: 0, remote: 0, pulling: 0 },
            projects: { total: 0 },
            recent_runs: [],
          },
          meta: undefined,
        }
      }
      if (path === "/system/health") {
        return {
          data: {
            status: "healthy",
            docker: { available: false, nvidia_runtime: false },
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
      if (path === "/system/readiness") {
        return {
          data: {
            severity: "blocked",
            next_action: {
              label: "Add an AI provider key",
              href: "/settings",
            },
            checks: [
              {
                id: "provider_key",
                label: "AI provider key",
                status: "fail",
                severity: "blocking",
                detail: "No provider key configured",
                hint: "Set one provider key before first run.",
                action_label: "Add an AI provider key",
                action_href: "/settings",
              },
              {
                id: "gpu",
                label: "GPU",
                status: "warn",
                severity: "optional",
                detail: "No GPU detected; CPU workflows can still run",
                hint: "Install GPU drivers only when a workflow needs acceleration.",
              },
            ],
            summary: {
              provider_key_configured: false,
              projects: 0,
              workflows: 0,
              workflow_bindings: 0,
            },
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<DashboardPage />)

    const user = userEvent.setup()
    const trigger = await screen.findByRole("button", {
      name: "dashboard.readiness.trigger",
    })

    expect(trigger).toHaveTextContent("dashboard.readiness.title")
    expect(trigger).toHaveTextContent("dashboard.readiness.triggerSummary:0:2")

    await user.click(trigger)

    expect(screen.getByRole("dialog", { name: "dashboard.readiness.drawerTitle" })).toBeInTheDocument()
    expect(screen.getByText("dashboard.readiness.progress:0:2")).toBeInTheDocument()
    expect(screen.getByText("dashboard.readiness.blockers")).toBeInTheDocument()
    expect(screen.getByText("dashboard.readiness.optional")).toBeInTheDocument()
    expect(screen.getByText("AI provider key")).toBeInTheDocument()
    expect(screen.getByText("GPU")).toBeInTheDocument()
    expect(screen.getAllByRole("link", { name: "Add an AI provider key" })[0]).toHaveAttribute(
      "href",
      "/settings",
    )
  })
})

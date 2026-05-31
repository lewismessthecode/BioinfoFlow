import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { ReadinessStatus } from "@/app/(app)/dashboard/components/dashboard-types"
import { ReadinessCenter } from "@/app/(app)/dashboard/components/readiness-center"

const openCreateProjectDialogMock = vi.fn()
const onRefreshMock = vi.fn()

vi.mock("next/link", () => ({
  default: ({ children, href, className }: { children: React.ReactNode; href: string; className?: string }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
    const copy: Record<string, string> = {
      "readiness.title": "First-run readiness",
      "readiness.trigger": "Open readiness checklist",
      "readiness.triggerSummary": `${values?.completed ?? 0}/${values?.total ?? 0} ready`,
      "readiness.requiredRemaining": `${values?.count ?? 0} required remaining`,
      "readiness.optionalWarnings": `${values?.count ?? 0} optional warnings`,
      "readiness.drawerTitle": "Readiness checklist",
      "readiness.drawerDescription": "Complete each item before the first run.",
      "readiness.progress": `${values?.completed ?? 0} of ${values?.total ?? 0} checks ready`,
      "readiness.blockers": "Required before first run",
      "readiness.optional": "Optional checks",
      "readiness.completed": "Already ready",
      "readiness.refresh": "Refresh status",
      "readiness.completedLabel": `Completed: ${values?.label ?? ""}`,
      "readiness.status.pass": "Pass",
      "readiness.status.fail": "Fix",
      "readiness.status.warn": "Warn",
      "readiness.status.skip": "Skip",
    }

    return copy[key] ?? key
  },
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  useOptionalWorkspaceShell: () => ({
    openCreateProjectDialog: openCreateProjectDialogMock,
  }),
}))

vi.mock("@/lib/celebrations", async () => {
  const actual = await vi.importActual<typeof import("@/lib/celebrations")>("@/lib/celebrations")
  return {
    ...actual,
    celebrateReadinessTransitions: vi.fn(),
  }
})

function blockedReadiness(): ReadinessStatus {
  return {
    severity: "blocked",
    next_action: {
      label: "Add an AI provider key",
      href: "/settings",
    },
    checks: [
      {
        id: "backend",
        label: "Backend API",
        status: "pass",
        severity: "info",
        detail: "Backend is responding",
      },
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
        id: "docker",
        label: "Docker",
        status: "pass",
        severity: "blocking",
        detail: "Docker is available",
        action_label: "Open image inventory",
        action_href: "/images",
      },
      {
        id: "scheduler",
        label: "Scheduler",
        status: "pass",
        severity: "blocking",
        detail: "Scheduler is active",
        action_label: "Open scheduler",
        action_href: "/scheduler",
      },
      {
        id: "gpu",
        label: "GPU",
        status: "warn",
        severity: "optional",
        detail: "NVIDIA runtime is configured, but GPU details are unavailable.",
        hint: "CPU workflows can still run.",
        action_label: "Open resource monitor",
        action_href: "/scheduler",
      },
      {
        id: "project",
        label: "Project",
        status: "fail",
        severity: "blocking",
        detail: "No project exists yet",
        hint: "Create a project before launching the first run.",
        action_label: "Create a project",
        action_href: "/dashboard",
      },
      {
        id: "workflow_registry",
        label: "Workflow registry",
        status: "pass",
        severity: "blocking",
        detail: "1 workflow registered",
        action_label: "Open workflow hub",
        action_href: "/workflows?scope=hub",
      },
      {
        id: "workflow_binding",
        label: "Project workflow binding",
        status: "fail",
        severity: "blocking",
        detail: "No workflow is enabled for a project yet",
        action_label: "Enable a workflow",
        action_href: "/workflows?scope=hub",
      },
    ],
    summary: {},
  }
}

describe("ReadinessCenter", () => {
  beforeEach(() => {
    openCreateProjectDialogMock.mockReset()
    onRefreshMock.mockReset()
  })

  it("opens a right-side checklist that makes progress counts explainable", async () => {
    const user = userEvent.setup()

    render(<ReadinessCenter readiness={blockedReadiness()} onRefresh={onRefreshMock} />)

    expect(screen.getByRole("button", { name: /open readiness checklist/i })).toHaveTextContent("4/8 ready")

    await user.click(screen.getByRole("button", { name: /open readiness checklist/i }))

    expect(screen.getByRole("dialog", { name: "Readiness checklist" })).toBeInTheDocument()
    expect(screen.getByText("4 of 8 checks ready")).toBeInTheDocument()

    for (const label of [
      "Backend API",
      "AI provider key",
      "Docker",
      "Scheduler",
      "GPU",
      "Project",
      "Workflow registry",
      "Project workflow binding",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it("mutes completed checklist rows with a strikethrough instead of hiding them", async () => {
    const user = userEvent.setup()

    render(<ReadinessCenter readiness={blockedReadiness()} onRefresh={onRefreshMock} />)

    await user.click(screen.getByRole("button", { name: /open readiness checklist/i }))

    const backendRow = screen.getByTestId("readiness-check-backend")
    expect(backendRow).toHaveAttribute("aria-label", "Completed: Backend API")
    expect(backendRow).toHaveClass("text-muted-foreground")
    expect(screen.getByText("Backend API")).toHaveClass("line-through")
  })

  it("routes setup actions to existing setup surfaces and opens the project dialog in place", async () => {
    const user = userEvent.setup()

    render(<ReadinessCenter readiness={blockedReadiness()} onRefresh={onRefreshMock} />)

    await user.click(screen.getByRole("button", { name: /open readiness checklist/i }))

    expect(screen.getByRole("link", { name: /add an ai provider key/i })).toHaveAttribute("href", "/settings")
    expect(screen.getByRole("link", { name: /enable a workflow/i })).toHaveAttribute("href", "/workflows?scope=hub")
    expect(screen.getByRole("link", { name: /open resource monitor/i })).toHaveAttribute("href", "/scheduler")

    await user.click(screen.getByRole("button", { name: /create a project/i }))

    expect(openCreateProjectDialogMock).toHaveBeenCalledTimes(1)
  })
})

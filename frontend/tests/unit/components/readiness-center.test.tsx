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
      "readiness.checks.backend.label": "Backend API",
      "readiness.checks.backend.detail.pass": "Backend is responding",
      "readiness.checks.provider_key.label": "AI provider key",
      "readiness.checks.provider_key.action": "Add an AI provider key",
      "readiness.checks.provider_key.detail.pass": "Provider key configured",
      "readiness.checks.provider_key.detail.fail": "No provider key configured",
      "readiness.checks.docker.label": "Docker",
      "readiness.checks.docker.action": "Open image inventory",
      "readiness.checks.docker.detail.pass": "Docker is available",
      "readiness.checks.docker.detail.fail": "Docker is unavailable",
      "readiness.checks.scheduler.label": "Scheduler",
      "readiness.checks.scheduler.action": "Open scheduler",
      "readiness.checks.scheduler.detail.pass": "Scheduler is active",
      "readiness.checks.scheduler.detail.fail": "Scheduler is unavailable",
      "readiness.checks.gpu.label": "GPU",
      "readiness.checks.gpu.action": "Open resource monitor",
      "readiness.checks.gpu.detail.ready": `GPU ready:${values?.names ?? ""}`,
      "readiness.checks.gpu.detail.visible": `GPU visible:${values?.count ?? 0}:${values?.names ?? ""}`,
      "readiness.checks.gpu.detail.runtimeHidden": "Runtime visible but backend hidden",
      "readiness.checks.gpu.detail.hostOnly": "Host has GPU tooling",
      "readiness.checks.gpu.detail.error": `GPU error:${values?.error ?? ""}`,
      "readiness.checks.gpu.detail.cpuOnly": "CPU only",
      "readiness.checks.project.label": "Project",
      "readiness.checks.project.action": "Create a project",
      "readiness.checks.project.detail.pass": `${values?.count ?? 0} project(s) exist`,
      "readiness.checks.project.detail.fail": "No project exists yet",
      "readiness.checks.workflow_registry.label": "Workflow registry",
      "readiness.checks.workflow_registry.action": "Open workflow hub",
      "readiness.checks.workflow_registry.detail.pass": `${values?.count ?? 0} workflow(s) registered`,
      "readiness.checks.workflow_registry.detail.fail": "No workflows are registered yet",
      "readiness.checks.workflow_binding.label": "Project workflow binding",
      "readiness.checks.workflow_binding.action": "Enable a workflow",
      "readiness.checks.workflow_binding.detail.pass": `${values?.count ?? 0} workflow binding(s) exist`,
      "readiness.checks.workflow_binding.detail.fail": "No workflow is enabled for a project yet",
    }

    return copy[key] ?? key
  },
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  useOptionalWorkspaceShell: () => ({
    openCreateProjectDialog: openCreateProjectDialogMock,
  }),
}))

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
        status: "pass",
        severity: "info",
        facts: { available: true },
      },
      {
        id: "provider_key",
        status: "fail",
        severity: "blocking",
        facts: { configured: false },
        action: { kind: "route", href: "/settings" },
      },
      {
        id: "docker",
        status: "pass",
        severity: "blocking",
        facts: { available: true },
        action: { kind: "route", href: "/images" },
      },
      {
        id: "scheduler",
        status: "pass",
        severity: "blocking",
        facts: { available: true },
        action: { kind: "route", href: "/scheduler" },
      },
      {
        id: "gpu",
        status: "warn",
        severity: "optional",
        facts: {
          docker_nvidia_runtime: true,
          runtime_visible_to_backend: false,
          gpu_count: 0,
          gpu_names: [],
        },
        action: { kind: "route", href: "/scheduler" },
      },
      {
        id: "project",
        status: "fail",
        severity: "blocking",
        facts: { count: 0 },
        action: { kind: "dialog", dialog: "create_project" },
      },
      {
        id: "workflow_registry",
        status: "pass",
        severity: "blocking",
        facts: { count: 1 },
        action: { kind: "route", href: "/workflows?scope=hub" },
      },
      {
        id: "workflow_binding",
        status: "fail",
        severity: "blocking",
        facts: { count: 0 },
        action: { kind: "route", href: "/workflows?scope=hub" },
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

    expect(screen.getByRole("button", { name: /open readiness checklist/i })).toHaveTextContent("3/6 ready")

    await user.click(screen.getByRole("button", { name: /open readiness checklist/i }))

    expect(screen.getByRole("dialog", { name: "Readiness checklist" })).toBeInTheDocument()
    expect(screen.getByText("3 of 6 checks ready")).toBeInTheDocument()

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

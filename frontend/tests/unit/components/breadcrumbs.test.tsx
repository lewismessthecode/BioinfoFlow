import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { BreadcrumbProvider } from "@/components/bioinfoflow/breadcrumb-context"
import { Breadcrumbs } from "@/components/bioinfoflow/breadcrumbs"
import { useSetBreadcrumbDetail } from "@/hooks/use-set-breadcrumb-detail"

let pathname = "/runs/run-123"

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      runs: "Runs",
      workflows: "Workflows",
      dashboard: "Dashboard",
      agent: "Agent",
    }
    return labels[key] ?? key
  },
}))

function BreadcrumbDetailSetter({ label }: { label: string }) {
  useSetBreadcrumbDetail(label)
  return null
}

describe("Breadcrumbs", () => {
  it("shows detail labels on deep links even before project context is loaded", () => {
    pathname = "/runs/run-123"

    render(
      <BreadcrumbProvider>
        <BreadcrumbDetailSetter label="run-123" />
        <Breadcrumbs />
      </BreadcrumbProvider>
    )

    expect(screen.getByText("Runs")).toBeInTheDocument()
    expect(screen.getByText("run-123")).toBeInTheDocument()
  })

})

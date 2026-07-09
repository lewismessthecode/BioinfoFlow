import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}))

import { WorkflowCardBase } from "@/app/(app)/workflows/components/workflow-card-base"

describe("WorkflowCardBase", () => {
  it("uses the shared app icon primitive for the quiet workflow tile", () => {
    const { container } = render(
      <WorkflowCardBase
        displayName="flaky-retry-mini"
        menuItems={<div>menu</div>}
        actions={<button type="button">Run</button>}
      >
        <div>Body</div>
      </WorkflowCardBase>,
    )

    expect(container.querySelector("[data-slot='app-icon']")).not.toBeNull()
    expect(container.querySelector(".quiet-card-icon-shell")).not.toBeNull()
  })

  it("keeps long workflow names from covering the actions menu", () => {
    render(
      <WorkflowCardBase
        displayName="parabricks_container_smoke_with_a_very_long_identifier"
        nameWrapper={(children) => <div>{children}</div>}
        menuItems={<div>menu</div>}
        actions={<button type="button">Run</button>}
      />,
    )

    const title = document.querySelector("h3")
    expect(title?.className).toContain("min-w-0")
    expect(title?.closest(".min-w-0.flex-1")).not.toBeNull()
    expect(document.querySelector("button[aria-label='actions']")?.className).toContain("shrink-0")
  })

  it("renders through the shared browse-card shell without changing actions", () => {
    const { container } = render(
      <WorkflowCardBase
        displayName="rnaseq-quant"
        estimatedTime="8m"
        menuItems={<button type="button">Details</button>}
        actions={<button type="button">Run</button>}
      >
        <div>WDL 1.0</div>
      </WorkflowCardBase>,
    )

    expect(container.querySelector("[data-slot='browse-card']")).not.toBeNull()
    expect(container.querySelector("[data-slot='browse-card-actions']")).not.toBeNull()
    expect(container.textContent).toContain("8m")
    expect(container.textContent).toContain("Run")
  })
})

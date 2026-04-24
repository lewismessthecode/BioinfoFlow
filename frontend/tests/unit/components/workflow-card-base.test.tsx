import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}))

import { WorkflowCardBase } from "@/app/(app)/workflows/components/workflow-card-base"

describe("WorkflowCardBase", () => {
  it("uses a flow-oriented lucide glyph for the quiet workflow tile", () => {
    const { container } = render(
      <WorkflowCardBase
        displayName="flaky-retry-mini"
        menuItems={<div>menu</div>}
        actions={<button type="button">Run</button>}
      >
        <div>Body</div>
      </WorkflowCardBase>,
    )

    expect(container.querySelector("svg.lucide-workflow")).not.toBeNull()
  })
})

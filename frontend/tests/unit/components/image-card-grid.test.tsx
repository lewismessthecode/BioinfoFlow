import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ImageCardsGrid } from "@/app/(app)/images/components/image-views"
import type { DockerImage } from "@/lib/types"

const image: DockerImage = {
  id: "img-1",
  name: "pancancer-core-callers",
  tag: "PHASE03-SCAFFOLD",
  full_name: "pancancer-core-callers:PHASE03-SCAFFOLD",
  status: "local",
  registry: "ghcr.io",
  size_bytes: 139 * 1024 * 1024,
}

describe("ImageCardsGrid", () => {
  it("renders local status as a neutral metadata pill while keeping the quieter package glyph", () => {
    const { container } = render(
      <ImageCardsGrid
        images={[image]}
        tImages={(key) => key}
        tCommon={(key) => key}
        onPull={vi.fn()}
        onViewDetails={vi.fn()}
        onCopyName={vi.fn()}
        onCopyPullCommand={vi.fn()}
        onDeleteLocal={vi.fn()}
      />,
    )

    const localBadge = screen.getByText("statuses.local")

    expect(localBadge.className).toContain("metadata-pill")
    expect(localBadge.className).not.toContain("bg-success")
    expect(localBadge.className).not.toContain("text-success")
    expect(screen.getByRole("button", { name: /actions.repull/i })).toBeInTheDocument()
    expect(container.querySelector("svg.lucide-package2")).not.toBeNull()
  })
})

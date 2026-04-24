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
  it("keeps the local badge visible while using the quieter package glyph", () => {
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

    expect(screen.getByText("statuses.local")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /actions.repull/i })).toBeInTheDocument()
    expect(container.querySelector("svg.lucide-package2")).not.toBeNull()
  })
})

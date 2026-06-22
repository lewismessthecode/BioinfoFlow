import { fireEvent, render, screen, within } from "@testing-library/react"
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
  it("groups the same image repository into one card with multiple versions", () => {
    const images: DockerImage[] = [
      { ...image, id: "img-1", tag: "1.0", full_name: "minibwa:1.0", name: "minibwa" },
      { ...image, id: "img-2", tag: "1.1", full_name: "minibwa:1.1", name: "minibwa", size_bytes: 167 * 1024 * 1024 },
      { ...image, id: "img-3", tag: "1.0-FIXED", full_name: "minibwa:1.0-FIXED", name: "minibwa" },
    ]

    render(
      <ImageCardsGrid
        images={images}
        tImages={(key) => key}
        tCommon={(key) => key}
        onPull={vi.fn()}
        onViewDetails={vi.fn()}
        onCopyName={vi.fn()}
        onCopyPullCommand={vi.fn()}
        onDeleteLocal={vi.fn()}
      />,
    )

    expect(screen.getAllByRole("heading", { name: "minibwa" })).toHaveLength(1)
    const card = screen.getByRole("heading", { name: "minibwa" }).closest("article")
    expect(card).not.toBeNull()
    expect(within(card as HTMLElement).getByText("1.0")).toBeInTheDocument()
    expect(within(card as HTMLElement).getByText("1.1")).toBeInTheDocument()
    expect(within(card as HTMLElement).getByText("1.0-FIXED")).toBeInTheDocument()
    expect(within(card as HTMLElement).getByText("167 MB")).toBeInTheDocument()
  })

  it("keeps version actions scoped to the selected tag", () => {
    const onPull = vi.fn()
    const oneZero = { ...image, id: "img-1", tag: "1.0", full_name: "minibwa:1.0", name: "minibwa" }
    const oneOne = { ...image, id: "img-2", tag: "1.1", full_name: "minibwa:1.1", name: "minibwa", status: "remote" as const }

    render(
      <ImageCardsGrid
        images={[oneZero, oneOne]}
        tImages={(key) => key}
        tCommon={(key) => key}
        onPull={onPull}
        onViewDetails={vi.fn()}
        onCopyName={vi.fn()}
        onCopyPullCommand={vi.fn()}
        onDeleteLocal={vi.fn()}
      />,
    )

    const row = screen.getByText("1.1").closest("[data-testid='image-version-row']")
    expect(row).not.toBeNull()
    fireEvent.click(within(row as HTMLElement).getByRole("button", { name: /actions.pull/i }))

    expect(onPull).toHaveBeenCalledWith(oneOne)
  })

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

  it("keeps long image names from covering the actions menu", () => {
    const longName = "ghcr.io/bioinfoflow/parabricks_container_smoke_with_a_very_long_identifier"
    render(
      <ImageCardsGrid
        images={[{ ...image, name: longName, full_name: `${longName}:latest` }]}
        tImages={(key) => key}
        tCommon={(key) => key}
        onPull={vi.fn()}
        onViewDetails={vi.fn()}
        onCopyName={vi.fn()}
        onCopyPullCommand={vi.fn()}
        onDeleteLocal={vi.fn()}
      />,
    )

    const title = screen.getByRole("heading", { name: longName })
    expect(title.className).toContain("min-w-0")
    expect(title.closest(".min-w-0.flex-1")).not.toBeNull()
    expect(screen.getByRole("button", { name: "actions" }).className).toContain("shrink-0")
  })
})

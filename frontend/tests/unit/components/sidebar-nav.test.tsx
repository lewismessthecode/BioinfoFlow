import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const usePathnameMock = vi.fn()

vi.mock("next/navigation", () => ({
  usePathname: () => usePathnameMock(),
}))

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    className,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} className={className} {...props}>
      {children}
    </a>
  ),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) =>
    ({
      dashboard: "Dashboard",
      agent: "Agent",
      workflows: "Workflows",
      runs: "Runs",
      images: "Images",
      scheduler: "Scheduler",
    })[key] ?? key,
}))

import { SidebarNav } from "@/components/bioinfoflow/sidebar/sidebar-nav"

describe("SidebarNav", () => {
  beforeEach(() => {
    usePathnameMock.mockReset()
  })

  it("marks the active route with aria-current", () => {
    usePathnameMock.mockReturnValue("/agent")

    render(<SidebarNav collapsed={false} />)

    expect(screen.getByRole("link", { name: "Agent" })).toHaveAttribute("aria-current", "page")
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current")
  })

  it("keeps the active route visually flat instead of elevated", () => {
    usePathnameMock.mockReturnValue("/agent")

    render(<SidebarNav collapsed={false} />)

    const activeLink = screen.getByRole("link", { name: "Agent" })
    expect(activeLink.className).not.toContain("shadow-sm")
    expect(activeLink.className).not.toContain("ring-1")
  })

  it("uses a flat selected pill closer to the reference sidebar polish", () => {
    usePathnameMock.mockReturnValue("/agent")

    render(<SidebarNav collapsed={false} />)

    const activeLink = screen.getByRole("link", { name: "Agent" })
    const inactiveLink = screen.getByRole("link", { name: "Dashboard" })

    expect(activeLink.className).toContain("bg-sidebar-foreground/[0.08]")
    expect(activeLink.className).toContain("text-sidebar-foreground")
    expect(activeLink.className).not.toContain("bg-sidebar-accent")
    expect(activeLink.className).not.toContain("bg-white")
    expect(inactiveLink.className).toContain("hover:bg-sidebar-foreground/[0.055]")
    expect(inactiveLink.className).not.toContain("hover:bg-sidebar-accent")
    expect(inactiveLink.className).not.toContain("text-foreground/72")
  })

  it("renders desktop links as compact system-list rows", () => {
    usePathnameMock.mockReturnValue("/agent")

    render(<SidebarNav collapsed={false} />)

    const activeLink = screen.getByRole("link", { name: "Agent" })

    expect(activeLink.className).toContain("h-[30px]")
    expect(activeLink.className).toContain("gap-2")
    expect(activeLink.className).toContain("px-2.5")
    expect(activeLink.className).toContain("text-[12px]")
    expect(activeLink.className).not.toContain("h-[34px]")
    expect(activeLink.className).not.toContain("gap-3")
  })
})

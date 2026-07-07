import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ConversationItem } from "@/components/bioinfoflow/sidebar/conversation-item"

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <div />,
}))

const noop = vi.fn()

describe("ConversationItem", () => {
  it("uses low-contrast neutral hover styling instead of accent color", () => {
    render(
      <ConversationItem
        conversation={{ id: "conv-1", title: "Conversation 2", pinned: false }}
        projectId="project-1"
        index={1}
        isActive={false}
        onSelect={noop}
        onRename={noop}
        onTogglePin={noop}
        onDelete={noop}
        tSidebar={(key) => key}
        tCommon={(key) => key}
      />
    )

    const row = screen.getByRole("button", { name: "Conversation 2" }).closest(".group")
    expect(row?.className).not.toContain("hover:bg-accent")
    expect(row?.className).not.toContain("hover:bg-sidebar-accent")
    expect(row?.className).not.toContain("text-accent-foreground")
    expect(row?.className).toContain("hover:bg-sidebar-foreground/[0.055]")
  })

  it("uses a flat selected pill for the active conversation", () => {
    render(
      <ConversationItem
        conversation={{ id: "conv-1", title: "Conversation 2", pinned: false }}
        projectId="project-1"
        index={1}
        isActive
        onSelect={noop}
        onRename={noop}
        onTogglePin={noop}
        onDelete={noop}
        tSidebar={(key) => key}
        tCommon={(key) => key}
      />
    )

    const row = screen.getByRole("button", { name: "Conversation 2" }).closest(".group")
    expect(row?.className).toContain("bg-sidebar-foreground/[0.08]")
    expect(row?.className).not.toContain("bg-sidebar-accent")
    expect(row?.className).toContain("text-sidebar-foreground")
    expect(row?.className).not.toContain("bg-white")
  })

  it("uses compact transcript rows for the sidebar list", () => {
    render(
      <ConversationItem
        conversation={{ id: "conv-1", title: "Conversation 2", pinned: false }}
        projectId="project-1"
        index={1}
        isActive={false}
        onSelect={noop}
        onRename={noop}
        onTogglePin={noop}
        onDelete={noop}
        tSidebar={(key) => key}
        tCommon={(key) => key}
      />,
    )

    const row = screen.getByRole("button", { name: "Conversation 2" }).closest(".group")
    expect(row?.className).toContain("text-[12px]")
    expect(row?.className).toContain("px-2")
    expect(row?.className).not.toContain("text-sm")
    expect(row?.className).not.toContain("px-3")
  })
})

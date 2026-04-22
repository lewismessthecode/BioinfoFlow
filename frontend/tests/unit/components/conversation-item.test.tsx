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
  it("uses lighter neutral hover styling instead of accent green", () => {
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
    expect(row?.className).not.toContain("text-accent-foreground")
    expect(row?.className).toContain("hover:bg-sidebar-accent/42")
  })

  it("uses the softest selected pill for the active conversation", () => {
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
    expect(row?.className).toContain("bg-sidebar-accent/62")
    expect(row?.className).toContain("border-sidebar-border/45")
    expect(row?.className).not.toContain("bg-white")
  })
})

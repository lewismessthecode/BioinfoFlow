import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ProjectItem } from "@/components/bioinfoflow/sidebar/project-item"

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <div />,
}))

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const noop = vi.fn()

describe("ProjectItem", () => {
  it("uses a flat selected pill for the active project", () => {
    render(
      <ProjectItem
        project={{ id: "demo-project", name: "Demo", project_root: "asset://project" }}
        isActive
        isExpanded={false}
        collapsed={false}
        conversations={[]}
        isLoadingConversations={false}
        activeConversationId=""
        onToggleExpand={noop}
        onSelectProject={noop}
        onSelectConversation={noop}
        onConversationDragStart={noop}
        onConversationDragEnd={noop}
        onConversationDrop={noop}
        onConversationDragOver={noop}
        onConversationDragLeave={noop}
        onCreateConversation={noop}
        onRenameConversation={noop}
        onTogglePin={noop}
        onDeleteConversation={noop}
        onRenameProject={noop}
        onDuplicateProject={noop}
        onDeleteProject={noop}
        tSidebar={(key) => key}
        tCommon={(key) => key}
      />
    )

    const projectButton = screen.getByRole("button", { name: "Demo" })
    const projectHeader = projectButton.closest(".group")

    expect(projectHeader?.className).not.toContain("bg-accent")
    expect(projectHeader?.className).not.toContain("shadow-sm")
    expect(projectHeader?.className).not.toContain("ring-1")
    expect(projectHeader?.className).toContain("bg-sidebar-accent")
    expect(projectHeader?.className).toContain("text-sidebar-foreground")
    expect(projectHeader?.className).not.toContain("bg-white")
  })
})

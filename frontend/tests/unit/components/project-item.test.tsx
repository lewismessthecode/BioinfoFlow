import { fireEvent, render, screen } from "@testing-library/react"
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
    expect(projectHeader?.className).toContain("bg-sidebar-foreground/[0.08]")
    expect(projectHeader?.className).not.toContain("bg-sidebar-accent")
    expect(projectHeader?.className).toContain("text-sidebar-foreground")
    expect(projectHeader?.className).not.toContain("bg-white")
  })

  it("uses compact project rows instead of a chunky card header", () => {
    render(
      <ProjectItem
        project={{ id: "demo-project", name: "Demo", project_root: "asset://project" }}
        isActive={false}
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
      />,
    )

    const projectButton = screen.getByRole("button", { name: "Demo" })
    const projectHeader = projectButton.closest(".group")

    expect(projectHeader?.className).toContain("text-[12px]")
    expect(projectHeader?.className).toContain("px-1.5")
    expect(projectHeader?.className).not.toContain("text-[13px]")
    expect(projectHeader?.className).not.toContain("py-1.5")
  })

  it("toggles an active expanded project when the main project row is clicked", () => {
    const onToggleExpand = vi.fn()
    const onSelectProject = vi.fn()
    render(
      <ProjectItem
        project={{ id: "demo-project", name: "Demo", project_root: "asset://project" }}
        isActive
        isExpanded
        collapsed={false}
        conversations={[]}
        isLoadingConversations={false}
        activeConversationId=""
        onToggleExpand={onToggleExpand}
        onSelectProject={onSelectProject}
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
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Demo" }))

    expect(onToggleExpand).toHaveBeenCalledWith("demo-project")
    expect(onSelectProject).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Demo" })).toHaveAttribute(
      "aria-expanded",
      "true",
    )
    expect(screen.queryByRole("button", { name: "Collapse" })).not.toBeInTheDocument()
  })

  it("keeps project row action buttons independent from row selection", () => {
    const onToggleExpand = vi.fn()
    const onSelectProject = vi.fn()
    const onCreateConversation = vi.fn()
    render(
      <ProjectItem
        project={{ id: "demo-project", name: "Demo", project_root: "asset://project" }}
        isActive
        isExpanded={false}
        collapsed={false}
        conversations={[]}
        isLoadingConversations={false}
        activeConversationId=""
        onToggleExpand={onToggleExpand}
        onSelectProject={onSelectProject}
        onSelectConversation={noop}
        onConversationDragStart={noop}
        onConversationDragEnd={noop}
        onConversationDrop={noop}
        onConversationDragOver={noop}
        onConversationDragLeave={noop}
        onCreateConversation={onCreateConversation}
        onRenameConversation={noop}
        onTogglePin={noop}
        onDeleteConversation={noop}
        onRenameProject={noop}
        onDuplicateProject={noop}
        onDeleteProject={noop}
        tSidebar={(key) => key}
        tCommon={(key) => key}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "newConversation" }))

    expect(onCreateConversation).toHaveBeenCalledWith("demo-project")
    expect(onToggleExpand).not.toHaveBeenCalled()
    expect(onSelectProject).not.toHaveBeenCalled()
  })

  it("keeps empty expanded projects free of explanatory rows", () => {
    render(
      <ProjectItem
        project={{ id: "demo-project", name: "Demo", project_root: "asset://project" }}
        isActive={false}
        isExpanded
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
      />,
    )

    expect(screen.queryByText("noConversations")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "newConversation" })).toBeInTheDocument()
  })
})

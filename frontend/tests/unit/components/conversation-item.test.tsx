import { render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ConversationItem } from "@/components/bioinfoflow/sidebar/conversation-item"

const nextIntlMock = vi.hoisted(() => ({ locale: "zh-CN" }))

vi.mock("next-intl", () => ({
  useLocale: () => nextIntlMock.locale,
}))

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <div />,
}))

const noop = vi.fn()

const baseConversation = {
  id: "conv-1",
  project_id: "project-1",
  workspace_id: "workspace-1",
  user_id: "user-1",
  title: "Conversation 2",
  role_profile: "bioinformatician",
  permission_mode: "guarded_auto",
  automation_mode: "assisted",
  status: "active",
  pinned: false,
  created_at: "2026-07-17T04:00:00Z",
  updated_at: "2026-07-17T04:00:00Z",
} as const

describe("ConversationItem", () => {
  beforeEach(() => {
    nextIntlMock.locale = "zh-CN"
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-07-17T04:00:00Z"))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("uses low-contrast neutral hover styling instead of accent color", () => {
    render(
      <ConversationItem
        conversation={baseConversation}
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
        conversation={baseConversation}
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
        conversation={baseConversation}
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

  it("shows zh relative dates for conversation updates", () => {
    const { rerender } = render(
      <ConversationItem
        conversation={{ ...baseConversation, updated_at: "2026-07-16T04:00:00Z" }}
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
    expect(screen.getByText("昨天")).toBeInTheDocument()

    rerender(
      <ConversationItem
        conversation={{ ...baseConversation, updated_at: "2026-07-15T04:00:00Z" }}
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
    expect(screen.getByText("2天前")).toBeInTheDocument()

    rerender(
      <ConversationItem
        conversation={{ ...baseConversation, updated_at: "2026-07-10T04:00:00Z" }}
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
    expect(screen.getByText("一周前")).toBeInTheDocument()
  })

  it("shows English relative dates for conversation updates", () => {
    nextIntlMock.locale = "en"
    const { rerender } = render(
      <ConversationItem
        conversation={{ ...baseConversation, updated_at: "2026-07-16T04:00:00Z" }}
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
    expect(screen.getByText("yesterday")).toBeInTheDocument()

    rerender(
      <ConversationItem
        conversation={{ ...baseConversation, updated_at: "2026-07-15T04:00:00Z" }}
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
    expect(screen.getByText("2 days ago")).toBeInTheDocument()

    rerender(
      <ConversationItem
        conversation={{ ...baseConversation, updated_at: "2026-07-10T04:00:00Z" }}
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
    expect(screen.getByText("1 week ago")).toBeInTheDocument()
  })
})

import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ProjectList } from "@/components/bioinfoflow/sidebar/project-list"
import type { AgentSessionSummary } from "@/lib/agent/client"

vi.mock("@/components/bioinfoflow/sidebar/project-item", () => ({
  ProjectItem: ({
    project,
    conversations,
  }: {
    project: { id: string; name: string }
    conversations: AgentSessionSummary[]
  }) => (
    <section aria-label={project.name}>
      {conversations.map((conversation) => (
        <span key={conversation.id}>{conversation.title}</span>
      ))}
    </section>
  ),
}))

vi.mock("@/components/bioinfoflow/sidebar/conversation-item", () => ({
  ConversationItem: ({ conversation }: { conversation: AgentSessionSummary }) => (
    <span>{conversation.title}</span>
  ),
}))

const noop = vi.fn()

const session = (id: string, projectId: string, title: string): AgentSessionSummary => ({
  id,
  project_id: projectId,
  title,
  permission_mode: "ask_changes",
  workspace_access: "read_write",
  status: "active",
  created_at: "2026-08-15T00:00:00Z",
  updated_at: "2026-08-15T00:00:00Z",
})

const baseProps = {
  projects: [{ id: "project-demo", name: "Demo", project_root: "asset://project" }],
  inboxConversations: [] as AgentSessionSummary[],
  defaultProjectId: "project-default",
  expandedProjects: new Set(["project-demo"]),
  projectConversations: new Map<string, AgentSessionSummary[]>(),
  loadingProjects: new Set<string>(),
  collapsed: false,
  activeProjectId: "",
  activeConversationId: "",
  onToggleExpand: noop,
  onSelectProject: noop,
  onSelectConversation: noop,
  onCreateConversation: noop,
  onRenameConversation: noop,
  onDeleteConversation: noop,
  onRenameProject: noop,
  onDuplicateProject: noop,
  onDeleteProject: noop,
  onOpenCreateDialog: noop,
  tSidebar: (key: string) => key,
  tCommon: (key: string) => key,
}

describe("ProjectList", () => {
  it("renders sessions only in their product-level project group", () => {
    render(
      <ProjectList
        {...baseProps}
        inboxConversations={[
          session("session-recent", "project-default", "Recent analysis"),
        ]}
        projectConversations={
          new Map([
            ["project-demo", [session("session-demo", "project-demo", "Demo analysis")]],
          ])
        }
      />,
    )

    expect(screen.getByText("Recent analysis")).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Demo" })).toHaveTextContent(
      "Demo analysis",
    )
  })

  it("does not expose cross-project session drag and drop", () => {
    const { container } = render(
      <ProjectList
        {...baseProps}
        inboxConversations={[
          session("session-recent", "project-default", "Recent analysis"),
        ]}
      />,
    )

    expect(container.querySelector("[draggable='true']")).toBeNull()
  })

  it("keeps the recent section invisible when it is empty", () => {
    render(<ProjectList {...baseProps} />)

    expect(screen.getByTestId("sidebar-recent-section")).toHaveClass("h-0", "overflow-hidden")
  })

  it("omits empty-state explanatory copy and the duplicate create control", () => {
    render(<ProjectList {...baseProps} projects={[]} />)

    expect(screen.queryByText("noProjects")).not.toBeInTheDocument()
    expect(screen.queryByText("noConversations")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "newProject" })).not.toBeInTheDocument()
  })
})

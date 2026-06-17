import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ProjectList } from "@/components/bioinfoflow/sidebar/project-list"

vi.mock("@/components/bioinfoflow/sidebar/project-item", () => ({
  ProjectItem: ({
    project,
    conversations,
    onConversationDragStart,
    onConversationDragEnd,
    onConversationDrop,
    onConversationDragOver,
  }: {
    project: { id: string; name: string }
    conversations?: Array<{ id: string; title?: string | null }>
    onConversationDragStart: (
      conversation: { id: string; title?: string | null },
      projectId: string,
    ) => void
    onConversationDragEnd: () => void
    onConversationDrop: (projectId: string) => void
    onConversationDragOver: (projectId: string) => void
  }) => (
    <div
      data-testid={`project-${project.id}`}
      onDragOver={() => onConversationDragOver(project.id)}
      onDrop={() => onConversationDrop(project.id)}
    >
      {project.name}
      {conversations?.map((conversation) => (
        <div
          key={conversation.id}
          draggable
          data-testid={`project-conversation-${conversation.id}`}
          onDragStart={() => onConversationDragStart(conversation, project.id)}
          onDragEnd={() => onConversationDragEnd()}
        >
          {conversation.title || conversation.id}
        </div>
      ))}
    </div>
  ),
}))

vi.mock("@/components/bioinfoflow/sidebar/conversation-item", () => ({
  ConversationItem: ({
    conversation,
    projectId,
    onDragStart,
    onDragEnd,
  }: {
    conversation: { id: string; title?: string | null }
    projectId: string
    onDragStart?: (conversation: { id: string; title?: string | null }, projectId: string) => void
    onDragEnd?: () => void
  }) => (
    <div
      draggable
      data-testid={`conversation-${conversation.id}`}
      onDragStart={() => onDragStart?.(conversation, projectId)}
      onDragEnd={() => onDragEnd?.()}
    >
      {conversation.title || conversation.id}
    </div>
  ),
}))

const noop = vi.fn()

describe("ProjectList", () => {
  it("moves an inbox conversation into a real project when dropped on that project", () => {
    const onMoveConversation = vi.fn()

    render(
      <ProjectList
        projects={[{ id: "project-demo", name: "Demo", project_root: "asset://project" }]}
        inboxConversations={[{ id: "conversation-inbox", project_id: "project-default", title: "Inbox" }]}
        defaultProjectId="project-default"
        expandedProjects={new Set()}
        projectConversations={new Map()}
        loadingProjects={new Set()}
        collapsed={false}
        activeProjectId=""
        activeConversationId=""
        onToggleExpand={noop}
        onSelectProject={noop}
        onSelectConversation={noop}
        onMoveConversation={onMoveConversation}
        onCreateConversation={noop}
        onRenameConversation={noop}
        onTogglePin={noop}
        onDeleteConversation={noop}
        onRenameProject={noop}
        onDuplicateProject={noop}
        onDeleteProject={noop}
        onOpenCreateDialog={noop}
        tSidebar={(key) => key}
        tCommon={(key) => key}
      />
    )

    fireEvent.dragStart(screen.getByTestId("conversation-conversation-inbox"))
    fireEvent.dragOver(screen.getByTestId("project-project-demo"))
    fireEvent.drop(screen.getByTestId("project-project-demo"))

    expect(onMoveConversation).toHaveBeenCalledWith(
      "conversation-inbox",
      "project-default",
      "project-demo",
    )
  })

  it("moves a project conversation back to inbox when dropped on the recent section", () => {
    const onMoveConversation = vi.fn()

    render(
      <ProjectList
        projects={[{ id: "project-demo", name: "Demo", project_root: "asset://project" }]}
        inboxConversations={[]}
        defaultProjectId="project-default"
        expandedProjects={new Set(["project-demo"])}
        projectConversations={
          new Map([
            ["project-demo", [{ id: "conversation-1", project_id: "project-demo", title: "Analysis 1" }]],
          ])
        }
        loadingProjects={new Set()}
        collapsed={false}
        activeProjectId="project-demo"
        activeConversationId=""
        onToggleExpand={noop}
        onSelectProject={noop}
        onSelectConversation={noop}
        onMoveConversation={onMoveConversation}
        onCreateConversation={noop}
        onRenameConversation={noop}
        onTogglePin={noop}
        onDeleteConversation={noop}
        onRenameProject={noop}
        onDuplicateProject={noop}
        onDeleteProject={noop}
        onOpenCreateDialog={noop}
        tSidebar={(key) => key}
        tCommon={(key) => key}
      />
    )

    const recentSection = screen.getByTestId("sidebar-recent-section")
    expect(screen.queryByText("noConversations")).not.toBeInTheDocument()

    fireEvent.dragStart(screen.getByTestId("project-conversation-conversation-1"))
    fireEvent.dragOver(recentSection)
    fireEvent.drop(recentSection)

    expect(onMoveConversation).toHaveBeenCalledWith(
      "conversation-1",
      "project-demo",
      "project-default",
    )
  })
})

import { act, renderHook } from "@testing-library/react"
import { useState } from "react"
import { describe, expect, it } from "vitest"
import {
  ProjectProvider,
  useProjectContext,
} from "@/components/bioinfoflow/project-context"

describe("ProjectContext", () => {
  it("throws when used outside the provider", () => {
    expect(() => renderHook(() => useProjectContext())).toThrow(
      "ProjectContext must be used within ProjectProvider"
    )
  })

  it("propagates updated project and conversation state through the provider", () => {
    function Wrapper({ children }: { children: React.ReactNode }) {
      const [selectedProjectId, setSelectedProjectId] = useState("project-1")
      const [conversationProjectId, setConversationProjectId] = useState("project-1")
      const [activeProjectId, setActiveProjectId] = useState("project-1")
      const [activeConversationId, setActiveConversationId] = useState("conversation-1")
      const [activeProjectName, setActiveProjectName] = useState("Project One")
      const [activeConversationTitle, setActiveConversationTitle] = useState("Initial Chat")
      const selectWorkspaceProject = (projectId: string) => {
        setActiveProjectId(projectId)
        setSelectedProjectId(projectId)
        setConversationProjectId(projectId)
        setActiveConversationId("")
      }

      return (
        <ProjectProvider
          value={{
            selectedProjectId,
            setSelectedProjectId,
            conversationProjectId,
            setConversationProjectId,
            activeProjectId,
            setActiveProjectId: selectWorkspaceProject,
            selectWorkspaceProject,
            activeConversationId,
            setActiveConversationId,
            activeProjectName,
            setActiveProjectName,
            activeConversationTitle,
            setActiveConversationTitle,
          }}
        >
          {children}
        </ProjectProvider>
      )
    }

    const { result } = renderHook(() => useProjectContext(), { wrapper: Wrapper })

    expect(result.current.activeProjectId).toBe("project-1")
    expect(result.current.activeConversationTitle).toBe("Initial Chat")

    act(() => {
      result.current.setActiveProjectId("project-2")
      result.current.setActiveConversationId("conversation-2")
      result.current.setActiveProjectName("Project Two")
      result.current.setActiveConversationTitle("Updated Chat")
    })

    expect(result.current.activeProjectId).toBe("project-2")
    expect(result.current.selectedProjectId).toBe("project-2")
    expect(result.current.conversationProjectId).toBe("project-2")
    expect(result.current.activeConversationId).toBe("conversation-2")
    expect(result.current.activeProjectName).toBe("Project Two")
    expect(result.current.activeConversationTitle).toBe("Updated Chat")
  })
})

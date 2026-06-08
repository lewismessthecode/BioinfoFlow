import type { ReactElement } from "react"
import { useState } from "react"
import { ProjectProvider } from "@/components/bioinfoflow/project-context"
import { renderWithProviders } from "@/tests/test-utils"

type ProjectContextState = {
  selectedProjectId: string
  conversationProjectId: string
  activeProjectId: string
  activeConversationId: string
  activeProjectName: string
  activeConversationTitle: string
}

export type AppTestState = {
  agentSurfaceProps: Record<string, unknown>
}

type RenderAppPageOptions = {
  projectContext?: Partial<ProjectContextState>
  agentSurfaceProps?: Record<string, unknown>
}

const defaultProjectContext: ProjectContextState = {
  selectedProjectId: "",
  conversationProjectId: "",
  activeProjectId: "",
  activeConversationId: "",
  activeProjectName: "",
  activeConversationTitle: "",
}

/**
 * Create a wrapper component that provides ProjectContext with stateful values.
 * Use with renderHook() for hook tests, or indirectly via renderAppPage() for component tests.
 */
export function createAppWrapper(projectContext?: Partial<ProjectContextState>) {
  function AppWrapper({ children }: { children: React.ReactNode }) {
    const initialState = {
      ...defaultProjectContext,
      ...projectContext,
    }
    const [activeProjectId, setActiveProjectId] = useState(initialState.activeProjectId)
    const [selectedProjectId, setSelectedProjectId] = useState(
      initialState.selectedProjectId || initialState.activeProjectId
    )
    const [conversationProjectId, setConversationProjectId] = useState(
      initialState.conversationProjectId ||
        initialState.selectedProjectId ||
        initialState.activeProjectId
    )
    const [activeConversationId, setActiveConversationId] = useState(
      initialState.activeConversationId
    )
    const [activeProjectName, setActiveProjectName] = useState(
      initialState.activeProjectName
    )
    const [activeConversationTitle, setActiveConversationTitle] = useState(
      initialState.activeConversationTitle
    )
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
          activeProjectId: selectedProjectId || activeProjectId,
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

  return AppWrapper
}

export function renderAppPage(
  ui: ReactElement,
  options: RenderAppPageOptions = {}
) {
  const appTestState: AppTestState = {
    agentSurfaceProps: options.agentSurfaceProps ?? {},
  }

  return {
    ...renderWithProviders(ui, {
      wrapper: createAppWrapper(options.projectContext),
    }),
    appTestState,
  }
}

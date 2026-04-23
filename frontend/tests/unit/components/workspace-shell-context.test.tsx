import { act, renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const { useSidebarDataMock } = vi.hoisted(() => ({
  useSidebarDataMock: vi.fn(),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}))

vi.mock("@/hooks/use-sidebar-data", () => ({
  useSidebarData: (...args: unknown[]) => useSidebarDataMock(...args),
}))

import {
  WorkspaceShellProvider,
  useWorkspaceShell,
} from "@/components/bioinfoflow/workspace-shell-context"

describe("WorkspaceShellContext", () => {
  beforeEach(() => {
    useSidebarDataMock.mockReset()
    useSidebarDataMock.mockReturnValue({
      projects: [{ id: "project-1", name: "Alpha" }],
      conversations: [],
      isLoading: false,
    })
  })

  it("throws when used outside the provider", () => {
    expect(() => renderHook(() => useWorkspaceShell())).toThrow(
      "useWorkspaceShell must be used within WorkspaceShellProvider"
    )
  })

  it("derives hasProjects and manages the create-project dialog state", () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <WorkspaceShellProvider>{children}</WorkspaceShellProvider>
    )

    const { result } = renderHook(() => useWorkspaceShell(), { wrapper })

    expect(result.current.hasProjects).toBe(true)
    expect(result.current.createProjectDialogOpen).toBe(false)

    act(() => {
      result.current.openCreateProjectDialog()
    })
    expect(result.current.createProjectDialogOpen).toBe(true)

    act(() => {
      result.current.setCreateProjectDialogOpen(false)
    })
    expect(result.current.createProjectDialogOpen).toBe(false)
  })
})

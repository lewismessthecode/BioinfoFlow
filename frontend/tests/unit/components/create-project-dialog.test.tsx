import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const copy: Record<string, string> = {
      newProject: "New Project",
      createProject: "Create Project",
      projectDescription: "Create a new bioinformatics project",
      projectName: "Project Name",
      workspacePath: "Workspace Path",
      advancedSettings: "Advanced Settings",
      "placeholders.projectName": "e.g., COVID Analysis",
      "placeholders.workspacePath": "e.g., projects/my-analysis",
      "placeholders.projectDescription": "Short description",
      storageManagedPreview: "Storage managed by Bioinfoflow",
      "hints.storageOverridePath": "Advanced override for external storage",
    }
    return copy[key] ?? key
  },
}))

import { CreateProjectDialog } from "@/components/bioinfoflow/create-project-dialog"

describe("CreateProjectDialog", () => {
  const onCreateProject = vi.fn().mockResolvedValue(undefined)

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("shows a managed storage message when the user types a name", async () => {
    const user = userEvent.setup()
    render(<CreateProjectDialog collapsed={false} onCreateProject={onCreateProject} />)

    await user.click(screen.getByRole("button", { name: "New Project" }))

    const nameInput = screen.getByLabelText("Project Name")
    await user.type(nameInput, "COVID Analysis")

    expect(screen.getByText("Storage managed by Bioinfoflow")).toBeInTheDocument()
  })

  it("does not show the storage preview when the name is empty", async () => {
    const user = userEvent.setup()
    render(<CreateProjectDialog collapsed={false} onCreateProject={onCreateProject} />)

    await user.click(screen.getByRole("button", { name: "New Project" }))

    expect(screen.queryByText("Storage managed by Bioinfoflow")).not.toBeInTheDocument()
  })

  it("hides the workspace path input behind Advanced Settings by default", async () => {
    const user = userEvent.setup()
    render(<CreateProjectDialog collapsed={false} onCreateProject={onCreateProject} />)

    await user.click(screen.getByRole("button", { name: "New Project" }))

    // Advanced Settings should be visible as a toggle
    expect(screen.getByText("Advanced Settings")).toBeInTheDocument()

    // Workspace input is in the DOM but inside a collapsed grid-rows-[0fr] container
    const workspaceInput = screen.getByLabelText("Workspace Path")
    const overflowContainer = workspaceInput.closest(".overflow-hidden")
    expect(overflowContainer).toBeInTheDocument()
    // The grid parent should have grid-rows-[0fr] class (collapsed)
    const gridParent = overflowContainer?.parentElement
    expect(gridParent?.className).toContain("grid-rows-[0fr]")
  })

  it("reveals the workspace input when Advanced Settings is expanded", async () => {
    const user = userEvent.setup()
    render(<CreateProjectDialog collapsed={false} onCreateProject={onCreateProject} />)

    await user.click(screen.getByRole("button", { name: "New Project" }))

    const nameInput = screen.getByLabelText("Project Name")
    await user.type(nameInput, "My Project")

    await user.click(screen.getByText("Advanced Settings"))

    const workspaceInput = screen.getByLabelText("Workspace Path")
    expect(workspaceInput).toBeVisible()
    expect(workspaceInput).toHaveValue("")
  })

  it("creates a managed project when no override is set", async () => {
    const user = userEvent.setup()
    render(<CreateProjectDialog collapsed={false} onCreateProject={onCreateProject} />)

    await user.click(screen.getByRole("button", { name: "New Project" }))

    const nameInput = screen.getByLabelText("Project Name")
    await user.type(nameInput, "COVID Analysis")

    await user.click(screen.getByRole("button", { name: "Create Project" }))

    expect(onCreateProject).toHaveBeenCalledWith({
      name: "COVID Analysis",
      description: "",
    })
  })

  it("uses the manually entered storage override path when user overrides", async () => {
    const user = userEvent.setup()
    render(<CreateProjectDialog collapsed={false} onCreateProject={onCreateProject} />)

    await user.click(screen.getByRole("button", { name: "New Project" }))

    const nameInput = screen.getByLabelText("Project Name")
    await user.type(nameInput, "My Project")

    await user.click(screen.getByText("Advanced Settings"))

    const workspaceInput = screen.getByLabelText("Workspace Path")
    await user.clear(workspaceInput)
    await user.type(workspaceInput, "/custom/path")

    await user.click(screen.getByRole("button", { name: "Create Project" }))

    expect(onCreateProject).toHaveBeenCalledWith({
      name: "My Project",
      description: "",
      storageOverridePath: "/custom/path",
    })
  })

  it("keeps the override input empty until the user opts into an advanced path", async () => {
    const user = userEvent.setup()
    render(<CreateProjectDialog collapsed={false} onCreateProject={onCreateProject} />)

    await user.click(screen.getByRole("button", { name: "New Project" }))

    const nameInput = screen.getByLabelText("Project Name")
    await user.type(nameInput, "Alpha")

    // Expand Advanced — override remains empty until the user provides one
    await user.click(screen.getByText("Advanced Settings"))
    const workspaceInput = screen.getByLabelText("Workspace Path")
    expect(workspaceInput).toHaveValue("")

    // Change the name — override stays untouched because managed storage is automatic
    await user.clear(nameInput)
    await user.type(nameInput, "Beta")
    expect(workspaceInput).toHaveValue("")

    await user.click(screen.getByRole("button", { name: "Create Project" }))

    expect(onCreateProject).toHaveBeenCalledWith({
      name: "Beta",
      description: "",
    })
  })
})

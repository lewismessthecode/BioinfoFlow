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
      projectType: "Project type",
      "projectTypes.local.title": "Local",
      "projectTypes.local.description": "Use local storage",
      "projectTypes.remote.title": "Remote",
      "projectTypes.remote.description": "Use SSH storage",
      remoteHost: "Remote host",
      remoteHostFallback: "Remote host",
      remotePath: "Remote folder path",
      remoteStoragePreview: "Remote: {host} · {path}",
      loadingRemoteHosts: "Loading remote hosts...",
      noRemoteHosts: "No remote hosts configured",
      browseDirectories: "Browse...",
      "errors.remoteHostsLoadFailed": "Couldn't load remote hosts. Check the connection service and try again.",
      "placeholders.remotePath": "e.g., /data/project",
      "hints.remotePath": "Agent commands run from this remote folder",
      "placeholders.projectName": "e.g., COVID Analysis",
      "placeholders.workspacePath": "e.g., projects/my-analysis",
      "placeholders.projectDescription": "Short description",
      storageManagedPreview: "Storage managed by Bioinfoflow",
      "hints.storageOverridePath": "Advanced override for external storage",
    }
    return copy[key] ?? key
  },
}))

vi.mock("@/lib/demo-connections", () => ({
  fetchRemoteConnections: vi.fn(),
}))

import { fetchRemoteConnections } from "@/lib/demo-connections"
import { CreateProjectDialog } from "@/components/bioinfoflow/create-project-dialog"

describe("CreateProjectDialog", () => {
  const onCreateProject = vi.fn().mockResolvedValue(undefined)

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(fetchRemoteConnections).mockResolvedValue([
      {
        id: "11111111-1111-1111-1111-111111111111",
        name: "Phoenix login",
        host: "login.example.org",
        port: 22,
        username: "alice",
        auth_method: "agent",
        ssh_alias: "",
        key_path: "",
        status: "online",
        skill_instructions: "Use phoenixcli.",
      },
    ])
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

  it("creates a remote project with selected host and remote path", async () => {
    const user = userEvent.setup()
    render(<CreateProjectDialog collapsed={false} onCreateProject={onCreateProject} />)

    await user.click(screen.getByRole("button", { name: "New Project" }))
    await user.type(screen.getByLabelText("Project Name"), "Phoenix sample")
    await user.click(screen.getByRole("radio", { name: /Remote/ }))

    expect(await screen.findByLabelText("Remote host")).toBeInTheDocument()
    await user.type(screen.getByLabelText("Remote folder path"), "/inspurfsms102/B2C_RD1/project/sample_xxx")
    await user.click(screen.getByRole("button", { name: "Create Project" }))

    expect(onCreateProject).toHaveBeenCalledWith({
      name: "Phoenix sample",
      description: "",
      projectType: "remote",
      remoteConnectionId: "11111111-1111-1111-1111-111111111111",
      remoteRootPath: "/inspurfsms102/B2C_RD1/project/sample_xxx",
    })
  })

  it("shows an error option when remote hosts fail to load", async () => {
    const user = userEvent.setup()
    vi.mocked(fetchRemoteConnections).mockRejectedValueOnce(new Error("offline"))
    render(<CreateProjectDialog collapsed={false} onCreateProject={onCreateProject} />)

    await user.click(screen.getByRole("button", { name: "New Project" }))
    await user.click(screen.getByRole("radio", { name: /Remote/ }))

    expect(await screen.findByText("Couldn't load remote hosts. Check the connection service and try again."))
      .toBeInTheDocument()
  })
})

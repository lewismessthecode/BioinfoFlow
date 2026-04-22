import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, params?: Record<string, string>) => {
    const copy: Record<string, string> = {
      title: "Start your first analysis",
      subtitle: "Choose a project template or create a custom workspace.",
      blankName: "Blank Workspace",
      blankDescription: "Start with an empty project for ad hoc exploration",
      wgsName: "WGS Analysis",
      wgsDescription: "Whole genome sequencing variant calling",
      rnaseqName: "RNA-seq Analysis",
      rnaseqDescription: "Differential gene expression analysis",
      createFromTemplate: "Use Template",
      createFromTemplateNamed: "Use {name}",
      customProject: "Create a custom project",
    }
    const template = copy[key] ?? key
    if (!params) return template
    return template.replace(/\{(\w+)\}/g, (_, k) => params[k] ?? `{${k}}`)
  },
}))

import { WelcomeCard } from "@/components/bioinfoflow/welcome-card"

// Each template card is now a single <button> whose accessible name
// is the concatenation of its visible text children.
const BLANK_NAME = /Blank Workspace/
const WGS_NAME = /WGS Analysis/
const RNASEQ_NAME = /RNA-seq Analysis/

describe("WelcomeCard", () => {
  const onQuickCreate = vi.fn().mockResolvedValue(undefined)
  const onOpenCreateDialog = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders the welcome title and subtitle", () => {
    render(
      <WelcomeCard
        onQuickCreate={onQuickCreate}
        onOpenCreateDialog={onOpenCreateDialog}
      />
    )

    expect(screen.getByText("Start your first analysis")).toBeInTheDocument()
    expect(screen.getByText("Choose a project template or create a custom workspace.")).toBeInTheDocument()
  })

  it("renders all three template cards", () => {
    render(
      <WelcomeCard
        onQuickCreate={onQuickCreate}
        onOpenCreateDialog={onOpenCreateDialog}
      />
    )

    expect(screen.getByText("Blank Workspace")).toBeInTheDocument()
    expect(screen.getByText("Start with an empty project for ad hoc exploration")).toBeInTheDocument()

    expect(screen.getByText("WGS Analysis")).toBeInTheDocument()
    expect(screen.getByText("Whole genome sequencing variant calling")).toBeInTheDocument()

    expect(screen.getByText("RNA-seq Analysis")).toBeInTheDocument()
    expect(screen.getByText("Differential gene expression analysis")).toBeInTheDocument()
  })

  it("renders a clickable button for each template", () => {
    render(
      <WelcomeCard
        onQuickCreate={onQuickCreate}
        onOpenCreateDialog={onOpenCreateDialog}
      />
    )

    expect(screen.getByRole("button", { name: BLANK_NAME })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: WGS_NAME })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: RNASEQ_NAME })).toBeInTheDocument()
  })

  it("calls onQuickCreate with blank template data when first card button is clicked", async () => {
    const user = userEvent.setup()
    render(
      <WelcomeCard
        onQuickCreate={onQuickCreate}
        onOpenCreateDialog={onOpenCreateDialog}
      />
    )

    await user.click(screen.getByRole("button", { name: BLANK_NAME }))

    expect(onQuickCreate).toHaveBeenCalledWith({
      name: "Blank Workspace",
      description: "Start with an empty project for ad hoc exploration",
    })
  })

  it("calls onQuickCreate with WGS template data when second card button is clicked", async () => {
    const user = userEvent.setup()
    render(
      <WelcomeCard
        onQuickCreate={onQuickCreate}
        onOpenCreateDialog={onOpenCreateDialog}
      />
    )

    await user.click(screen.getByRole("button", { name: WGS_NAME }))

    expect(onQuickCreate).toHaveBeenCalledWith({
      name: "WGS Analysis",
      description: "Whole genome sequencing variant calling",
    })
  })

  it("calls onQuickCreate with RNA-seq template data when third card button is clicked", async () => {
    const user = userEvent.setup()
    render(
      <WelcomeCard
        onQuickCreate={onQuickCreate}
        onOpenCreateDialog={onOpenCreateDialog}
      />
    )

    await user.click(screen.getByRole("button", { name: RNASEQ_NAME }))

    expect(onQuickCreate).toHaveBeenCalledWith({
      name: "RNA-seq Analysis",
      description: "Differential gene expression analysis",
    })
  })

  it("renders a custom project link that calls onOpenCreateDialog", async () => {
    const user = userEvent.setup()
    render(
      <WelcomeCard
        onQuickCreate={onQuickCreate}
        onOpenCreateDialog={onOpenCreateDialog}
      />
    )

    await user.click(screen.getByRole("button", { name: "Create a custom project" }))

    expect(onOpenCreateDialog).toHaveBeenCalled()
  })

  it("disables create buttons while a template is being created", async () => {
    let resolveCreate: () => void
    const pendingCreate = new Promise<void>((resolve) => {
      resolveCreate = resolve
    })
    onQuickCreate.mockReturnValueOnce(pendingCreate)

    const user = userEvent.setup()
    render(
      <WelcomeCard
        onQuickCreate={onQuickCreate}
        onOpenCreateDialog={onOpenCreateDialog}
      />
    )

    await user.click(screen.getByRole("button", { name: BLANK_NAME }))

    for (const pattern of [BLANK_NAME, WGS_NAME, RNASEQ_NAME]) {
      expect(screen.getByRole("button", { name: pattern })).toBeDisabled()
    }

    resolveCreate!()
  })
})

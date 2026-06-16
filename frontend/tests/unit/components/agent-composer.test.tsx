import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentComposer } from "@/components/bioinfoflow/agent-runtime/agent-composer"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      composerPlaceholder: "Message Bioinfoflow...",
      attach: "Attach or add context",
      send: "Send message",
      stop: "Stop response",
      "attachMenu.attachFiles": "Attach files",
      "attachMenu.browseProjectFiles": "Browse project files",
      "attachMenu.referenceRun": "Reference a run",
      "attachMenu.runPreflight": "Run preflight",
      "attachMenu.diagnoseRun": "Diagnose run",
      "attachMenu.comingSoon": "Coming soon",
      "mode.label": "Agent mode",
      "mode.act": "Act",
      "mode.plan": "Plan",
      "permission.label": "Permission mode",
      "permission.options.ask_each_action.label": "Request approval",
      "permission.options.ask_each_action.description": "Ask before side-effecting actions.",
      "permission.options.guarded_auto.label": "Approve for me",
      "permission.options.guarded_auto.description": "Run low-risk actions automatically.",
      "permission.options.bypass.label": "Full access",
      "permission.options.bypass.description": "Run non-critical actions automatically.",
      "files.removeAttachment": "Remove workflow.wdl",
      auto: "Auto",
      configure: "Configure providers",
      noProviders: "No model available",
      searchModels: "Search models...",
    }
    return labels[key] ?? key
  },
}))

vi.mock("@/components/bioinfoflow/chat/provider-icons", () => ({
  ProviderIcon: ({ provider }: { provider: string }) => (
    <span aria-hidden="true" data-provider={provider} />
  ),
}))

describe("AgentComposer", () => {
  it("grows with input until the max height cap", () => {
    const onChange = vi.fn()
    render(
      <AgentComposer
        value=""
        onChange={onChange}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )

    const textarea = screen.getByPlaceholderText("Message Bioinfoflow...")
    let nextHeight = 132
    Object.defineProperty(textarea, "scrollHeight", {
      configurable: true,
      get: () => nextHeight,
    })

    fireEvent.change(textarea, { target: { value: "first line\nsecond line" } })

    expect(onChange).toHaveBeenCalledWith("first line\nsecond line")
    expect(textarea).toHaveStyle({ height: "132px" })

    nextHeight = 420
    fireEvent.change(textarea, { target: { value: "expanded content" } })

    expect(textarea).toHaveStyle({ height: "160px" })
    expect(textarea).toHaveStyle({ overflowY: "auto" })
  })

  it("toggles plan and act modes with Shift+Tab", () => {
    const onModeChange = vi.fn()
    render(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        mode="execution"
        onModeChange={onModeChange}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )

    fireEvent.keyDown(screen.getByPlaceholderText("Message Bioinfoflow..."), {
      key: "Tab",
      shiftKey: true,
    })

    expect(onModeChange).toHaveBeenCalledWith("plan")
  })

  it("renders context attachment chips", () => {
    const onRemoveContextAttachment = vi.fn()
    render(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        contextAttachments={[
          { kind: "file_ref", path: "/workspace/workflow.wdl", label: "workflow.wdl" },
        ]}
        onRemoveContextAttachment={onRemoveContextAttachment}
      />,
    )

    expect(screen.getByTestId("context-attachments")).toBeInTheDocument()
    expect(screen.getByText("workflow.wdl")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Remove workflow.wdl" }))
    expect(onRemoveContextAttachment).toHaveBeenCalledWith("/workspace/workflow.wdl")
  })

  it("changes permission mode from the composer dropdown", async () => {
    const onPermissionModeChange = vi.fn()
    render(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        permissionMode="guarded_auto"
        onPermissionModeChange={onPermissionModeChange}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )

    fireEvent.pointerDown(screen.getByRole("button", { name: "Permission mode" }))
    fireEvent.click(await screen.findByText("Full access"))

    expect(onPermissionModeChange).toHaveBeenCalledWith("bypass")
  })
})

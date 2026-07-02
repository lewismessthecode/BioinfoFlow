import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AgentComposer } from "@/components/bioinfoflow/agent-runtime/agent-composer"
import { apiRequest } from "@/lib/api"

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
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
      "runtimeLocation.placeholder": "Local / Remote",
      "runtimeLocation.menuTitle": "Local / Remote",
      "runtimeLocation.manage": "Manage SSH hosts",
      "runtimeLocation.local.label": "Local",
      "runtimeLocation.local.description": "Run in this Bioinfoflow workspace",
      "runtimeLocation.remote.label": "Remote",
      "runtimeLocation.emptyRemoteHosts": "No remote hosts configured.",
      "runtimeLocation.loadFailed": "Could not load remote hosts.",
      "runtimeLocation.status.online": "Online",
      "runtimeLocation.status.offline": "Offline",
      "runtimeLocation.status.error": "Connection error",
      "runtimeLocation.status.unknown": "Not tested",
      "runtimeLocation.selectedLocalAria": "Current execution target: local",
      "runtimeLocation.selectedRemoteAria": `Current execution target: ${values?.name ?? ""} at ${values?.host ?? ""}, ${values?.status ?? ""}`,
      placeholder: "Local / Remote",
      menuTitle: "Local / Remote",
      manage: "Manage SSH hosts",
      "local.label": "Local",
      "local.description": "Run in this Bioinfoflow workspace",
      "remote.label": "Remote",
      emptyRemoteHosts: "No remote hosts configured.",
      loadFailed: "Could not load remote hosts.",
      "status.online": "Online",
      "status.offline": "Offline",
      "status.error": "Connection error",
      "status.unknown": "Not tested",
      selectedLocalAria: "Current execution target: local",
      selectedRemoteAria: `Current execution target: ${values?.name ?? ""} at ${values?.host ?? ""}, ${values?.status ?? ""}`,
      "tokenUsage.label": "Tokens",
      "tokenUsage.display": `${values?.value ?? ""} tokens`,
      "tokenUsage.compactDisplay": `${values?.value ?? ""}`,
      "tokenUsage.aria": `${values?.total ?? ""} tokens used in this session. ${values?.input ?? ""} input, ${values?.output ?? ""} output.`,
      "tokenUsage.title": "Context window",
      "tokenUsage.used": "Used",
      "tokenUsage.remaining": "remaining",
      "tokenUsage.input": "Input",
      "tokenUsage.output": "Output",
      "tokenUsage.cached": "Cached",
      "tokenUsage.reasoning": "Reasoning",
      "tokenUsage.window": "Window",
      "tokenUsage.maxOutput": "Max output",
    }
    return labels[key] ?? key
  },
}))

vi.mock("@/components/bioinfoflow/chat/provider-icons", () => ({
  ProviderIcon: ({ provider }: { provider: string }) => (
    <span aria-hidden="true" data-provider={provider} />
  ),
}))

const apiRequestMock = vi.mocked(apiRequest)

const composerConnections = [
  {
    id: "connection-sim-224",
    name: "Simulation host sz01",
    host: "10.227.5.224",
    port: 22,
    username: "bioflow",
    auth_method: "key_file",
    ssh_alias: "",
    key_path: "~/.ssh/bioflow_sim_ed25519",
    status: "online",
    skill_instructions: "Use /data/sim.",
  },
  {
    id: "connection-test-231",
    name: "Test host sz03",
    host: "10.227.5.231",
    port: 22,
    username: "bioflow",
    auth_method: "ssh_config",
    ssh_alias: "bioflow-test-sz03",
    key_path: "",
    status: "online",
    skill_instructions: "Use /data/test.",
  },
]

describe("AgentComposer", () => {
  beforeEach(() => {
    apiRequestMock.mockReset()
    apiRequestMock.mockReturnValue(new Promise(() => {}))
  })

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

  it("keeps composer controls accessible in constrained side-panel layouts", () => {
    render(
      <div style={{ width: 420 }}>
        <AgentComposer
          value="Run QC"
          onChange={vi.fn()}
          onSubmit={vi.fn()}
          onStop={vi.fn()}
          isRunning={false}
          permissionMode="bypass"
          onPermissionModeChange={vi.fn()}
          mode="execution"
          onModeChange={vi.fn()}
          models={[]}
          selectedModel={null}
          onSelectModel={vi.fn()}
        />
      </div>,
    )

    expect(screen.getByRole("button", { name: "Permission mode" })).toBeVisible()
    expect(screen.getByRole("group", { name: "Agent mode" })).toBeVisible()
    expect(screen.getByRole("link", { name: "Configure providers" })).toBeVisible()
    expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled()
  })

  it("compresses secondary controls when rendered beside the side panel", () => {
    render(
      <AgentComposer
        value="Run QC"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        permissionMode="bypass"
        onPermissionModeChange={vi.fn()}
        mode="execution"
        onModeChange={vi.fn()}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        compactControls
      />,
    )

    expect(screen.getByTestId("agent-composer")).toHaveAttribute(
      "data-compact-controls",
      "true",
    )
    expect(screen.getByRole("button", { name: "Permission mode" })).toHaveClass(
      "max-w-9",
    )
    const modeGroup = screen.getByRole("group", { name: "Agent mode" })
    expect(modeGroup).toHaveClass("hidden")
    expect(modeGroup).not.toHaveClass("sm:flex")
  })

  it("shows cumulative token usage with accessible details", async () => {
    render(
      <AgentComposer
        value="Run QC"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        tokenUsageSummary={{
          has_token_usage: true,
          input_tokens: 97_000,
          output_tokens: 3_000,
          total_tokens: 100_000,
          cached_input_tokens: 12_000,
          reasoning_tokens: 600,
          context_window: 258_000,
          max_output_tokens: 8_192,
          turns_with_usage: 2,
          raw_totals: {},
        }}
      />,
    )

    const trigger = screen.getByRole("button", {
      name: "100K tokens used in this session. 97K input, 3K output.",
    })
    expect(trigger).toHaveTextContent("100K tokens")

    fireEvent.click(trigger)

    expect(await screen.findByText("Context window")).toBeInTheDocument()
    expect(screen.getByText("39%")).toBeInTheDocument()
    expect(screen.getByText("61% remaining")).toBeInTheDocument()
    expect(screen.getByText("258K")).toBeInTheDocument()
  })

  it("uses the compact token label when composer controls are compressed", () => {
    render(
      <AgentComposer
        value="Run QC"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        compactControls
        tokenUsageSummary={{
          has_token_usage: true,
          input_tokens: 10_000,
          output_tokens: 2_400,
          total_tokens: 12_400,
          context_window: null,
          max_output_tokens: null,
          turns_with_usage: 1,
          raw_totals: {},
        }}
      />,
    )

    expect(screen.getByRole("button", { name: /12.4K tokens used/ })).toHaveTextContent(
      "12.4K",
    )
    expect(screen.queryByText("12.4K tokens")).not.toBeInTheDocument()
  })

  it("surfaces selected remote connection changes", async () => {
    const onRemoteConnectionChange = vi.fn()
    apiRequestMock.mockResolvedValueOnce({ data: composerConnections })

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
        selectedRemoteConnectionId="connection-sim-224"
        onRemoteConnectionChange={onRemoteConnectionChange}
      />,
    )

    fireEvent.pointerDown(
      await screen.findByRole("button", {
        name: "Current execution target: Simulation host sz01 at 10.227.5.224, Online",
      }),
    )
    fireEvent.click(await screen.findByText("Test host sz03"))

    expect(onRemoteConnectionChange).toHaveBeenCalledWith("connection-test-231")
  })
})

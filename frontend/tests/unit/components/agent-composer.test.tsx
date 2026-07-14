import { readFileSync } from "node:fs"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AgentComposer } from "@/components/bioinfoflow/agent-runtime/agent-composer"
import { apiRequest } from "@/lib/api"

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
}))

vi.mock("next-intl", () => ({
  useLocale: () => "en",
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
      "permission.boundary.local": "Local actions remain inside the active Bioinfoflow sandbox.",
      "permission.boundary.remote": "SSH actions use the remote account and server policy; the working folder is not a sandbox.",
      "permission.safetyFloor": "Critical actions remain blocked in every mode.",
      "permission.status.updating": "Updating permission mode...",
      "permission.status.updated": "Permission mode updated for future operations.",
      "permission.status.reconciled": `${values?.affected ?? "0"} waiting operations approved; ${values?.excluded ?? "0"} excluded.`,
      "permission.status.failed": "Could not update permission mode: Network unavailable",
      "permission.retry": "Retry permission update",
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
      "skills.menuTitle": "Skills",
      "skills.loading": "Loading skills...",
      "skills.empty": "No skills found.",
      "skills.noMatches": "No matching skills.",
      "skills.loadFailed": "Could not load skills.",
      "skills.remove": `Remove ${values?.name ?? ""}`,
      "skills.activeForNextTurn": "Skills",
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

const composerModels = [
  {
    provider: "provider-openai",
    provider_kind: "openai",
    label: "OpenAI",
    base_url: "https://api.openai.com/v1",
    models: [
      {
        id: "gpt-4o-mini",
        name: "GPT-4o mini",
        context_window: 128000,
      },
    ],
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

    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
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

  it("selects a slash skill without submitting the slash token", () => {
    const onChange = vi.fn()
    const onAddActiveSkill = vi.fn()
    render(
      <AgentComposer
        value="/next"
        onChange={onChange}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        availableSkills={[
          {
            name: "nextflow-debugging",
            version: "0.1.0",
            description: "Diagnose failed Nextflow runs.",
            tags: ["nextflow"],
          },
        ]}
        onAddActiveSkill={onAddActiveSkill}
      />,
    )

    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    textarea.setSelectionRange(5, 5)
    fireEvent.click(textarea)
    fireEvent.click(screen.getByTestId("agent-skill-option"))

    expect(onAddActiveSkill).toHaveBeenCalledWith("nextflow-debugging")
    expect(onChange).toHaveBeenCalledWith("")
  })

  it("renders active skill chips and removes them", () => {
    const onRemoveActiveSkill = vi.fn()
    render(
      <AgentComposer
        value="Analyze this run"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        availableSkills={[
          {
            name: "run-failure-triage",
            version: "0.1.0",
            description: "Collect run evidence.",
            tags: ["runs"],
          },
        ]}
        activeSkillNames={["run-failure-triage"]}
        onRemoveActiveSkill={onRemoveActiveSkill}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Remove run-failure-triage" }))

    expect(screen.getByText("/run-failure-triage")).toBeInTheDocument()
    expect(onRemoveActiveSkill).toHaveBeenCalledWith("run-failure-triage")
  })

  it("names the textarea independently from the visible placeholder", () => {
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
      />,
    )

    expect(
      screen.getByRole("textbox", { name: "Message Bioinfoflow..." }),
    ).toBeInTheDocument()
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

  it("renders a centered composer context row when provided", () => {
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
        presentation="center"
        contextTitle="Cancer Cohort"
      />,
    )

    expect(screen.getByTestId("agent-composer")).toHaveAttribute(
      "data-presentation",
      "center",
    )
    expect(screen.getByText("Cancer Cohort")).toHaveClass("min-w-0", "truncate")
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

  it("exposes permission choices as an accessible radio group", async () => {
    render(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        permissionMode="guarded_auto"
        onPermissionModeChange={vi.fn()}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )

    fireEvent.pointerDown(screen.getByRole("button", { name: "Permission mode" }))

    const choices = await screen.findAllByRole("menuitemradio")
    expect(choices).toHaveLength(3)
    expect(screen.getByRole("menuitemradio", { name: /Approve for me/ })).toHaveAttribute(
      "aria-checked",
      "true",
    )
    expect(screen.getByRole("menuitemradio", { name: /Full access/ })).toHaveAttribute(
      "aria-checked",
      "false",
    )
  })

  it("disables the permission transaction while busy and announces its status", async () => {
    render(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        permissionMode="bypass"
        onPermissionModeChange={vi.fn()}
        permissionUpdate={{
          status: "pending",
          mode: "bypass",
          pendingStrategy: "future_only",
          reconciliation: null,
          error: null,
        }}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )

    const trigger = screen.getByRole("button", { name: "Permission mode" })
    expect(trigger).not.toBeDisabled()
    expect(trigger).toHaveAttribute("aria-disabled", "true")
    expect(trigger).toHaveClass("cursor-wait", "opacity-60")
    expect(trigger).toHaveAttribute("aria-busy", "true")
    expect(screen.getByRole("status")).toHaveTextContent("Updating permission mode...")
  })

  it("keeps focus on the permission trigger while an async update is pending", async () => {
    const user = userEvent.setup()

    function PermissionHarness() {
      const [mode, setMode] = useState<"guarded_auto" | "bypass">("guarded_auto")
      const [pending, setPending] = useState(false)
      return (
        <AgentComposer
          value=""
          onChange={vi.fn()}
          onSubmit={vi.fn()}
          onStop={vi.fn()}
          isRunning={false}
          permissionMode={mode}
          onPermissionModeChange={(nextMode) => {
            setMode(nextMode as "guarded_auto" | "bypass")
            setPending(true)
          }}
          permissionUpdate={{
            status: pending ? "pending" : "idle",
            mode: pending ? mode : null,
            pendingStrategy: pending ? "future_only" : null,
            reconciliation: null,
            error: null,
          }}
          models={[]}
          selectedModel={null}
          onSelectModel={vi.fn()}
        />
      )
    }

    render(<PermissionHarness />)
    const trigger = screen.getByRole("button", { name: "Permission mode" })
    await user.click(trigger)
    await user.click(screen.getByRole("menuitemradio", { name: /Full access/ }))

    expect(trigger).toHaveFocus()
    expect(trigger).not.toBeDisabled()
    expect(trigger).toHaveAttribute("aria-disabled", "true")
    await user.keyboard("{Enter}")
    expect(screen.queryByRole("menuitemradio")).not.toBeInTheDocument()
    await user.keyboard("{ArrowDown}")
    expect(screen.queryByRole("menuitemradio")).not.toBeInTheDocument()
  })

  it("keeps permission failures local and exposes a retry action", () => {
    const onRetry = vi.fn()
    render(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        permissionMode="guarded_auto"
        onPermissionModeChange={vi.fn()}
        permissionUpdate={{
          status: "error",
          mode: "bypass",
          pendingStrategy: "future_only",
          reconciliation: null,
          error: "Network unavailable",
        }}
        onRetryPermissionModeChange={onRetry}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Could not update permission mode: Network unavailable",
    )
    fireEvent.click(screen.getByRole("button", { name: "Retry permission update" }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it("describes local and remote authority boundaries without weakening the safety floor", async () => {
    const { rerender } = render(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        permissionMode="bypass"
        onPermissionModeChange={vi.fn()}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )

    fireEvent.pointerDown(screen.getByRole("button", { name: "Permission mode" }))
    expect(await screen.findByText(/Local actions remain inside/)).toBeInTheDocument()
    expect(screen.getByText("Critical actions remain blocked in every mode.")).toBeInTheDocument()
    fireEvent.keyDown(document, { key: "Escape" })

    rerender(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        permissionMode="bypass"
        onPermissionModeChange={vi.fn()}
        selectedRemoteConnectionId="connection-1"
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )
    fireEvent.pointerDown(screen.getByRole("button", { name: "Permission mode" }))
    expect(await screen.findByText(/SSH actions use the remote account/)).toBeInTheDocument()
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

    const permissionButton = screen.getByRole("button", { name: "Permission mode" })
    expect(permissionButton).toBeVisible()
    expect(permissionButton).not.toHaveClass("hidden")
    expect(screen.getByRole("button", { name: "Agent mode" })).toBeVisible()
    expect(screen.getByRole("link", { name: "Configure providers" })).toBeVisible()
    expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled()
  })

  it("renders composer controls as a neutral toolbar with sparse mode color", () => {
    render(
      <AgentComposer
        value="Run QC"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        permissionMode="guarded_auto"
        onPermissionModeChange={vi.fn()}
        mode="plan"
        onModeChange={vi.fn()}
        models={composerModels}
        selectedModel={{ provider: "provider-openai", model: "gpt-4o-mini" }}
        onSelectModel={vi.fn()}
      />,
    )

    const locationChip = screen.getByRole("button", {
      name: "Current execution target: local",
    })
    expect(locationChip).toHaveAttribute("data-composer-chip", "true")
    expect(locationChip).toHaveClass("min-h-7", "rounded-[8px]", "bg-transparent")

    const permissionChip = screen.getByRole("button", { name: "Permission mode" })
    expect(permissionChip).toHaveAttribute("data-composer-chip", "true")
    expect(permissionChip).toHaveClass("min-h-7", "rounded-[8px]", "bg-transparent")

    const modeChip = screen.getByTestId("agent-mode-chip")
    expect(modeChip).toHaveAttribute("data-composer-chip", "true")
    expect(modeChip).toHaveAttribute("data-mode", "plan")
    expect(modeChip).toHaveClass("min-h-7", "rounded-[8px]", "bg-[#f7ead3]")
    expect(screen.getByTestId("agent-mode-chip-marker")).toHaveClass("bg-[#b87924]")

    const modelChip = screen.getByRole("combobox", { name: "GPT-4o mini" })
    expect(modelChip).toHaveAttribute("data-composer-chip", "true")
    expect(modelChip).toHaveClass("min-h-7", "rounded-[8px]", "bg-transparent")

    const sendButton = screen.getByRole("button", { name: "Send message" })
    expect(sendButton).toHaveClass("bg-primary")
    expect(sendButton.getAttribute("class")).not.toContain("f54e00")
    expect(sendButton.getAttribute("class")).not.toContain("d04200")
  })

  it("does not hard-code orange into composer primary actions", () => {
    const composerSource = readFileSync(
      "components/bioinfoflow/agent-runtime/agent-composer.tsx",
      "utf8",
    )

    for (const forbiddenHex of ["f54e" + "00", "d042" + "00"]) {
      expect(composerSource).not.toContain(forbiddenHex)
    }
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
    const modeChipShell = screen.getByTestId("agent-mode-chip-shell")
    expect(modeChipShell).toHaveClass("hidden", "sm:inline-flex")
    expect(screen.getByRole("button", { name: "Agent mode" })).toHaveClass("max-w-9")
    expect(screen.getByRole("link", { name: "Configure providers" })).toHaveClass("max-w-9")
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

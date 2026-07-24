import { readFileSync } from "node:fs"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AgentComposer } from "@/components/bioinfoflow/agent-runtime/agent-composer"
import { apiRequest } from "@/lib/api"
import { getSpeechStatus, transcribeSpeech } from "@/lib/speech"

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
}))

vi.mock("@/lib/speech", () => ({
  getSpeechStatus: vi.fn(),
  transcribeSpeech: vi.fn(),
}))

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    const labels: Record<string, string> = {
      composerPlaceholder: "Message Bioinfoflow...",
      attach: "Attach or add context",
      send: "Send message",
      stop: "Stop response",
      "voice.start": "Start voice input",
      "voice.stop": "Stop recording",
      "voice.recording": `Listening ${values?.time ?? "0:00"}`,
      "voice.transcribing": "Transcribing...",
      "voice.unavailable": "Voice input is unavailable",
      "voice.failed": "Could not transcribe the recording.",
      "voice.cancelled": "Voice recording cancelled.",
      "attachMenu.attachFiles": "Attach files",
      "attachMenu.browseProjectFiles": "Browse project files",
      "attachMenu.referenceRun": "Reference a run",
      "attachMenu.runPreflight": "Run preflight",
      "attachMenu.diagnoseRun": "Diagnose run",
      "attachMenu.comingSoon": "Coming soon",
      "attachMenu.addFileFolder": "Add file/folder",
      "attachMenu.addFiles": "Add files",
      "attachMenu.addFolder": "Add folder",
      "attachments.label": "Attachments",
      "attachments.uploading": "Uploading…",
      "attachments.removing": "Removing…",
      "attachments.uploadFailed": "Upload failed",
      "attachments.preview": `Preview ${values?.name ?? ""}`,
      "attachments.remove": `Remove ${values?.name ?? ""}`,
      "attachments.retry": `Retry ${values?.name ?? ""}`,
      "attachments.delete": `Delete ${values?.name ?? ""}`,
      "attachments.deleteAction": "Delete",
      "attachments.imagePreview": "Image attachment preview",
      "contextSearch.menuTitle": "Files, workflows, and runs",
      "contextSearch.loading": "Searching context…",
      "contextSearch.empty": "Type to search context",
      "contextSearch.noMatches": "No matching context",
      "contextSearch.remove": `Remove ${values?.name ?? ""}`,
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
      "runtimeLocation.placeholder": "Execution targets",
      "runtimeLocation.menuTitle": "Execution targets",
      "runtimeLocation.auto": "Auto",
      "runtimeLocation.manual": "Manual",
      "runtimeLocation.allTargets": "All",
      "runtimeLocation.targetCount": `${values?.count ?? "0"} targets`,
      "runtimeLocation.localBadge": "Local",
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
      "runtimeLocation.selectedAutoAria": "Execution targets: Auto",
      "runtimeLocation.selectedAutoTargetAria": `Execution targets: Auto, current target ${values?.target ?? ""}`,
      "runtimeLocation.selectedManualAria": `Execution targets: Manual, ${values?.target ?? ""}`,
      placeholder: "Execution targets",
      menuTitle: "Execution targets",
      manual: "Manual",
      allTargets: "All",
      targetCount: `${values?.count ?? "0"} targets`,
      localBadge: "Local",
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
      selectedAutoAria: "Execution targets: Auto",
      selectedAutoTargetAria: `Execution targets: Auto, current target ${values?.target ?? ""}`,
      selectedManualAria: `Execution targets: Manual, ${values?.target ?? ""}`,
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
      "workflows.menuTitle": "Workflows",
      "workflows.loading": "Loading workflows...",
      "workflows.empty": "No workflows found.",
      "workflows.noMatches": "No matching workflows.",
      "workflows.loadFailed": "Could not load workflows.",
      "workflows.remove": `Remove ${values?.name ?? ""}`,
      "workflows.activeForNextTurn": "Workflow context",
      "workflows.pinned": "Pinned version",
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
const speechStatusMock = vi.mocked(getSpeechStatus)
const transcribeSpeechMock = vi.mocked(transcribeSpeech)

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
  it("shows separate send and stop controls while a response is running", () => {
    render(
      <AgentComposer
        value="Add one more constraint"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )

    expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "Stop response" })).toBeEnabled()
  })

  beforeEach(() => {
    apiRequestMock.mockReset()
    apiRequestMock.mockReturnValue(new Promise(() => {}))
    speechStatusMock.mockReset()
    speechStatusMock.mockReturnValue(new Promise(() => {}))
    transcribeSpeechMock.mockReset()
  })

  it("records voice, disables send, and inserts editable text without submitting", async () => {
    const onSubmit = vi.fn()
    const trackStop = vi.fn()
    class Recorder {
      static isTypeSupported() { return true }
      state = "inactive"
      mimeType = "audio/webm"
      ondataavailable: ((event: { data: Blob }) => void) | null = null
      onstop: (() => void) | null = null
      start() { this.state = "recording" }
      stop() {
        this.state = "inactive"
        this.ondataavailable?.({ data: new Blob(["voice"], { type: this.mimeType }) })
        this.onstop?.()
      }
    }
    vi.stubGlobal("MediaRecorder", Recorder)
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: trackStop }],
        }),
      },
    })
    speechStatusMock.mockResolvedValueOnce({
      configured: true, available: true, provider: "funasr", model: "fun-asr-nano", language: "zh", message: null,
    })
    transcribeSpeechMock.mockResolvedValueOnce({ text: "检查 FASTQ", language: "zh" })

    function Harness() {
      const [value, setValue] = useState("运行 ")
      return (
        <AgentComposer
          value={value}
          onChange={setValue}
          onSubmit={onSubmit}
          onStop={vi.fn()}
          isRunning={false}
          models={[]}
          selectedModel={null}
          onSelectModel={vi.fn()}
        />
      )
    }

    render(<Harness />)
    const microphone = await screen.findByRole("button", { name: "Start voice input" })
    await waitFor(() => expect(microphone).toBeEnabled())
    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    textarea.setSelectionRange(3, 3)
    fireEvent.click(microphone)
    await screen.findByText("Listening 0:00")
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled()
    fireEvent.change(textarea, { target: { value: "运行 后续" } })

    fireEvent.click(screen.getByRole("button", { name: "Stop recording" }))

    await waitFor(() => expect(textarea).toHaveValue("运行 检查 FASTQ 后续"))
    expect(onSubmit).not.toHaveBeenCalled()
    await waitFor(() => expect(textarea).toHaveFocus())
    expect(trackStop).toHaveBeenCalled()
  })

  it("cancels an active recording with Escape without uploading", async () => {
    class Recorder {
      static isTypeSupported() { return true }
      state = "inactive"
      mimeType = "audio/webm"
      ondataavailable: ((event: { data: Blob }) => void) | null = null
      onstop: (() => void) | null = null
      start() { this.state = "recording" }
      stop() {
        this.state = "inactive"
        this.ondataavailable?.({ data: new Blob(["voice"], { type: this.mimeType }) })
        this.onstop?.()
      }
    }
    vi.stubGlobal("MediaRecorder", Recorder)
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
    })
    speechStatusMock.mockResolvedValueOnce({
      configured: true, available: true, provider: "funasr", model: "fun-asr-nano", language: "zh", message: null,
    })
    render(
      <AgentComposer
        value="draft"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )
    const microphone = await screen.findByRole("button", { name: "Start voice input" })
    await waitFor(() => expect(microphone).toBeEnabled())
    fireEvent.click(microphone)
    await screen.findByText("Listening 0:00")

    const stopButton = screen.getByRole("button", { name: "Stop recording" })
    stopButton.focus()
    fireEvent.keyDown(stopButton, { key: "Escape" })

    await waitFor(() => expect(screen.queryByText("Listening 0:00")).not.toBeInTheDocument())
    expect(transcribeSpeechMock).not.toHaveBeenCalled()
  })

  it("inserts Chinese dictation without adding spaces between Han characters", async () => {
    class Recorder {
      static isTypeSupported() { return true }
      state = "inactive"
      mimeType = "audio/webm"
      ondataavailable: ((event: { data: Blob }) => void) | null = null
      onstop: (() => void) | null = null
      start() { this.state = "recording" }
      stop() {
        this.state = "inactive"
        this.ondataavailable?.({ data: new Blob(["voice"], { type: this.mimeType }) })
        this.onstop?.()
      }
    }
    vi.stubGlobal("MediaRecorder", Recorder)
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
    })
    speechStatusMock.mockResolvedValue({
      configured: true, available: true, provider: "funasr", model: "fun-asr-nano", language: "zh", message: null,
    })
    transcribeSpeechMock.mockResolvedValue({ text: "帮我", language: "zh" })

    function Harness() {
      const [value, setValue] = useState("请继续")
      return <AgentComposer value={value} onChange={setValue} onSubmit={vi.fn()} onStop={vi.fn()} isRunning={false} models={[]} selectedModel={null} onSelectModel={vi.fn()} />
    }
    render(<Harness />)
    const microphone = await screen.findByRole("button", { name: "Start voice input" })
    await waitFor(() => expect(microphone).toBeEnabled())
    const textarea = screen.getByRole("textbox")
    textarea.setSelectionRange(1, 1)
    fireEvent.click(microphone)
    await screen.findByRole("button", { name: "Stop recording" })
    fireEvent.click(screen.getByRole("button", { name: "Stop recording" }))

    await waitFor(() => expect(textarea).toHaveValue("请帮我继续"))
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
    vi.unstubAllGlobals()
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

  it("renders active skill tokens inside the composer input surface and removes them", () => {
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

    const tokenFlow = screen.getByTestId("agent-inline-token-flow")
    expect(screen.queryByTestId("agent-active-skills")).not.toBeInTheDocument()
    expect(within(tokenFlow).getByText("/run-failure-triage")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Remove run-failure-triage" }))
    expect(onRemoveActiveSkill).toHaveBeenCalledWith("run-failure-triage")
  })

  it("renders inline tokens in the caller-provided insertion order", () => {
    const skill = {
      name: "phoenix-platform-operator",
      version: "0.1.0",
      description: "Operate Phoenix platform workflows.",
      tags: ["phoenix"],
    }
    const workflow = {
      id: "workflow-deaf-20",
      name: "Deaf_20",
      version: "2.0.9.9",
      engine: "nextflow",
      source: "local",
      description: "Deaf workflow.",
      scope: "global" as const,
      projectId: null,
    }

    render(
      <AgentComposer
        value="我想"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        availableSkills={[skill]}
        activeSkillNames={[skill.name]}
        activeWorkflowMentions={[workflow]}
        activeComposerTokens={[
          { kind: "skill", skill },
          { kind: "workflow", workflow },
        ]}
      />,
    )

    const tokenFlow = screen.getByTestId("agent-inline-token-flow")
    const skillToken = within(tokenFlow).getByTestId("agent-inline-skill-token")
    const workflowToken = within(tokenFlow).getByTestId("agent-inline-workflow-token")
    expect(
      skillToken.compareDocumentPosition(workflowToken) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it("opens the unified command menu for slash skills and workflow mentions", () => {
    const { rerender } = render(
      <AgentComposer
        value="/next"
        onChange={vi.fn()}
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
        availableWorkflowMentions={[
          {
            id: "workflow-rna-12",
            name: "rnaseq-quant-mini",
            version: "1.2.0",
            engine: "nextflow",
            source: "local",
            description: "RNA-seq quantification.",
            scope: "global",
            projectId: null,
          },
        ]}
        onAddActiveSkill={vi.fn()}
        onAddWorkflowMention={vi.fn()}
      />,
    )

    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    textarea.setSelectionRange(5, 5)
    fireEvent.click(textarea)

    expect(screen.getByTestId("agent-command-menu")).toBeInTheDocument()
    expect(screen.getByTestId("agent-command-option")).toHaveTextContent(
      "/nextflow-debugging",
    )

    rerender(
      <AgentComposer
        value="@rna"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        availableSkills={[]}
        availableWorkflowMentions={[
          {
            id: "workflow-rna-12",
            name: "rnaseq-quant-mini",
            version: "1.2.0",
            engine: "nextflow",
            source: "local",
            description: "RNA-seq quantification.",
            scope: "global",
            projectId: null,
          },
        ]}
        onAddActiveSkill={vi.fn()}
        onAddWorkflowMention={vi.fn()}
      />,
    )
    const nextTextarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    nextTextarea.setSelectionRange(4, 4)
    fireEvent.click(nextTextarea)

    expect(screen.getByTestId("agent-command-menu")).toBeInTheDocument()
    expect(screen.getByTestId("agent-command-option")).toHaveTextContent(
      "@rnaseq-quant-mini",
    )
  })

  it("connects the command listbox and highlighted option to the textarea", () => {
    render(
      <AgentComposer
        value="/"
        onChange={vi.fn()}
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
          {
            name: "run-failure-triage",
            version: "0.1.0",
            description: "Collect run evidence.",
            tags: ["runs"],
          },
        ]}
        onAddActiveSkill={vi.fn()}
      />,
    )

    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    textarea.setSelectionRange(1, 1)
    fireEvent.click(textarea)

    const menu = screen.getByTestId("agent-command-menu")
    const options = screen.getAllByTestId("agent-command-option")
    expect(textarea).toHaveAttribute("aria-haspopup", "listbox")
    expect(textarea).toHaveAttribute("aria-expanded", "true")
    expect(textarea).toHaveAttribute("aria-controls", menu.id)
    expect(textarea).toHaveAttribute("aria-activedescendant", options[0]!.id)

    fireEvent.keyDown(textarea, { key: "ArrowDown" })
    expect(textarea).toHaveAttribute("aria-activedescendant", options[1]!.id)
  })

  it("localizes the pinned workflow option detail", () => {
    render(
      <AgentComposer
        value="@rna"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        availableWorkflowMentions={[
          {
            id: "workflow-rna-12",
            name: "rnaseq-quant-mini",
            version: "1.2.0",
            engine: "nextflow",
            source: "local",
            description: "RNA-seq quantification.",
            scope: "global",
            projectId: null,
            pinned: true,
          },
        ]}
        onAddWorkflowMention={vi.fn()}
      />,
    )

    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    textarea.setSelectionRange(4, 4)
    fireEvent.click(textarea)

    expect(screen.getByTestId("agent-command-option")).toHaveTextContent(
      "Pinned version",
    )
  })

  it("selects and removes a workflow mention token inside the composer input surface", () => {
    function WorkflowMentionHarness() {
      const [value, setValue] = useState("@rna")
      const [mentions, setMentions] = useState<Array<{
        id: string
        name: string
        version: string
        engine: "nextflow"
        source: "local"
        description: string
        scope: "global"
        projectId: null
      }>>([])
      const workflow = {
        id: "workflow-rna-12",
        name: "rnaseq-quant-mini",
        version: "1.2.0",
        engine: "nextflow" as const,
        source: "local" as const,
        description: "RNA-seq quantification.",
        scope: "global" as const,
        projectId: null,
      }

      return (
        <AgentComposer
          value={value}
          onChange={setValue}
          onSubmit={vi.fn()}
          onStop={vi.fn()}
          isRunning={false}
          models={[]}
          selectedModel={null}
          onSelectModel={vi.fn()}
          availableWorkflowMentions={[workflow]}
          activeWorkflowMentions={mentions}
          onAddWorkflowMention={(mention) =>
            setMentions((current) =>
              current.some((item) => item.id === mention.id)
                ? current
                : [...current, mention],
            )
          }
          onRemoveWorkflowMention={(workflowId) =>
            setMentions((current) => current.filter((item) => item.id !== workflowId))
          }
        />
      )
    }

    render(<WorkflowMentionHarness />)

    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    textarea.setSelectionRange(4, 4)
    fireEvent.click(textarea)
    fireEvent.click(screen.getByTestId("agent-command-option"))

    expect(textarea).toHaveValue("")
    const tokenFlow = screen.getByTestId("agent-inline-token-flow")
    expect(screen.queryByTestId("agent-active-workflows")).not.toBeInTheDocument()
    expect(within(tokenFlow).getByText("@rnaseq-quant-mini")).toBeInTheDocument()
    expect(within(tokenFlow).getByText("1.2.0")).toHaveAttribute(
      "title",
      "rnaseq-quant-mini 1.2.0",
    )

    fireEvent.click(screen.getByRole("button", { name: "Remove rnaseq-quant-mini 1.2.0" }))
    expect(screen.queryByText("@rnaseq-quant-mini")).not.toBeInTheDocument()
  })

  it("removes the previous inline token with backspace at the input start", () => {
    const onRemoveWorkflowMention = vi.fn()
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
        activeWorkflowMentions={[
          {
            id: "workflow-rna-12",
            name: "rnaseq-quant-mini",
            version: "1.2.0",
            engine: "nextflow",
            source: "local",
            description: "RNA-seq quantification.",
            scope: "global",
            projectId: null,
          },
        ]}
        onRemoveWorkflowMention={onRemoveWorkflowMention}
      />,
    )

    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    textarea.setSelectionRange(0, 0)
    fireEvent.keyDown(textarea, { key: "Backspace" })

    expect(onRemoveWorkflowMention).toHaveBeenCalledWith("workflow-rna-12")
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

  it("types, pauses, deletes faster, and advances to the next placeholder", () => {
    vi.useFakeTimers()
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
        placeholderSuggestions={["AB", "CD"]}
      />,
    )

    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    expect(textarea).toHaveAttribute("placeholder", "")

    act(() => vi.advanceTimersByTime(80))
    expect(textarea).toHaveAttribute("placeholder", "A")

    act(() => vi.advanceTimersByTime(80))
    expect(textarea).toHaveAttribute("placeholder", "AB")

    act(() => vi.advanceTimersByTime(1_399))
    expect(textarea).toHaveAttribute("placeholder", "AB")

    act(() => vi.advanceTimersByTime(1))
    act(() => vi.advanceTimersByTime(35))
    expect(textarea).toHaveAttribute("placeholder", "A")

    act(() => vi.advanceTimersByTime(35))
    act(() => vi.advanceTimersByTime(300))
    act(() => vi.advanceTimersByTime(80))
    expect(textarea).toHaveAttribute("placeholder", "C")
    expect(textarea).toHaveAttribute("aria-label", "Message Bioinfoflow...")

    act(() => vi.advanceTimersByTime(80))
    act(() => vi.advanceTimersByTime(1_400))
    act(() => vi.advanceTimersByTime(35))
    act(() => vi.advanceTimersByTime(35))
    act(() => vi.advanceTimersByTime(300))
    act(() => vi.advanceTimersByTime(80))
    expect(textarea).toHaveAttribute("placeholder", "A")
  })

  it("stops placeholder animation while focused or while the composer has a value", () => {
    vi.useFakeTimers()
    const { rerender } = render(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        placeholderSuggestions={["AB", "CD"]}
      />,
    )

    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    act(() => vi.advanceTimersByTime(80))
    expect(textarea).toHaveAttribute("placeholder", "A")

    fireEvent.focus(textarea)
    expect(textarea).toHaveAttribute("placeholder", "AB")
    act(() => vi.advanceTimersByTime(5_000))
    expect(textarea).toHaveAttribute("placeholder", "AB")

    fireEvent.blur(textarea)
    rerender(
      <AgentComposer
        value="already writing"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        placeholderSuggestions={["AB", "CD"]}
      />,
    )
    expect(textarea).toHaveAttribute("placeholder", "AB")
    act(() => vi.advanceTimersByTime(5_000))
    expect(textarea).toHaveAttribute("placeholder", "AB")
  })

  it("uses one complete stable placeholder when reduced motion is preferred", () => {
    vi.useFakeTimers()
    const setTimeoutSpy = vi.spyOn(window, "setTimeout")
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

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
        placeholderSuggestions={["Complete prompt", "Another prompt"]}
      />,
    )

    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    expect(textarea).toHaveAttribute("placeholder", "Complete prompt")
    expect(setTimeoutSpy).not.toHaveBeenCalledWith(expect.any(Function), 80)
    act(() => vi.advanceTimersByTime(10_000))
    expect(textarea).toHaveAttribute("placeholder", "Complete prompt")
  })

  it("cleans the active placeholder timer after unmount", () => {
    vi.useFakeTimers()
    const setTimeoutSpy = vi.spyOn(window, "setTimeout")
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")
    const { unmount } = render(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        placeholderSuggestions={["First prompt", "Second prompt"]}
      />,
    )

    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 80)
    const timer = setTimeoutSpy.mock.results.at(-1)?.value
    unmount()
    expect(clearTimeoutSpy).toHaveBeenCalledWith(timer)
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
        executionSelection={{ mode: "manual", targetIds: ["connection-1"] }}
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
      name: "Execution targets: Auto",
    })
    expect(locationChip).toHaveAttribute("data-composer-chip", "true")
    expect(locationChip).toHaveClass("min-h-7", "rounded-[8px]", "bg-muted/35")

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

  it("surfaces manual execution target changes", async () => {
    const onExecutionSelectionChange = vi.fn()
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
        executionSelection={{ mode: "manual", targetIds: ["connection-sim-224"] }}
        onExecutionSelectionChange={onExecutionSelectionChange}
      />,
    )

    fireEvent.pointerDown(
      await screen.findByRole("button", {
        name: "Execution targets: Manual, Simulation host sz01",
      }),
    )
    fireEvent.click(await screen.findByText("Test host sz03"))

    expect(onExecutionSelectionChange).toHaveBeenCalledWith({
      mode: "manual",
      targetIds: ["connection-sim-224", "connection-test-231"],
    })
  })

  it("uses one add-file entry with file and folder secondary actions", async () => {
    const user = userEvent.setup()
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
        onAddFiles={vi.fn()}
        onAddFolder={vi.fn()}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Attach or add context" }))
    expect(screen.getByRole("menuitem", { name: "Add file/folder" })).toBeInTheDocument()
    expect(screen.queryByRole("menuitem", { name: "Reference a run" })).not.toBeInTheDocument()

    await user.click(screen.getByRole("menuitem", { name: "Add file/folder" }))
    expect(screen.getByRole("menuitem", { name: "Add files" })).toBeInTheDocument()
    expect(screen.getByRole("menuitem", { name: "Add folder" })).toBeInTheDocument()
  })

  it("uploads pasted images and preserves clipboard text on macOS and Windows", () => {
    const onChange = vi.fn()
    const onPasteImages = vi.fn()
    render(
      <AgentComposer
        value="Review: "
        onChange={onChange}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        onPasteImages={onPasteImages}
      />,
    )
    const image = new File(["png"], "clipboard.png", { type: "image/png" })
    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    ;(textarea as HTMLTextAreaElement).setSelectionRange(8, 8)
    fireEvent.paste(textarea, {
      clipboardData: {
        files: [image],
        getData: (type: string) => (type === "text/plain" ? "check this" : ""),
      },
    })

    expect(onPasteImages).toHaveBeenCalledWith([image])
    expect(onChange).toHaveBeenCalledWith("Review: check this")
  })

  it("allows ready attachment-only sends but blocks unresolved uploads", () => {
    const onSubmit = vi.fn()
    const { rerender } = render(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={onSubmit}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        attachments={[
          {
            id: "image-1",
            filename: "clipboard.png",
            kind: "image",
            status: "ready",
            previewUrl: "/preview/image-1",
          },
        ]}
        onRemoveAttachment={vi.fn()}
      />,
    )
    expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled()

    rerender(
      <AgentComposer
        value=""
        onChange={vi.fn()}
        onSubmit={onSubmit}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        attachments={[
          {
            id: "image-1",
            filename: "clipboard.png",
            kind: "image",
            status: "uploading",
          },
        ]}
        onRemoveAttachment={vi.fn()}
      />,
    )
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled()
  })

  it("searches server context for @ mentions and selects a structured reference", async () => {
    const onAddContextMention = vi.fn()
    const onSearchContext = vi.fn().mockResolvedValue({
      results: [
        {
          id: "file:src/main.py",
          kind: "file",
          label: "main.py",
          detail: "src/main.py",
          input_part: { type: "file_ref", path: "src/main.py" },
        },
      ],
      counts: { file: 1 },
      next_cursor: null,
    })
    render(
      <AgentComposer
        value="@mai"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        onSearchContext={onSearchContext}
        onAddContextMention={onAddContextMention}
      />,
    )
    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    ;(textarea as HTMLTextAreaElement).setSelectionRange(4, 4)
    fireEvent.click(textarea)

    expect(await screen.findByRole("option", { name: /main.py/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("option", { name: /main.py/ }))
    expect(onAddContextMention).toHaveBeenCalledWith(
      expect.objectContaining({ id: "file:src/main.py" }),
    )
  })

  it("treats a malformed context search response as an empty result", async () => {
    const onSearchContext = vi.fn().mockResolvedValue({ data: [] })
    render(
      <AgentComposer
        value="@missing"
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isRunning={false}
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
        onSearchContext={onSearchContext}
        onAddContextMention={vi.fn()}
      />,
    )
    const textarea = screen.getByRole("textbox", { name: "Message Bioinfoflow..." })
    ;(textarea as HTMLTextAreaElement).setSelectionRange(8, 8)
    fireEvent.click(textarea)

    await waitFor(() => expect(onSearchContext).toHaveBeenCalledTimes(1))
    expect(await screen.findByTestId("agent-context-menu-empty")).toHaveTextContent(
      "No matching context",
    )
    expect(screen.queryByRole("option")).not.toBeInTheDocument()
  })
})

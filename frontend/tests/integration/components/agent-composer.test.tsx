import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState, type ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { AgentComposer } from "@/components/bioinfoflow/agent/agent-composer"
import type {
  AgentEnvironmentSelection,
  AgentEnvironmentTarget,
} from "@/components/bioinfoflow/agent/environment-selector"
import type {
  ActiveRunView,
  AgentPermissionMode,
  AgentWorkspaceAccess,
  InputPart,
} from "@/lib/agent/contracts"
import type { AgentContextInput } from "@/lib/agent/context"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => {
    const copy: Record<string, string> = {
      "agentComposer.label": "Message the agent",
      "agentComposer.placeholder": "Ask Bioinfoflow to do something…",
      "agentComposer.send": "Send message",
      "agentComposer.queue": "Queue message",
      "agentComposer.steer": "Steer active run",
      "agentComposer.stop": "Stop run",
      "agentComposer.stopping": "Stopping…",
      "agentComposer.sending": "Sending…",
      "agentComposer.steering": "Steering…",
      "agentComposer.submitError":
        "The message could not be submitted. Try again.",
      "agentComposer.stopError": "The run could not be stopped. Try again.",
      "agentComposer.permission.label": "Approval mode",
      "agentComposer.permission.title": "How should agent actions be approved?",
      "agentComposer.permission.ask_changes.name": "Ask before changes",
      "agentComposer.permission.ask_changes.description":
        "Ask before files, network, or other side effects change.",
      "agentComposer.permission.ask_dangerous.name": "Approve safe actions",
      "agentComposer.permission.ask_dangerous.description":
        "Only ask for dangerous or critical actions.",
      "agentComposer.permission.full_access.name": "Full access",
      "agentComposer.permission.full_access.description":
        "Run automatically inside hard workspace and safety limits.",
      "agentComposer.permission.activeRun":
        "Approval mode cannot change while a run is active.",
      "agentComposer.permission.nextRun": "Changes apply to the next run.",
      "agentComposer.permission.readOnlyWorkspace":
        "This workspace is read-only. Approval mode cannot grant write access.",
      "agentComposer.permission.updating": "Updating approval mode…",
      "agentComposer.permission.updateError":
        "Approval mode could not be updated.",
      "agentComposer.permission.retry": "Retry approval update",
      "agentComposer.environment.label": "Execution environments",
      "agentComposer.environment.title": "Choose visible environments",
      "agentComposer.environment.auto.name": "Auto",
      "agentComposer.environment.auto.description":
        "Let the agent use any available environment.",
      "agentComposer.environment.manual.name": "Manual",
      "agentComposer.environment.manual.description":
        "Limit the agent to selected environments.",
      "agentComposer.environment.local": "Local",
      "agentComposer.environment.targetCount": "{count} environments",
      "agentComposer.environment.updating": "Updating environments…",
      "agentComposer.environment.updateError":
        "Environments could not be updated.",
      "agentComposer.environment.retry": "Retry environment update",
      "agentComposer.environment.status.online": "Online",
      "agentComposer.environment.status.offline": "Offline",
      "agentComposer.environment.status.error": "Error",
      "agentComposer.environment.status.unknown": "Unknown",
      "agentComposer.starterHint": "Try one of these project-aware prompts",
    }
    return copy[`${namespace}.${key}`] ?? `${namespace}.${key}`
  },
}))

const timestamp = "2026-08-15T00:00:00Z"

function activeRun(): ActiveRunView {
  return {
    run: {
      id: "run-1",
      session_id: "session-1",
      status: "running",
      phase: "model",
      revision: 1,
      started_at: timestamp,
      completed_at: null,
      termination_reason: null,
      error: null,
      created_at: timestamp,
      updated_at: timestamp,
    },
    assistant_draft: null,
    tool_progress: [],
    pending_interaction: null,
  }
}

function renderComposer({
  permissionMode = "ask_dangerous",
  workspaceAccess = "read_write",
  currentRun = null,
  onSendMessage = vi.fn().mockResolvedValue(undefined),
  onSteer = vi.fn().mockResolvedValue(undefined),
  onCancel = vi.fn().mockResolvedValue(undefined),
  onPermissionModeChange = vi.fn().mockResolvedValue(undefined),
  contextInputs = [],
  onRemoveContextInput = vi.fn(),
  onContextSubmitted = vi.fn(),
  disabled = false,
  placement = "dock",
  modelControls,
  environmentTargets,
  environmentSelection,
  effectiveEnvironmentSelection,
  environmentSelectionPending = false,
  onEnvironmentSelectionChange = vi.fn().mockResolvedValue(undefined),
  starterPrompts,
  capabilityHint,
}: {
  permissionMode?: AgentPermissionMode
  workspaceAccess?: AgentWorkspaceAccess
  currentRun?: ActiveRunView | null
  onSendMessage?: (parts: InputPart[]) => Promise<void>
  onSteer?: (parts: InputPart[]) => Promise<void>
  onCancel?: () => Promise<void>
  onPermissionModeChange?: (mode: AgentPermissionMode) => Promise<void>
  contextInputs?: AgentContextInput[]
  onRemoveContextInput?: (inputId: string) => void
  onContextSubmitted?: () => void
  disabled?: boolean
  placement?: "draft" | "dock"
  modelControls?: ReactNode
  environmentTargets?: AgentEnvironmentTarget[]
  environmentSelection?: AgentEnvironmentSelection
  effectiveEnvironmentSelection?: AgentEnvironmentSelection
  environmentSelectionPending?: boolean
  onEnvironmentSelectionChange?: (
    selection: AgentEnvironmentSelection,
  ) => Promise<void>
  starterPrompts?: readonly string[]
  capabilityHint?: string
} = {}) {
  return {
    ...renderWithProviders(
      <AgentComposer
        permissionMode={permissionMode}
        workspaceAccess={workspaceAccess}
        activeRun={currentRun}
        onSendMessage={onSendMessage}
        onSteer={onSteer}
        onCancel={onCancel}
        onPermissionModeChange={onPermissionModeChange}
        contextInputs={contextInputs}
        onRemoveContextInput={onRemoveContextInput}
        onContextSubmitted={onContextSubmitted}
        disabled={disabled}
        placement={placement}
        modelControls={modelControls}
        environmentTargets={environmentTargets}
        environmentSelection={environmentSelection}
        effectiveEnvironmentSelection={effectiveEnvironmentSelection}
        environmentSelectionPending={environmentSelectionPending}
        onEnvironmentSelectionChange={onEnvironmentSelectionChange}
        starterPrompts={starterPrompts}
        capabilityHint={capabilityHint}
      />,
    ),
    onSendMessage,
    onSteer,
    onCancel,
    onPermissionModeChange,
    onRemoveContextInput,
    onContextSubmitted,
  }
}

describe("AgentComposer", () => {
  it("uses a centered draft surface and a compact docked surface without changing behavior", () => {
    const view = renderComposer({
      placement: "draft",
      modelControls: <button type="button">GPT-5.6</button>,
    })

    expect(screen.getByTestId("agent-composer")).toHaveAttribute(
      "data-placement",
      "draft",
    )
    expect(
      screen.getByRole("textbox", { name: "Message the agent" }),
    ).toHaveAttribute("rows", "3")
    expect(screen.getByRole("button", { name: "GPT-5.6" })).toBeInTheDocument()
    expect(screen.getByTestId("agent-composer")).not.toHaveClass(
      "bg-gradient-to-t",
    )
    expect(screen.getByTestId("agent-composer-surface")).not.toHaveClass(
      "shadow-md",
    )
    expect(
      screen.getByRole("textbox", { name: "Message the agent" }),
    ).toHaveClass("dark:bg-transparent")

    view.rerender(
      <AgentComposer
        permissionMode="ask_dangerous"
        workspaceAccess="read_write"
        activeRun={null}
        onSendMessage={view.onSendMessage}
        onSteer={view.onSteer}
        onCancel={view.onCancel}
        onPermissionModeChange={view.onPermissionModeChange}
        placement="dock"
      />,
    )

    expect(screen.getByTestId("agent-composer")).toHaveAttribute(
      "data-placement",
      "dock",
    )
    expect(
      screen.getByRole("textbox", { name: "Message the agent" }),
    ).toHaveAttribute("rows", "2")
    expect(screen.getByTestId("agent-composer")).not.toHaveClass(
      "bg-gradient-to-t",
    )
  })

  it("shows starter prompts only in the draft and moves a selected prompt into the editor", async () => {
    const user = userEvent.setup()
    const view = renderComposer({
      placement: "draft",
      starterPrompts: ["Review the latest run", "Explain the workflow inputs"],
    })

    expect(
      screen.getByText("Try one of these project-aware prompts"),
    ).toBeInTheDocument()
    await user.click(
      screen.getByRole("button", { name: "Review the latest run" }),
    )
    expect(
      screen.getByRole("textbox", { name: "Message the agent" }),
    ).toHaveValue("Review the latest run")

    view.rerender(
      <AgentComposer
        permissionMode="ask_dangerous"
        workspaceAccess="read_write"
        activeRun={null}
        onSendMessage={view.onSendMessage}
        onSteer={view.onSteer}
        onCancel={view.onCancel}
        onPermissionModeChange={view.onPermissionModeChange}
        placement="dock"
        starterPrompts={["Review the latest run"]}
      />,
    )

    expect(
      screen.queryByText("Try one of these project-aware prompts"),
    ).not.toBeInTheDocument()
  })

  it("shows a distinct, honest capability hint only in the draft", () => {
    const capabilityHint =
      "The agent can work in this project and the environments you authorize. Actions that require approval will pause and ask first."
    const view = renderComposer({ placement: "draft", capabilityHint })

    expect(screen.getByTestId("agent-capability-hint")).toHaveTextContent(
      capabilityHint,
    )
    expect(screen.getByTestId("agent-capability-hint")).not.toHaveAttribute(
      "aria-label",
      "Try one of these project-aware prompts",
    )

    view.rerender(
      <AgentComposer
        permissionMode="ask_dangerous"
        workspaceAccess="read_write"
        activeRun={null}
        onSendMessage={view.onSendMessage}
        onSteer={view.onSteer}
        onCancel={view.onCancel}
        onPermissionModeChange={view.onPermissionModeChange}
        placement="dock"
        capabilityHint={capabilityHint}
      />,
    )

    expect(screen.queryByTestId("agent-capability-hint")).not.toBeInTheDocument()
  })

  it("offers Auto or multi-environment Manual selection without exposing transport types", async () => {
    stubMatchMedia(false)
    const user = userEvent.setup()
    const onEnvironmentSelectionChange = vi.fn().mockResolvedValue(undefined)
    const targets: AgentEnvironmentTarget[] = [
      { id: "local", label: "Local", kind: "local", status: "online" },
      {
        id: "gpu-01",
        label: "GPU 01",
        description: "bio@gpu-01",
        kind: "ssh",
        status: "online",
      },
    ]
    function EnvironmentComposer() {
      const [selection, setSelection] = useState<AgentEnvironmentSelection>({
        mode: "auto",
      })
      return (
        <AgentComposer
          permissionMode="ask_dangerous"
          workspaceAccess="read_write"
          activeRun={null}
          onSendMessage={vi.fn()}
          onSteer={vi.fn()}
          onCancel={vi.fn()}
          onPermissionModeChange={vi.fn()}
          environmentTargets={targets}
          environmentSelection={selection}
          effectiveEnvironmentSelection={selection}
          onEnvironmentSelectionChange={async (nextSelection) => {
            onEnvironmentSelectionChange(nextSelection)
            setSelection(nextSelection)
          }}
        />
      )
    }
    const view = renderWithProviders(<EnvironmentComposer />)

    await user.click(
      screen.getByRole("button", { name: /Execution environments: Auto/i }),
    )
    await user.click(screen.getByRole("menuitemradio", { name: /Manual/i }))
    expect(onEnvironmentSelectionChange).toHaveBeenCalledWith({
      mode: "manual",
      targetIds: ["local"],
    })

    await user.click(screen.getByRole("menuitemcheckbox", { name: /GPU 01/i }))
    expect(onEnvironmentSelectionChange).toHaveBeenLastCalledWith({
      mode: "manual",
      targetIds: ["local", "gpu-01"],
    })

    view.rerender(
      <AgentComposer
        permissionMode="ask_dangerous"
        workspaceAccess="read_write"
        activeRun={null}
        onSendMessage={vi.fn()}
        onSteer={vi.fn()}
        onCancel={vi.fn()}
        onPermissionModeChange={vi.fn()}
        environmentTargets={targets}
        environmentSelection={{
          mode: "manual",
          targetIds: ["local", "gpu-01"],
        }}
        effectiveEnvironmentSelection={{ mode: "auto" }}
        environmentSelectionPending
        onEnvironmentSelectionChange={onEnvironmentSelectionChange}
      />,
    )
    expect(screen.getByText("Updating environments…")).toBeInTheDocument()
  })

  it("grows the textarea with its content up to the bounded composer height", () => {
    renderComposer({ placement: "draft" })
    const input = screen.getByRole("textbox", { name: "Message the agent" })
    Object.defineProperty(input, "scrollHeight", {
      configurable: true,
      value: 240,
    })

    fireEvent.input(input, { target: { value: "A long\nmultiline\nrequest" } })

    expect(input).toHaveStyle({ height: "160px" })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("sends trimmed text with Enter and keeps Shift+Enter as a newline", async () => {
    const user = userEvent.setup()
    const { onSendMessage } = renderComposer()
    const input = screen.getByRole("textbox", { name: "Message the agent" })

    await user.type(input, "First line{Shift>}{Enter}{/Shift}Second line")
    expect(input).toHaveValue("First line\nSecond line")

    await user.keyboard("{Enter}")

    await waitFor(() => expect(onSendMessage).toHaveBeenCalledTimes(1))
    expect(onSendMessage).toHaveBeenCalledWith([
      { type: "text", text: "First line\nSecond line" },
    ])
    expect(input).toHaveValue("")
  })

  it("submits typed context without translating it into display-only metadata", async () => {
    const user = userEvent.setup()
    const contextInputs: AgentContextInput[] = [
      {
        id: "workflow:workflow-1",
        kind: "workflow",
        label: "RNA-seq",
        input_part: {
          type: "workflow_ref",
          workflow_id: "workflow-1",
          scope: "project",
          project_id: "project-1",
        },
      },
    ]
    const { onSendMessage, onContextSubmitted } = renderComposer({
      contextInputs,
    })

    expect(screen.getByText("RNA-seq")).toBeInTheDocument()
    await user.type(
      screen.getByRole("textbox", { name: "Message the agent" }),
      "Inspect it",
    )
    await user.click(screen.getByRole("button", { name: "Send message" }))

    expect(onSendMessage).toHaveBeenCalledWith([
      contextInputs[0].input_part,
      { type: "text", text: "Inspect it" },
    ])
    expect(onContextSubmitted).toHaveBeenCalledTimes(1)
  })

  it("queues an ordinary message during a run and offers explicit steer and stop actions", async () => {
    const user = userEvent.setup()
    const stopRequest = deferred<void>()
    const onCancel = vi.fn(() => stopRequest.promise)
    const { onSendMessage, onSteer } = renderComposer({
      currentRun: activeRun(),
      onCancel,
    })
    const input = screen.getByRole("textbox", { name: "Message the agent" })

    await user.type(input, "Do this next")
    await user.click(screen.getByRole("button", { name: "Queue message" }))
    expect(onSendMessage).toHaveBeenCalledWith([
      expect.objectContaining({ type: "text", text: "Do this next" }),
    ])
    expect(onSteer).not.toHaveBeenCalled()

    await user.type(input, "Use the smaller sample")
    await user.click(screen.getByRole("button", { name: "Steer active run" }))
    expect(onSteer).toHaveBeenCalledWith([
      expect.objectContaining({ type: "text", text: "Use the smaller sample" }),
    ])

    await user.click(screen.getByRole("button", { name: "Stop run" }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("button", { name: "Stopping…" })).toBeDisabled()

    stopRequest.resolve()
  })

  it("keeps failed submissions editable and succeeds when the user retries", async () => {
    const user = userEvent.setup()
    const onSendMessage = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(undefined)
    renderComposer({ onSendMessage })
    const input = screen.getByRole("textbox", { name: "Message the agent" })

    await user.type(input, "Inspect workflow.nf")
    await user.click(screen.getByRole("button", { name: "Send message" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The message could not be submitted. Try again.",
    )
    expect(input).toHaveValue("Inspect workflow.nf")

    await user.click(screen.getByRole("button", { name: "Send message" }))
    await waitFor(() => expect(onSendMessage).toHaveBeenCalledTimes(2))
    expect(input).toHaveValue("")
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("shows a requested approval mode while waiting for authoritative session state", async () => {
    stubMatchMedia(false)
    const user = userEvent.setup()
    const onPermissionModeChange = vi.fn().mockResolvedValue(undefined)
    const view = renderComposer({ onPermissionModeChange })

    await user.click(
      screen.getByRole("button", {
        name: "Approval mode: Approve safe actions",
      }),
    )
    await user.click(
      screen.getByRole("menuitemradio", { name: /Full access/i }),
    )

    expect(onPermissionModeChange).toHaveBeenCalledWith("full_access")
    expect(
      screen.getByRole("button", {
        name: "Approval mode: Full access",
      }),
    ).toBeDisabled()
    expect(screen.getByText("Updating approval mode…")).toBeInTheDocument()

    view.rerender(
      <AgentComposer
        permissionMode="full_access"
        workspaceAccess="read_write"
        activeRun={null}
        onSendMessage={view.onSendMessage}
        onSteer={view.onSteer}
        onCancel={view.onCancel}
        onPermissionModeChange={onPermissionModeChange}
      />,
    )

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Approval mode: Full access" }),
      ).toBeInTheDocument(),
    )
    expect(
      screen.queryByText("Updating approval mode…"),
    ).not.toBeInTheDocument()
  })

  it("uses an accessible bottom sheet for approval mode on mobile", async () => {
    stubMatchMedia(true)
    const user = userEvent.setup()
    const onPermissionModeChange = vi.fn().mockResolvedValue(undefined)
    renderComposer({ onPermissionModeChange })

    const trigger = screen.getByRole("button", {
      name: "Approval mode: Approve safe actions",
    })
    await user.click(trigger)

    let sheet = await screen.findByRole("dialog")
    expect(sheet).toHaveAccessibleName("How should agent actions be approved?")
    expect(sheet).toHaveAccessibleDescription(
      "Only ask for dangerous or critical actions.",
    )
    expect(screen.queryByRole("menuitemradio")).not.toBeInTheDocument()

    const options = within(sheet).getByRole("group", {
      name: "How should agent actions be approved?",
    })
    expect(options).toHaveClass("overscroll-contain")
    expect(options).toHaveClass("pb-[max(1rem,env(safe-area-inset-bottom))]")
    expect(
      within(options).getByRole("button", { name: /Approve safe actions/i }),
    ).toHaveAttribute("aria-pressed", "true")

    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()

    await user.click(trigger)
    sheet = await screen.findByRole("dialog")
    const nextMode = within(sheet).getByRole("button", {
      name: /Ask before changes/i,
    })
    nextMode.focus()
    await user.keyboard("{Enter}")

    expect(onPermissionModeChange).toHaveBeenCalledWith("ask_changes")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(
      screen.getByRole("button", {
        name: "Approval mode: Ask before changes",
      }),
    ).toBeDisabled()
  })

  it("cannot bypass a read-only workspace but allows changing the next run while one is active", async () => {
    stubMatchMedia(false)
    const user = userEvent.setup()
    const onPermissionModeChange = vi.fn()
    const view = renderComposer({
      permissionMode: "full_access",
      workspaceAccess: "read_only",
      onPermissionModeChange,
    })

    expect(
      screen.getByText(
        "This workspace is read-only. Approval mode cannot grant write access.",
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Approval mode: Full access" }),
    ).toBeDisabled()

    view.rerender(
      <AgentComposer
        permissionMode="ask_dangerous"
        workspaceAccess="read_write"
        activeRun={activeRun()}
        onSendMessage={view.onSendMessage}
        onSteer={view.onSteer}
        onCancel={view.onCancel}
        onPermissionModeChange={onPermissionModeChange}
      />,
    )

    const activeTrigger = screen.getByRole("button", {
      name: "Approval mode: Approve safe actions",
    })
    expect(activeTrigger).toBeEnabled()
    expect(
      screen.getByText("Changes apply to the next run."),
    ).toBeInTheDocument()
    await user.click(activeTrigger)
    await user.click(
      screen.getByRole("menuitemradio", { name: /Full access/i }),
    )
    expect(onPermissionModeChange).toHaveBeenCalledWith("full_access")
  })

  it("disables both message entry and permission changes in a read-only conversation", () => {
    renderComposer({ disabled: true })

    expect(
      screen.getByRole("textbox", { name: "Message the agent" }),
    ).toBeDisabled()
    expect(
      screen.getByRole("button", {
        name: "Approval mode: Approve safe actions",
      }),
    ).toBeDisabled()
  })

  it("offers a retry when an approval mode update fails", async () => {
    const user = userEvent.setup()
    const onPermissionModeChange = vi
      .fn<(mode: AgentPermissionMode) => Promise<void>>()
      .mockRejectedValueOnce(new Error("conflict"))
      .mockResolvedValueOnce(undefined)
    renderComposer({ onPermissionModeChange })

    await user.click(
      screen.getByRole("button", {
        name: "Approval mode: Approve safe actions",
      }),
    )
    await user.click(
      screen.getByRole("menuitemradio", { name: /Ask before changes/i }),
    )

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Approval mode could not be updated.",
    )
    await user.click(
      screen.getByRole("button", { name: "Retry approval update" }),
    )
    expect(onPermissionModeChange).toHaveBeenCalledTimes(2)
    expect(onPermissionModeChange).toHaveBeenLastCalledWith("ask_changes")
  })

  it("changes approval mode in a new-session draft before any Session exists", async () => {
    const user = userEvent.setup()
    const onDraftModeChange = vi.fn()

    function DraftComposer() {
      const [mode, setMode] = useState<AgentPermissionMode>("ask_dangerous")
      return (
        <AgentComposer
          permissionMode={mode}
          workspaceAccess="read_write"
          activeRun={null}
          onSendMessage={vi.fn()}
          onSteer={vi.fn()}
          onCancel={vi.fn()}
          onPermissionModeChange={async (nextMode) => {
            onDraftModeChange(nextMode)
            setMode(nextMode)
          }}
        />
      )
    }

    renderWithProviders(<DraftComposer />)
    await user.click(
      screen.getByRole("button", {
        name: "Approval mode: Approve safe actions",
      }),
    )
    await user.click(
      screen.getByRole("menuitemradio", { name: /Ask before changes/i }),
    )

    expect(onDraftModeChange).toHaveBeenCalledWith("ask_changes")
    expect(
      await screen.findByRole("button", {
        name: "Approval mode: Ask before changes",
      }),
    ).toBeInTheDocument()
  })
})

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((media: string) => ({
      matches,
      media,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  )
}

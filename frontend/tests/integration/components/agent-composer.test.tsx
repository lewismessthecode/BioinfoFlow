import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

import { AgentComposer } from "@/components/bioinfoflow/agent/agent-composer"
import type {
  ActiveRunView,
  AgentPermissionMode,
  AgentWorkspaceAccess,
  InputPart,
} from "@/lib/agent/contracts"
import type { AgentContextInput } from "@/lib/agent/context"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) =>
    (key: string) => {
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
        "agentComposer.submitError": "The message could not be submitted. Try again.",
        "agentComposer.stopError": "The run could not be stopped. Try again.",
        "agentComposer.permission.label": "Approval mode",
        "agentComposer.permission.title": "How should agent actions be approved?",
        "agentComposer.permission.ask_changes.name": "Ask before changes",
        "agentComposer.permission.ask_changes.description": "Ask before files, network, or other side effects change.",
        "agentComposer.permission.ask_dangerous.name": "Approve safe actions",
        "agentComposer.permission.ask_dangerous.description": "Only ask for dangerous or critical actions.",
        "agentComposer.permission.full_access.name": "Full access",
        "agentComposer.permission.full_access.description": "Run automatically inside hard workspace and safety limits.",
        "agentComposer.permission.activeRun": "Approval mode cannot change while a run is active.",
        "agentComposer.permission.readOnlyWorkspace": "This workspace is read-only. Approval mode cannot grant write access.",
        "agentComposer.permission.updating": "Updating approval mode…",
        "agentComposer.permission.updateError": "Approval mode could not be updated.",
        "agentComposer.permission.retry": "Retry approval update",
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

  it("patches approval mode only while idle and waits for authoritative session state", async () => {
    const user = userEvent.setup()
    const onPermissionModeChange = vi.fn().mockResolvedValue(undefined)
    const view = renderComposer({ onPermissionModeChange })

    await user.click(
      screen.getByRole("button", {
        name: "Approval mode: Approve safe actions",
      }),
    )
    await user.click(screen.getByRole("menuitemradio", { name: /Full access/i }))

    expect(onPermissionModeChange).toHaveBeenCalledWith("full_access")
    expect(
      screen.getByRole("button", {
        name: "Approval mode: Approve safe actions",
      }),
    ).toBeInTheDocument()
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
    expect(screen.queryByText("Updating approval mode…")).not.toBeInTheDocument()
  })

  it("cannot use approval mode to bypass a read-only workspace or an active run", async () => {
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
    await user.click(
      screen.getByRole("button", { name: "Approval mode: Full access" }),
    )
    expect(screen.getByRole("menuitemradio", { name: /Full access/i })).toHaveTextContent(
      "hard workspace and safety limits",
    )
    await user.keyboard("{Escape}")

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

    expect(
      screen.getByRole("button", {
        name: "Approval mode: Approve safe actions",
      }),
    ).toBeDisabled()
    expect(
      screen.getByText("Approval mode cannot change while a run is active."),
    ).toBeInTheDocument()
    expect(onPermissionModeChange).not.toHaveBeenCalled()
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

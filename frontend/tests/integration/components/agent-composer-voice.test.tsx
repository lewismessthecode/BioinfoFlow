import { act, fireEvent, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AgentComposer } from "@/components/bioinfoflow/agent/agent-composer"
import type { InputPart } from "@/lib/agent/contracts"
import { getSpeechStatus, transcribeSpeech } from "@/lib/speech"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("@/lib/speech", () => ({
  getSpeechStatus: vi.fn(),
  transcribeSpeech: vi.fn(),
}))

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) =>
    (key: string, values?: Record<string, string | number>) => {
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
        "agentComposer.voice.start": "Start voice dictation",
        "agentComposer.voice.stop": "Stop recording",
        "agentComposer.voice.recording": `Recording ${values?.seconds ?? 0}s`,
        "agentComposer.voice.transcribing": "Transcribing voice…",
        "agentComposer.voice.error": "Voice dictation failed. Try again.",
        "agentComposer.voice.retry": "Retry voice dictation",
        "agentComposer.permission.label": "Approval",
        "agentComposer.permission.title": "Approval policy",
        "agentComposer.permission.ask_changes.name": "Confirm changes",
        "agentComposer.permission.ask_changes.description": "Read-only actions run directly; confirm every workspace change.",
        "agentComposer.permission.ask_dangerous.name": "Confirm risks",
        "agentComposer.permission.ask_dangerous.description": "Routine changes run directly; confirm risky or gated actions.",
        "agentComposer.permission.full_access.name": "No approval",
        "agentComposer.permission.full_access.description": "Allowed actions run directly within workspace and hard safety limits.",
        "agentComposer.permission.activeRun": "Approval mode cannot change while a run is active.",
        "agentComposer.permission.readOnlyWorkspace": "This workspace is read-only.",
        "agentComposer.permission.updating": "Updating approval mode…",
        "agentComposer.permission.updateError": "Approval mode could not be updated.",
        "agentComposer.permission.retry": "Retry approval update",
      }
      return copy[`${namespace}.${key}`] ?? `${namespace}.${key}`
    },
}))

const statusMock = vi.mocked(getSpeechStatus)
const transcribeMock = vi.mocked(transcribeSpeech)

class FakeMediaRecorder {
  static last: FakeMediaRecorder | null = null
  static isTypeSupported() {
    return true
  }

  state: RecordingState = "inactive"
  mimeType: string
  ondataavailable: ((event: BlobEvent) => void) | null = null
  onstop: (() => void) | null = null

  constructor(_stream: MediaStream, options?: MediaRecorderOptions) {
    this.mimeType = options?.mimeType || "audio/webm"
    FakeMediaRecorder.last = this
  }

  start() {
    this.state = "recording"
  }

  stop() {
    this.state = "inactive"
    this.ondataavailable?.({
      data: new Blob(["voice"], { type: this.mimeType }),
    } as BlobEvent)
    this.onstop?.()
  }
}

function renderComposer(
  onSendMessage = vi.fn<(parts: InputPart[]) => Promise<void>>().mockResolvedValue(undefined),
) {
  renderWithProviders(
    <AgentComposer
      permissionMode="ask_dangerous"
      workspaceAccess="read_write"
      activeRun={null}
      onSendMessage={onSendMessage}
      onSteer={vi.fn()}
      onCancel={vi.fn()}
      onPermissionModeChange={vi.fn()}
    />,
  )
  return { onSendMessage }
}

describe("AgentComposer voice dictation", () => {
  const trackStop = vi.fn()

  beforeEach(() => {
    statusMock.mockReset()
    transcribeMock.mockReset()
    trackStop.mockReset()
    FakeMediaRecorder.last = null
    statusMock.mockResolvedValue({
      configured: true,
      available: true,
      provider: "funasr",
      model: "fun-asr-nano",
      language: "en",
      message: null,
    })
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder)
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: trackStop }],
        }),
      },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("appends the transcript as ordinary text and blocks accidental sends while busy", async () => {
    const user = userEvent.setup()
    let resolveTranscript!: (value: { text: string; language: string }) => void
    transcribeMock.mockReturnValue(
      new Promise((resolve) => {
        resolveTranscript = resolve
      }),
    )
    const { onSendMessage } = renderComposer()
    const input = screen.getByRole("textbox", { name: "Message the agent" })
    await user.type(input, "Inspect workflow.")

    const start = await screen.findByRole("button", {
      name: "Start voice dictation",
    })
    expect(start).toHaveTextContent("")
    await user.click(start)

    expect(
      await screen.findByRole("button", { name: "Stop recording" }),
    ).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent("Recording 0s")
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled()
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false })
    expect(onSendMessage).not.toHaveBeenCalled()

    await user.click(screen.getByRole("button", { name: "Stop recording" }))

    expect(
      await screen.findByRole("button", { name: "Transcribing voice…" }),
    ).toBeDisabled()
    expect(screen.getByRole("status")).toHaveTextContent("Transcribing voice…")
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled()
    expect(onSendMessage).not.toHaveBeenCalled()

    await act(async () => {
      resolveTranscript({ text: "Check sample A", language: "en" })
      await Promise.resolve()
    })

    await waitFor(() =>
      expect(input).toHaveValue("Inspect workflow. Check sample A"),
    )
    await user.click(screen.getByRole("button", { name: "Send message" }))

    expect(onSendMessage).toHaveBeenCalledWith([
      { type: "text", text: "Inspect workflow. Check sample A" },
    ])
    expect(transcribeMock).toHaveBeenCalledWith(expect.any(Blob))
    expect(trackStop).toHaveBeenCalled()
  })

  it("surfaces transcription errors and offers an icon-only retry action", async () => {
    const user = userEvent.setup()
    transcribeMock.mockRejectedValueOnce(new Error("speech service unavailable"))
    renderComposer()

    const start = await screen.findByRole("button", {
      name: "Start voice dictation",
    })
    await user.click(start)
    await user.click(screen.getByRole("button", { name: "Stop recording" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Voice dictation failed. Try again.",
    )
    const retry = screen.getByRole("button", { name: "Retry voice dictation" })
    expect(retry).toHaveTextContent("")

    await user.click(retry)

    expect(
      await screen.findByRole("button", { name: "Stop recording" }),
    ).toBeInTheDocument()
  })
})

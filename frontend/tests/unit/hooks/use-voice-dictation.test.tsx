import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useVoiceDictation } from "@/hooks/use-voice-dictation"
import { getSpeechStatus, transcribeSpeech } from "@/lib/speech"

vi.mock("@/lib/speech", () => ({
  getSpeechStatus: vi.fn(),
  transcribeSpeech: vi.fn(),
}))

const statusMock = vi.mocked(getSpeechStatus)
const transcribeMock = vi.mocked(transcribeSpeech)

class FakeMediaRecorder {
  static last: FakeMediaRecorder | null = null
  static isTypeSupported = vi.fn(() => true)
  state = "inactive"
  mimeType: string
  ondataavailable: ((event: { data: Blob }) => void) | null = null
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
    this.ondataavailable?.({ data: new Blob(["voice"], { type: this.mimeType }) })
    this.onstop?.()
  }
}

describe("useVoiceDictation", () => {
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
      language: "zh",
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
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("records, transcribes, and releases the microphone without persisting audio", async () => {
    const onTranscript = vi.fn()
    transcribeMock.mockResolvedValue({ text: "检查这个流程", language: "zh" })
    const { result } = renderHook(() => useVoiceDictation({ onTranscript }))
    await waitFor(() => expect(result.current.available).toBe(true))

    await act(async () => result.current.start())
    expect(result.current.state).toBe("recording")

    act(() => result.current.stop())
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith("检查这个流程"))

    expect(transcribeMock).toHaveBeenCalledWith(expect.any(Blob))
    expect(trackStop).toHaveBeenCalled()
    expect(result.current.state).toBe("idle")
  })

  it("cancels and discards a recording", async () => {
    const onTranscript = vi.fn()
    const { result } = renderHook(() => useVoiceDictation({ onTranscript }))
    await waitFor(() => expect(result.current.available).toBe(true))

    await act(async () => result.current.start())
    act(() => result.current.cancel())

    await waitFor(() => expect(result.current.state).toBe("idle"))
    expect(transcribeMock).not.toHaveBeenCalled()
    expect(onTranscript).not.toHaveBeenCalled()
    expect(trackStop).toHaveBeenCalled()
  })

  it("stops automatically at 120 seconds", async () => {
    vi.useFakeTimers()
    transcribeMock.mockResolvedValue({ text: "完成", language: "zh" })
    const { result } = renderHook(() =>
      useVoiceDictation({ onTranscript: vi.fn(), maxDurationSeconds: 120 }),
    )
    await act(async () => Promise.resolve())
    await act(async () => result.current.start())

    act(() => vi.advanceTimersByTime(120_000))
    await act(async () => Promise.resolve())

    expect(transcribeMock).toHaveBeenCalledTimes(1)
  })

  it("stops and discards an active recorder when the composer unmounts", async () => {
    const { result, unmount } = renderHook(() =>
      useVoiceDictation({ onTranscript: vi.fn() }),
    )
    await waitFor(() => expect(result.current.available).toBe(true))
    await act(async () => result.current.start())

    unmount()

    expect(FakeMediaRecorder.last?.state).toBe("inactive")
    expect(transcribeMock).not.toHaveBeenCalled()
    expect(trackStop).toHaveBeenCalled()
  })

  it("allows only one microphone request while permission is pending", async () => {
    let resolveStream!: (stream: MediaStream) => void
    const getUserMedia = vi.fn().mockReturnValue(
      new Promise<MediaStream>((resolve) => { resolveStream = resolve }),
    )
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    })
    const { result } = renderHook(() => useVoiceDictation({ onTranscript: vi.fn() }))
    await waitFor(() => expect(result.current.available).toBe(true))

    let firstStart!: Promise<void>
    act(() => {
      firstStart = result.current.start()
      void result.current.start()
    })
    expect(getUserMedia).toHaveBeenCalledTimes(1)

    resolveStream({ getTracks: () => [{ stop: trackStop }] } as unknown as MediaStream)
    await act(async () => firstStart)
    await waitFor(() => expect(result.current.state).toBe("recording"))
  })

  it("discards a stream resolved after the composer unmounts", async () => {
    let resolveStream!: (stream: MediaStream) => void
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockReturnValue(
          new Promise<MediaStream>((resolve) => { resolveStream = resolve }),
        ),
      },
    })
    const { result, unmount } = renderHook(() =>
      useVoiceDictation({ onTranscript: vi.fn() }),
    )
    await waitFor(() => expect(result.current.available).toBe(true))
    act(() => { void result.current.start() })
    unmount()

    await act(async () => {
      resolveStream({ getTracks: () => [{ stop: trackStop }] } as unknown as MediaStream)
      await Promise.resolve()
    })

    expect(trackStop).toHaveBeenCalled()
    expect(FakeMediaRecorder.last).toBeNull()
    expect(transcribeMock).not.toHaveBeenCalled()
  })

  it("ignores a transcription that resolves after unmount", async () => {
    let resolveTranscript!: (value: { text: string; language: string }) => void
    transcribeMock.mockReturnValue(
      new Promise((resolve) => { resolveTranscript = resolve }),
    )
    const onTranscript = vi.fn()
    const { result, unmount } = renderHook(() =>
      useVoiceDictation({ onTranscript }),
    )
    await waitFor(() => expect(result.current.available).toBe(true))
    await act(async () => result.current.start())
    act(() => result.current.stop())
    await waitFor(() => expect(transcribeMock).toHaveBeenCalled())

    unmount()
    resolveTranscript({ text: "stale text", language: "zh" })
    await Promise.resolve()

    expect(onTranscript).not.toHaveBeenCalled()
  })
})

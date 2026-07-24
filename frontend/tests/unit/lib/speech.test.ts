import { beforeEach, describe, expect, it, vi } from "vitest"

import { apiRequest } from "@/lib/api"
import { getSpeechStatus, transcribeSpeech } from "@/lib/speech"

vi.mock("@/lib/api", () => ({ apiRequest: vi.fn() }))

const requestMock = vi.mocked(apiRequest)

describe("speech API", () => {
  beforeEach(() => requestMock.mockReset())

  it("loads the provider status through the shared API runtime", async () => {
    requestMock.mockResolvedValueOnce({
      data: {
        configured: true,
        available: true,
        provider: "funasr",
        model: "fun-asr-nano",
        language: "zh",
        message: null,
      },
      meta: undefined,
    })

    await expect(getSpeechStatus()).resolves.toMatchObject({
      configured: true,
      available: true,
      provider: "funasr",
    })
    expect(requestMock).toHaveBeenCalledWith("/speech/status")
  })

  it("uploads an in-memory recording as multipart form data", async () => {
    requestMock.mockResolvedValueOnce({
      data: { text: "检查这个流程", language: "zh" },
      meta: undefined,
    })
    const audio = new Blob(["audio"], { type: "audio/webm" })

    await expect(transcribeSpeech(audio)).resolves.toEqual({
      text: "检查这个流程",
      language: "zh",
    })

    expect(requestMock).toHaveBeenCalledWith(
      "/speech/transcriptions",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    )
    const body = requestMock.mock.calls[0]?.[1]?.body as FormData
    expect(body.get("file")).toBeInstanceOf(File)
  })
})

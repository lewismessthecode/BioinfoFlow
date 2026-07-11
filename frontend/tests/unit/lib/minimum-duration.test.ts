import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { withMinimumDuration } from "@/lib/minimum-duration"

describe("withMinimumDuration", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("waits for the minimum duration when work fulfills immediately", async () => {
    const resultPromise = withMinimumDuration(Promise.resolve("ready"), 100)
    const onFulfilled = vi.fn()
    void resultPromise.then(onFulfilled, () => undefined)

    await vi.advanceTimersByTimeAsync(99)
    expect(onFulfilled).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    await expect(resultPromise).resolves.toBe("ready")
  })

  it("does not add delay when work is slower than the minimum duration", async () => {
    const work = new Promise<string>((resolve) => {
      setTimeout(() => resolve("slow result"), 750)
    })
    const resultPromise = withMinimumDuration(work, 500)
    const onFulfilled = vi.fn()
    void resultPromise.then(onFulfilled, () => undefined)

    await vi.advanceTimersByTimeAsync(500)
    expect(onFulfilled).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(249)
    expect(onFulfilled).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    await expect(resultPromise).resolves.toBe("slow result")
  })

  it("propagates a rejection only after the minimum duration", async () => {
    const error = new Error("request failed")
    const resultPromise = withMinimumDuration(Promise.reject(error), 100)
    const onRejected = vi.fn()
    void resultPromise.then(undefined, onRejected)

    await vi.advanceTimersByTimeAsync(99)
    expect(onRejected).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    await expect(resultPromise).rejects.toBe(error)
  })

  it("uses the existing 500ms minimum by default", async () => {
    const resultPromise = withMinimumDuration(Promise.resolve("ready"))
    const onFulfilled = vi.fn()
    void resultPromise.then(onFulfilled, () => undefined)

    await vi.advanceTimersByTimeAsync(499)
    expect(onFulfilled).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    await expect(resultPromise).resolves.toBe("ready")
  })
})

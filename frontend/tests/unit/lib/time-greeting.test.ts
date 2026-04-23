import { afterEach, describe, expect, it, vi } from "vitest"

import { getTimePeriod } from "@/lib/time-greeting"

describe("getTimePeriod", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it.each([
    [new Date(2026, 3, 23, 5, 0, 0), "morning"],
    [new Date(2026, 3, 23, 12, 0, 0), "afternoon"],
    [new Date(2026, 3, 23, 17, 0, 0), "evening"],
    [new Date(2026, 3, 23, 23, 30, 0), "lateNight"],
  ] satisfies Array<[Date, ReturnType<typeof getTimePeriod>]>)(
    "returns %s -> %s",
    (value, expected) => {
      vi.useFakeTimers()
      vi.setSystemTime(value)

      expect(getTimePeriod()).toBe(expected)
    },
  )
})

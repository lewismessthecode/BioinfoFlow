import { describe, expect, it } from "vitest"

import {
  formatAgentDuration,
  formatAgentEndTime,
} from "@/lib/agent/date-format"

describe("agent date formatting", () => {
  it("formats a completed run using the requested locale", () => {
    const completedAt = "2026-08-15T08:00:02.500Z"
    const expectedTime = new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date(completedAt))

    expect(formatAgentEndTime(completedAt, "en-US")).toBe(expectedTime)
    expect(
      formatAgentDuration(
        "2026-08-15T08:00:00.000Z",
        completedAt,
        "en-US",
      ),
    ).toBe("2.5 s")
  })

  it("rejects missing, invalid, and backwards run timestamps", () => {
    expect(formatAgentEndTime("not-a-date", "en-US")).toBeNull()
    expect(formatAgentDuration(null, "2026-08-15T08:00:00Z", "en-US")).toBeNull()
    expect(
      formatAgentDuration(
        "2026-08-15T08:00:01Z",
        "2026-08-15T08:00:00Z",
        "en-US",
      ),
    ).toBeNull()
  })
})

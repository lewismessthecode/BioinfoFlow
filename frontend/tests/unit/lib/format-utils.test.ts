import { describe, expect, it } from "vitest"

import {
  formatDate,
  formatDateTime,
  formatDuration,
  formatSize,
} from "@/lib/format-utils"

describe("format-utils", () => {
  it("guards invalid or missing date values", () => {
    expect(formatDateTime()).toBe("-")
    expect(formatDateTime("not-a-date")).toBe("-")
    expect(formatDate()).toBe("-")
    expect(formatDate("still-not-a-date")).toBe("-")
  })

  it("formats durations across zero, minute, and hour boundaries", () => {
    expect(formatDuration(0)).toBe("0s")
    expect(formatDuration(-5)).toBe("0s")
    expect(formatDuration(65)).toBe("1m 5s")
    expect(formatDuration(3660)).toBe("1h 1m")
  })

  it("formats byte sizes with the same rounding rules used in the UI", () => {
    expect(formatSize(0)).toBe("0 B")
    expect(formatSize(1536)).toBe("1.5 KB")
    expect(formatSize(10 * 1024)).toBe("10 KB")
    expect(formatSize(1024 * 1024)).toBe("1.0 MB")
    expect(formatSize()).toBe("-")
  })
})

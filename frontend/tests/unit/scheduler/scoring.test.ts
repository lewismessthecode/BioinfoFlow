import { describe, it, expect } from "vitest"
import { computePressure } from "@/app/(app)/scheduler/components/scoring"

describe("computePressure", () => {
  it("returns 0 for an idle system", () => {
    const result = computePressure({
      cpu: 0,
      memUsedGb: 0,
      memTotalGb: 32,
      load: 0,
      cores: 8,
      queue: 0,
    })
    expect(result.score).toBe(0)
    expect(result.status).toBe("healthy")
  })

  it("reports saturated when every signal maxes out", () => {
    const result = computePressure({
      cpu: 100,
      memUsedGb: 32,
      memTotalGb: 32,
      load: 16,
      cores: 8,
      queue: 50,
    })
    expect(result.score).toBe(100)
    expect(result.status).toBe("saturated")
  })

  it("reports moderate around the 60–85 band", () => {
    const result = computePressure({
      cpu: 70,
      memUsedGb: 22,
      memTotalGb: 32,
      load: 5,
      cores: 8,
      queue: 2,
    })
    expect(result.score).toBeGreaterThanOrEqual(60)
    expect(result.score).toBeLessThan(85)
    expect(result.status).toBe("moderate")
  })

  it("does not divide by zero when totals are missing", () => {
    const result = computePressure({
      cpu: 50,
      memUsedGb: 10,
      memTotalGb: 0,
      load: 2,
      cores: 0,
      queue: 0,
    })
    expect(Number.isFinite(result.score)).toBe(true)
  })

  it("queue pressure alone is non-zero but bounded", () => {
    const result = computePressure({
      cpu: 0,
      memUsedGb: 0,
      memTotalGb: 32,
      load: 0,
      cores: 8,
      queue: 10,
    })
    // queue at max contributes 10% weight only → score ≈ 10
    expect(result.score).toBe(10)
    expect(result.status).toBe("healthy")
  })

  it("clamps negative or NaN inputs to zero", () => {
    const result = computePressure({
      cpu: -50,
      memUsedGb: NaN,
      memTotalGb: 32,
      load: -1,
      cores: 8,
      queue: -5,
    })
    expect(result.score).toBe(0)
    expect(result.status).toBe("healthy")
  })

  it("saturates cleanly when values exceed 100%", () => {
    // e.g. load > cores can happen on a thrashing system
    const result = computePressure({
      cpu: 120,
      memUsedGb: 40,
      memTotalGb: 32,
      load: 20,
      cores: 8,
      queue: 100,
    })
    expect(result.score).toBe(100)
    expect(result.status).toBe("saturated")
  })
})

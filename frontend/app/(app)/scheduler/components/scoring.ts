/**
 * Composite "system pressure" score derived from the four admission-gating
 * signals exposed by the scheduler: CPU, memory, load average, and queue
 * depth. Kept as a pure function with no I/O so it can be unit tested in
 * isolation and reused anywhere the UI needs a single severity number.
 *
 * Weights chosen to match the primacy order the scheduler actually uses
 * when deciding whether to admit a new task:
 *   cpu 40% · mem 30% · load 20% · queue 10%
 *
 * Thresholds (60 / 85) match the existing GaugeBar contract in the prior
 * `resource-gauges.tsx` — we don't introduce a new scale.
 */

export type PressureInput = {
  cpu: number // 0..100 — CPU utilisation %
  memUsedGb: number // GB in use
  memTotalGb: number // GB installed (>0)
  load: number // 1-minute load average
  cores: number // logical cores (>0, used to normalise load)
  queue: number // current scheduler queue depth
}

export type PressureStatus = "healthy" | "moderate" | "saturated"

export type PressureResult = {
  score: number // 0..100
  status: PressureStatus
}

const clamp01 = (value: number): number => {
  if (Number.isNaN(value)) return 0
  if (value < 0) return 0
  if (value > 1) return 1
  return value
}

export function computePressure(input: PressureInput): PressureResult {
  const memTotal = input.memTotalGb > 0 ? input.memTotalGb : 1
  const cores = input.cores > 0 ? input.cores : 1

  const cpuP = clamp01(input.cpu / 100)
  const memP = clamp01(input.memUsedGb / memTotal)
  const loadP = clamp01(input.load / cores)
  const queueP = clamp01(input.queue / 10)

  const raw = cpuP * 0.4 + memP * 0.3 + loadP * 0.2 + queueP * 0.1
  const score = Math.round(clamp01(raw) * 100)

  let status: PressureStatus = "healthy"
  if (score >= 85) status = "saturated"
  else if (score >= 60) status = "moderate"

  return { score, status }
}

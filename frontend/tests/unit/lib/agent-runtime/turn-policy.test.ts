import { beforeEach, describe, expect, it } from "vitest"

import {
  AGENT_TURN_POLICY_STORAGE_KEY,
  DEFAULT_AGENT_TURN_POLICY,
  isAgentTurnPolicy,
  readAgentTurnPolicy,
  writeAgentTurnPolicy,
} from "@/lib/agent-runtime/turn-policy"

describe("agent turn policy preference", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it("defaults to steering for continuous active turn handling", () => {
    expect(readAgentTurnPolicy()).toBe(DEFAULT_AGENT_TURN_POLICY)
    expect(DEFAULT_AGENT_TURN_POLICY).toBe("steer")
  })

  it("persists queue and steering policies", () => {
    writeAgentTurnPolicy("queue")

    expect(window.localStorage.getItem(AGENT_TURN_POLICY_STORAGE_KEY)).toBe("queue")
    expect(readAgentTurnPolicy()).toBe("queue")

    writeAgentTurnPolicy("steer")

    expect(readAgentTurnPolicy()).toBe("steer")
  })

  it("migrates the legacy interrupt preference to steer", () => {
    window.localStorage.setItem(AGENT_TURN_POLICY_STORAGE_KEY, "interrupt")

    expect(readAgentTurnPolicy()).toBe("steer")
    expect(window.localStorage.getItem(AGENT_TURN_POLICY_STORAGE_KEY)).toBe("steer")
  })

  it("ignores invalid stored values", () => {
    window.localStorage.setItem(AGENT_TURN_POLICY_STORAGE_KEY, "parallel")

    expect(isAgentTurnPolicy("parallel")).toBe(false)
    expect(readAgentTurnPolicy()).toBe("steer")
  })
})

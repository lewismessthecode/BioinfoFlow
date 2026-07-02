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

  it("defaults to interrupt for Codex-style active turn handling", () => {
    expect(readAgentTurnPolicy()).toBe(DEFAULT_AGENT_TURN_POLICY)
    expect(DEFAULT_AGENT_TURN_POLICY).toBe("interrupt")
  })

  it("persists queue and interrupt policies", () => {
    writeAgentTurnPolicy("queue")

    expect(window.localStorage.getItem(AGENT_TURN_POLICY_STORAGE_KEY)).toBe("queue")
    expect(readAgentTurnPolicy()).toBe("queue")

    writeAgentTurnPolicy("interrupt")

    expect(readAgentTurnPolicy()).toBe("interrupt")
  })

  it("ignores invalid stored values", () => {
    window.localStorage.setItem(AGENT_TURN_POLICY_STORAGE_KEY, "parallel")

    expect(isAgentTurnPolicy("parallel")).toBe(false)
    expect(readAgentTurnPolicy()).toBe("interrupt")
  })
})

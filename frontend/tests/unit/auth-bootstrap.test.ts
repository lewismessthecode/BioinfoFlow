import { describe, expect, it } from "vitest"

import { planBootstrapOwner } from "@/lib/auth-bootstrap"

describe("auth bootstrap recovery", () => {
  it("creates a new owner when the bootstrap email does not exist yet", () => {
    const result = planBootstrapOwner({
      email: "owner@example.com",
      existingUser: null,
    })

    expect(result).toEqual({
      type: "create",
      email: "owner@example.com",
    })
  })

  it("recovers an existing oauth-only user by adding a local credential", () => {
    const result = planBootstrapOwner({
      email: "owner@example.com",
      existingUser: {
        id: "user-1",
        hasCredentialAccount: false,
      },
    })

    expect(result).toEqual({
      type: "recover",
      userId: "user-1",
      hasCredentialAccount: false,
    })
  })

  it("reuses an existing local account and updates its password when needed", () => {
    const result = planBootstrapOwner({
      email: "owner@example.com",
      existingUser: {
        id: "user-2",
        hasCredentialAccount: true,
      },
    })

    expect(result).toEqual({
      type: "recover",
      userId: "user-2",
      hasCredentialAccount: true,
    })
  })
})

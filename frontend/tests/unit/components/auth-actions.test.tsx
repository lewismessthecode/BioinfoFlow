"use client"

import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AuthActions } from "@/components/auth/auth-actions"

const signInSocialMock = vi.fn()

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      continueWithGithub: "Continue with GitHub",
      continueWithGoogle: "Continue with Google",
      redirecting: "Redirecting...",
      errorMessage: "Could not sign in.",
      enableProviders: "Enable more providers.",
      noProviders: "No providers available.",
    }
    return labels[key] ?? key
  },
}))

vi.mock("@/lib/auth-client", () => ({
  authClient: {
    signIn: {
      social: (...args: unknown[]) => signInSocialMock(...args),
    },
  },
}))

describe("AuthActions", () => {
  beforeEach(() => {
    signInSocialMock.mockReset()
  })

  it("renders only enabled providers", () => {
    render(<AuthActions providers={{ github: true, google: false }} />)

    expect(
      screen.getByRole("button", { name: "Continue with GitHub" }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Continue with Google" }),
    ).not.toBeInTheDocument()
  })

  it("shows the empty-state note when no providers are enabled", () => {
    render(<AuthActions providers={{ github: false, google: false }} />)

    expect(screen.getByText("No providers available.")).toBeInTheDocument()
  })

  it("starts the enabled provider sign-in flow", async () => {
    signInSocialMock.mockResolvedValue(undefined)

    render(<AuthActions providers={{ github: true, google: false }} />)

    fireEvent.click(screen.getByRole("button", { name: "Continue with GitHub" }))

    expect(signInSocialMock).toHaveBeenCalledWith({
      provider: "github",
      callbackURL: "/agent",
    })
  })
})

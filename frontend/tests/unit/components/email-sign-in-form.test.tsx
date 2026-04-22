"use client"

import * as React from "react"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { EmailSignInForm } from "@/components/auth/email-sign-in-form"

const replaceMock = vi.fn()
const refreshMock = vi.fn()
const signInEmailMock = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: replaceMock,
    refresh: refreshMock,
  }),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      "local.emailLabel": "Email",
      "local.emailPlaceholder": "name@lab.org",
      "local.passwordLabel": "Password",
      "local.passwordPlaceholder": "Enter your password",
      "local.submit": "Sign in with email",
      "local.submitting": "Signing in...",
      "local.errorMessage": "That email or password didn't work.",
      "local.timeoutMessage": "Request timed out. Try again.",
    }
    return labels[key] ?? key
  },
}))

vi.mock("@/lib/auth-client", () => ({
  authClient: {
    signIn: {
      email: (...args: unknown[]) => signInEmailMock(...args),
    },
  },
}))

describe("EmailSignInForm", () => {
  beforeEach(() => {
    vi.useRealTimers()
    signInEmailMock.mockReset()
    replaceMock.mockReset()
    refreshMock.mockReset()
  })

  it("shows an error and re-enables submit when sign-in returns an error result", async () => {
    signInEmailMock.mockResolvedValue({
      error: {
        message: "Invalid credentials",
      },
    })

    render(<EmailSignInForm />)

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "owner@example.com" },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong-password" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Sign in with email" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That email or password didn't work.",
    )
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Sign in with email" }),
      ).toBeEnabled()
    })
  })

  it("times out stalled requests and restores the form state", async () => {
    vi.useFakeTimers()
    signInEmailMock.mockReturnValue(new Promise(() => {}))

    render(<EmailSignInForm />)

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "owner@example.com" },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "slow-password" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Sign in with email" }))

    await act(async () => {
      vi.advanceTimersByTime(15000)
      await Promise.resolve()
    })

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Request timed out. Try again.",
    )
    expect(
      screen.getByRole("button", { name: "Sign in with email" }),
    ).toBeEnabled()
  })
})

import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import ConnectionsPage from "@/app/(app)/connections/page"
import enMessages from "@/messages/en.json"

function readMessage(namespace: string, key: string, params?: Record<string, string | number>) {
  const path = `${namespace}.${key}`.split(".")
  let value: unknown = enMessages

  for (const part of path) {
    value = typeof value === "object" && value !== null ? (value as Record<string, unknown>)[part] : undefined
  }

  if (typeof value !== "string") {
    return key
  }

  return Object.entries(params ?? {}).reduce(
    (text, [name, replacement]) => text.replaceAll(`{${name}}`, String(replacement)),
    value,
  )
}

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations:
    (namespace: string) =>
    (key: string, params?: Record<string, string | number>) =>
      readMessage(namespace, key, params),
}))

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
  },
}))

describe("ConnectionsPage", () => {
  it("focuses the main flow on SSH config and Agent Skill instructions", () => {
    render(<ConnectionsPage />)

    expect(screen.getByRole("heading", { name: "Connection Center" })).toBeInTheDocument()
    expect(screen.getByText("SSH alias")).toBeInTheDocument()
    expect(screen.getByText("Private key path")).toBeInTheDocument()
    expect(screen.getAllByText("Agent Skill instructions")[0]).toBeInTheDocument()
    expect(
      screen.getByText("Put paths, APIs, environment notes, and startup commands in the skill text."),
    ).toBeInTheDocument()

    expect(screen.queryByText("Tags")).not.toBeInTheDocument()
    expect(screen.queryByText("Accessible paths")).not.toBeInTheDocument()
    expect(screen.queryByText("APIs and ports")).not.toBeInTheDocument()
    expect(screen.queryByText("Environment variables")).not.toBeInTheDocument()
    expect(screen.queryByText("Startup snippet")).not.toBeInTheDocument()
  })
})

import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AgentCustomInstructions } from "@/components/bioinfoflow/settings/agent-custom-instructions"
import { apiRequest } from "@/lib/api"

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
  getApiErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

const labels = {
  label: "Custom instructions",
  description: "Add context the agent should receive when a new session starts.",
  newSessionsOnly: "Changes apply only to new sessions.",
  placeholder: "Add platform conventions, environment details, or other context...",
  save: "Save instructions",
  saving: "Saving...",
  clear: "Clear",
  saved: "Custom instructions saved.",
  saveFailed: "Couldn't save custom instructions.",
  loadFailed: "Couldn't load custom instructions.",
}

describe("AgentCustomInstructions", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  beforeEach(() => {
    apiRequestMock.mockReset()
  })

  it("loads and saves the single custom-instructions textarea", async () => {
    let resolveSave: (() => void) | undefined
    apiRequestMock
      .mockResolvedValueOnce({
        data: { custom_instructions: "Use the validated production reference." },
        meta: undefined,
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSave = () =>
              resolve({
                data: { custom_instructions: "Use the staging reference first." },
                meta: undefined,
              })
          }),
      )

    render(<AgentCustomInstructions labels={labels} />)

    const textarea = await screen.findByRole("textbox", {
      name: "Custom instructions",
    })
    expect(textarea).toHaveValue("Use the validated production reference.")
    expect(screen.getByText("Changes apply only to new sessions.")).toBeInTheDocument()

    fireEvent.change(textarea, {
      target: { value: "Use the staging reference first." },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save instructions" }))

    expect(textarea).toBeDisabled()
    expect(screen.getByRole("button", { name: "Saving..." })).toBeDisabled()
    expect(apiRequestMock).toHaveBeenLastCalledWith("/agent/settings", {
      method: "PUT",
      body: JSON.stringify({
        custom_instructions: "Use the staging reference first.",
      }),
    })

    resolveSave?.()
    await waitFor(() => expect(textarea).not.toBeDisabled())
  })

  it("clears instructions by saving an empty string", async () => {
    apiRequestMock
      .mockResolvedValueOnce({
        data: { custom_instructions: "Temporary context" },
        meta: undefined,
      })
      .mockResolvedValueOnce({
        data: { custom_instructions: "" },
        meta: undefined,
      })

    render(<AgentCustomInstructions labels={labels} />)

    await screen.findByDisplayValue("Temporary context")
    fireEvent.click(screen.getByRole("button", { name: "Clear" }))

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenLastCalledWith("/agent/settings", {
        method: "PUT",
        body: JSON.stringify({ custom_instructions: "" }),
      })
    })
    expect(screen.getByRole("textbox", { name: "Custom instructions" })).toHaveValue("")
  })

  it("shows load and save errors without discarding the draft", async () => {
    apiRequestMock.mockRejectedValueOnce(new Error("offline"))

    const { unmount } = render(<AgentCustomInstructions labels={labels} />)
    expect(await screen.findByText("Couldn't load custom instructions.")).toBeInTheDocument()

    unmount()
    apiRequestMock
      .mockResolvedValueOnce({
        data: { custom_instructions: "Original" },
        meta: undefined,
      })
      .mockRejectedValueOnce(new Error("offline"))

    render(<AgentCustomInstructions labels={labels} />)
    const textarea = await screen.findByDisplayValue("Original")
    fireEvent.change(textarea, { target: { value: "Unsaved draft" } })
    fireEvent.click(screen.getByRole("button", { name: "Save instructions" }))

    expect(await screen.findByText("Couldn't save custom instructions.")).toBeInTheDocument()
    expect(textarea).toHaveValue("Unsaved draft")
  })
})

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
  description: "Add lasting context for new conversations.",
  newSessionsOnly: "New conversations only.",
  placeholder: "Add platform conventions, environment details, or other context...",
  loading: "Loading custom instructions...",
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

  it("renders as a flat settings-row control with compact helper text", async () => {
    apiRequestMock.mockResolvedValueOnce({
      data: { custom_instructions: "" },
      meta: undefined,
    })

    render(<AgentCustomInstructions labels={labels} />)

    const form = screen.getByTestId("agent-custom-instructions")
    expect(form).toHaveAttribute("data-layout", "flat")
    expect(form).not.toHaveClass("rounded-xl", "border", "bg-card")
    const count = await screen.findByText("0 / 20,000")
    expect(count.parentElement).toHaveTextContent(
      "New conversations only.·0 / 20,000",
    )
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
    expect(screen.getByText("New conversations only.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save instructions" })).toBeDisabled()

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
    expect(screen.getByRole("button", { name: "Save instructions" })).toBeDisabled()
  })

  it("announces loading and associates textarea help and character count", async () => {
    let resolveLoad: (() => void) | undefined
    apiRequestMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveLoad = () =>
            resolve({ data: { custom_instructions: "" }, meta: undefined })
        }),
    )

    render(<AgentCustomInstructions labels={labels} />)

    expect(screen.getByRole("status")).toHaveTextContent("Loading custom instructions...")
    const textarea = screen.getByRole("textbox", { name: "Custom instructions" })
    expect(textarea).toBeDisabled()
    expect(textarea).toHaveAttribute(
      "aria-describedby",
      "agent-custom-instructions-help agent-custom-instructions-count",
    )
    expect(screen.getByText("New conversations only.")).toHaveAttribute(
      "id",
      "agent-custom-instructions-help",
    )
    expect(screen.getByText("0 / 20,000")).toHaveAttribute(
      "id",
      "agent-custom-instructions-count",
    )

    resolveLoad?.()
    await waitFor(() => expect(screen.queryByText("Loading custom instructions...")).toBeNull())
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

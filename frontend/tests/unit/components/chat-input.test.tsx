import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      message: "Message",
      attachFiles: "Attach files",
      sendMessage: "Send message",
      stopGenerating: "Stop generating",
      selectProject: "Select a project first",
    }
    return labels[key] ?? key
  },
}))

import { ChatInput } from "@/components/bioinfoflow/chat/chat-input"

describe("ChatInput", () => {
  it("sends on Enter, but not on Shift+Enter or when disabled", async () => {
    const onSend = vi.fn()
    const onStop = vi.fn()
    const onInputChange = vi.fn()
    const user = userEvent.setup()

    const { rerender } = render(
      <ChatInput
        input="  analyze this run  "
        onInputChange={onInputChange}
        onSend={onSend}
        onStop={onStop}
        isStreaming={false}
        disabled={false}
      />,
    )

    const textarea = screen.getByLabelText("Message")
    fireEvent.keyDown(textarea, { key: "Enter" })

    expect(onSend).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true })
    expect(onSend).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole("button", { name: "Send message" }))
    expect(onSend).toHaveBeenCalledTimes(2)

    rerender(
      <ChatInput
        input="still blocked"
        onInputChange={onInputChange}
        onSend={onSend}
        onStop={onStop}
        isStreaming={false}
        disabled
      />,
    )

    fireEvent.keyDown(screen.getByLabelText("Message"), { key: "Enter" })
    expect(onSend).toHaveBeenCalledTimes(2)
    expect(screen.getByPlaceholderText("Select a project first")).toBeDisabled()
  })

  it("shows stop control while streaming", async () => {
    const onSend = vi.fn()
    const onStop = vi.fn()
    const user = userEvent.setup()

    render(
      <ChatInput
        input="analyzing"
        onInputChange={vi.fn()}
        onSend={onSend}
        onStop={onStop}
        isStreaming
        disabled={false}
      />,
    )

    expect(screen.queryByRole("button", { name: "Send message" })).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Stop generating" }))
    expect(onStop).toHaveBeenCalledTimes(1)
    expect(onSend).not.toHaveBeenCalled()
  })

  it("surfaces the file-drop overlay and forwards dropped files", () => {
    const file = new File(["workflow"], "workflow.nf", { type: "text/plain" })
    const onFileDrop = vi.fn()

    const { container } = render(
      <ChatInput
        input=""
        onInputChange={vi.fn()}
        onSend={vi.fn()}
        onStop={vi.fn()}
        onFileDrop={onFileDrop}
        isStreaming={false}
        disabled={false}
      />,
    )

    const dropZone = container.querySelector(".group.relative")
    expect(dropZone).not.toBeNull()

    fireEvent.dragEnter(dropZone!, {
      dataTransfer: {
        files: [file],
        types: ["Files"],
      },
    })

    expect(screen.getByText("Drop files to upload")).toBeInTheDocument()

    fireEvent.drop(dropZone!, {
      dataTransfer: {
        files: [file],
        types: ["Files"],
      },
    })

    expect(onFileDrop).toHaveBeenCalledWith([file])
    expect(screen.queryByText("Drop files to upload")).not.toBeInTheDocument()
  })
})

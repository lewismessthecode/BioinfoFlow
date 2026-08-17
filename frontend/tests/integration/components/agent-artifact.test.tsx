import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AgentArtifactReference } from "@/components/bioinfoflow/agent/agent-artifact"
import type { ArtifactTranscriptBlock } from "@/lib/agent/conversation-model/types"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) =>
    (key: string, values?: Record<string, string | number>) => {
      const copy: Record<string, string> = {
        "agentHistory.artifact.open": `Preview ${values?.name ?? "artifact"}`,
        "agentHistory.artifact.preview": "Preview file",
        "agentHistory.artifact.action": "Preview",
      }
      return copy[`${namespace}.${key}`] ?? `${namespace}.${key}`
    },
}))

const artifactBlock: ArtifactTranscriptBlock = {
  id: "artifact-part-1",
  type: "artifact",
  runId: "run-1",
  createdAt: "2026-08-15T08:00:00Z",
  artifactId: "artifact-1",
  title: "qc-report.html",
  mediaType: "text/html",
}

describe("AgentArtifactReference", () => {
  it("renders the transcript artifact card and delegates preview selection", async () => {
    const onOpen = vi.fn()
    renderWithProviders(
      <AgentArtifactReference artifact={artifactBlock} onOpen={onOpen} />,
    )

    const card = screen.getByRole("article", { name: "qc-report.html" })
    expect(card).toHaveTextContent("Preview file")
    expect(card).toHaveAttribute("data-artifact-id", "artifact-1")

    await userEvent.click(
      screen.getByRole("button", { name: "Preview qc-report.html" }),
    )

    expect(onOpen).toHaveBeenCalledOnce()
    expect(onOpen).toHaveBeenCalledWith("artifact-1")
  })
})

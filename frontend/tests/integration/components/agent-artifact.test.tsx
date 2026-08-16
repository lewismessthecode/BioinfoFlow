import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AgentArtifactReference } from "@/components/bioinfoflow/agent/agent-artifact"
import type { ArtifactRefPart } from "@/lib/agent/contracts"
import { apiRequest, buildApiUrl } from "@/lib/api"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: (namespace: string) =>
    (key: string, values?: Record<string, string | number>) => {
      const copy: Record<string, string> = {
        "agentHistory.reference.artifact": "Artifact",
        "agentHistory.artifact.open": `Open ${values?.name ?? "artifact"}`,
        "agentHistory.artifact.description": "Preview or download this artifact.",
        "agentHistory.artifact.loading": "Loading artifact",
        "agentHistory.artifact.loadFailed": "Could not load this artifact.",
        "agentHistory.artifact.retry": "Retry",
        "agentHistory.artifact.download": "Download",
        "agentHistory.artifact.downloading": "Downloading…",
        "agentHistory.artifact.downloadFailed": "Could not download this artifact.",
        "agentHistory.artifact.previewUnavailable": "Preview is not available for this file type.",
        "agentHistory.artifact.previewTooLarge": "This artifact is too large to preview.",
      }
      return copy[`${namespace}.${key}`] ?? `${namespace}.${key}`
    },
}))

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
  buildApiUrl: vi.fn(),
}))

const part: ArtifactRefPart = {
  id: "artifact-part-1",
  type: "artifact_ref",
  artifact_id: "artifact-1",
  title: "qc-report.html",
  media_type: "text/html",
}

const artifact = {
  id: "artifact-1",
  session_id: "session-1",
  run_id: "run-1",
  type: "report",
  title: "qc-report.html",
  summary: "Quality-control report",
  payload: null,
  resource_ref: {
    kind: "stored_file",
    filename: "qc-report.html",
    mime_type: "text/html",
    size_bytes: 68,
  },
  created_at: "2026-08-15T08:00:00Z",
  updated_at: "2026-08-15T08:00:01Z",
}

describe("AgentArtifactReference", () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset()
    vi.mocked(buildApiUrl).mockReset()
    vi.unstubAllGlobals()
  })

  it("renders a theme-safe artifact card before loading the preview", () => {
    renderWithProviders(<AgentArtifactReference part={part} />)

    const card = screen.getByTestId("agent-artifact-card")
    expect(card).toHaveAttribute("data-artifact-id", "artifact-1")
    expect(card).toHaveClass("dark:bg-transparent")
    expect(card).not.toHaveClass("dark:bg-input/30")
  })

  it("opens an artifact and renders HTML as inert text instead of executing it", async () => {
    const user = userEvent.setup()
    vi.mocked(apiRequest).mockResolvedValueOnce({ data: artifact })
    vi.mocked(buildApiUrl).mockReturnValue("/artifact-download")
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response('<script>window.__unsafe = true</script><h1>QC report</h1>', {
          headers: { "content-type": "text/html" },
        }),
      ),
    )

    renderWithProviders(<AgentArtifactReference part={part} />)
    await user.click(screen.getByRole("button", { name: "Open qc-report.html" }))

    expect(await screen.findByText("Quality-control report")).toBeInTheDocument()
    expect(screen.getByText(/<script>window.__unsafe/)).toBeInTheDocument()
    expect(
      [...document.querySelectorAll("script")].some((script) =>
        script.textContent?.includes("window.__unsafe"),
      ),
    ).toBe(false)
  })

  it("downloads through the authenticated artifact endpoint", async () => {
    const user = userEvent.setup()
    vi.mocked(apiRequest).mockResolvedValueOnce({ data: artifact })
    vi.mocked(buildApiUrl).mockReturnValue("/artifact-download")
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("<h1>QC report</h1>", {
        headers: {
          "content-disposition": 'attachment; filename="qc-report.html"',
          "content-type": "text/html",
        },
      }),
    )
    vi.stubGlobal("fetch", fetchMock)
    const createObjectURL = vi.fn().mockReturnValue("blob:artifact")
    const revokeObjectURL = vi.fn()
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})

    renderWithProviders(<AgentArtifactReference part={part} />)
    await user.click(screen.getByRole("button", { name: "Open qc-report.html" }))
    await screen.findByText(/<h1>QC report/)
    await user.click(screen.getByRole("button", { name: "Download" }))

    await waitFor(() => expect(click).toHaveBeenCalledOnce())
    expect(fetchMock).toHaveBeenCalledWith("/artifact-download", {
      credentials: "include",
      signal: expect.any(AbortSignal),
    })
    expect(createObjectURL).toHaveBeenCalled()
    click.mockRestore()
  })

  it("keeps unsupported artifacts downloadable without attempting to render them", async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    vi.mocked(apiRequest).mockResolvedValueOnce({
      data: {
        ...artifact,
        title: "alignment.bam",
        resource_ref: {
          kind: "stored_file",
          filename: "alignment.bam",
          mime_type: "application/octet-stream",
          size_bytes: 4096,
        },
      },
    })

    renderWithProviders(
      <AgentArtifactReference
        part={{ ...part, title: "alignment.bam", media_type: null }}
      />,
    )
    await user.click(screen.getByRole("button", { name: "Open alignment.bam" }))

    expect(
      await screen.findByText("Preview is not available for this file type."),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Download" })).toBeEnabled()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("offers an inline retry when artifact loading fails", async () => {
    const user = userEvent.setup()
    vi.mocked(apiRequest)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ data: artifact })
    vi.mocked(buildApiUrl).mockReturnValue("/artifact-download")
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("QC report", {
          headers: { "content-type": "text/plain" },
        }),
      ),
    )

    renderWithProviders(<AgentArtifactReference part={part} />)
    await user.click(screen.getByRole("button", { name: "Open qc-report.html" }))

    expect(await screen.findByText("Could not load this artifact.")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Retry" }))
    expect(await screen.findByText("QC report")).toBeInTheDocument()
  })
})

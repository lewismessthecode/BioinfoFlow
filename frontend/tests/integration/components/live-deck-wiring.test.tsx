import * as React from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import type { AgentWorkspaceAdapter } from "@/lib/agent/workspace-adapter"
import type { DagData } from "@/lib/types"

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: (namespace: string) => (key: string) =>
    ({
      "workspace.liveDeck.files": "Files",
      "workspace.liveDeck.pipeline": "Workflow",
      "workspace.liveDeck.artifacts": "Artifacts",
      "workspace.liveDeck.browser": "Browser",
      "workspace.files.label": "Project files",
      "workspace.files.root": "workspace",
      "workspace.files.tree": "File tree",
      "workspace.files.filter": "Filter files",
      "workspace.files.select": "Select a file",
      "workspace.files.download": "Download file",
      "workspace.files.refresh": "Refresh files",
      "workspace.browser.label": "Built-in browser",
      "workspace.browser.title": "Browser",
      "workspace.browser.address": "Browser address",
      "workspace.browser.placeholder": "Enter a URL",
      "workspace.browser.go": "Open address",
      "workspace.browser.empty": "Enter a URL",
      "workspace.artifacts.label": "Agent artifacts",
      "workspace.artifacts.empty": "No artifacts yet",
      "accessibility.hidePanel": "Hide panel",
    })[`${namespace}.${key}`] ?? key,
}))

vi.mock("shiki", () => ({
  codeToHtml: vi.fn(async (content: string) => `<pre><code>${content}</code></pre>`),
}))

vi.mock("@/hooks/use-dag-positions", () => ({
  usePersistedPositions: () => ({
    positions: {},
    savePosition: vi.fn(),
    clearPositions: vi.fn(),
  }),
}))

vi.mock("@/components/bioinfoflow/dag/dag-data-hooks", () => ({
  useDagRuns: () => ({ runs: [], runsLoading: false, runsError: null }),
  useDagWorkflowGroups: () => ({
    workflowGroups: [],
    selectedGroupIndex: null,
    setSelectedGroupIndex: vi.fn(),
    workflowGroupsLoading: false,
    selectedGroup: null,
  }),
  useDagFetch: (
    _runId: string | null | undefined,
    _workflowId: string | null,
    dag: DagData | null | undefined,
    applyDagData: (value: DagData) => void,
  ) => {
    const appliedRef = React.useRef(false)
    React.useEffect(() => {
      if (dag && !appliedRef.current) {
        appliedRef.current = true
        applyDagData(dag)
      }
    }, [applyDagData, dag])
    return { isLoading: false, error: null }
  },
}))

vi.mock("reactflow", async () => {
  const ReactModule = await vi.importActual<typeof React>("react")
  function useNodesState<T>(initial: T[]) {
    const [nodes, setNodes] = ReactModule.useState(initial)
    return [nodes, setNodes, vi.fn()] as const
  }
  function useEdgesState<T>(initial: T[]) {
    const [edges, setEdges] = ReactModule.useState(initial)
    return [edges, setEdges, vi.fn()] as const
  }
  function ReactFlow({ nodes, children }: { nodes: Array<{ data?: { displayLabel?: string; label?: string } }>; children?: React.ReactNode }) {
    return (
      <div data-testid="fixture-dag">
        {nodes.map((node) => node.data?.displayLabel ?? node.data?.label).join(",")}
        {children}
      </div>
    )
  }
  return {
    __esModule: true,
    default: ReactFlow,
    Background: () => null,
    Controls: () => null,
    MiniMap: () => null,
    Handle: () => null,
    Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
    MarkerType: { ArrowClosed: "arrowclosed" },
    useNodesState,
    useEdgesState,
  }
})

import { LiveDeck } from "@/components/bioinfoflow/live-deck"

function fixtureAdapter(): AgentWorkspaceAdapter {
  return {
    listFiles: vi.fn(async () => [
      { name: "pipeline.nf", path: "pipeline.nf", type: "file", sizeBytes: 12, modifiedAt: null },
    ]),
    readFile: vi.fn(async () => ({
      path: "pipeline.nf",
      content: "workflow { FASTQC() }",
      totalLines: 1,
      truncated: false,
    })),
    fileDownloadUrl: vi.fn(() => "/download/pipeline.nf"),
    listArtifacts: vi.fn(async () => [
      {
        id: "session:report-1",
        source: "session",
        title: "qc-report.json",
        summary: "QC report",
        kind: "report",
        mediaType: "application/json",
        sizeBytes: 10,
        createdAt: "2026-09-04T00:00:00Z",
        updatedAt: "2026-09-04T00:00:00Z",
        payload: null,
        resource: { kind: "session", artifactId: "report-1" },
      },
    ]),
    getArtifact: vi.fn(),
    fetchArtifactContent: vi.fn(async () => ({
      blob: new Blob(['{"ok":true}'], { type: "application/json" }),
      filename: "qc-report.json",
      mediaType: "application/json",
    })),
  } as unknown as AgentWorkspaceAdapter
}

const fixtureDag: DagData = {
  nodes: [
    {
      id: "fastqc",
      type: "pipeline",
      position: { x: 0, y: 0 },
      data: { label: "FASTQC", displayLabel: "FASTQC", status: "pending" },
    },
  ],
  edges: [],
}

function FixtureLiveDeck({ adapter }: { adapter: AgentWorkspaceAdapter }) {
  const [activeTab, setActiveTab] = React.useState<"workspace" | "dag" | "artifacts" | "browser">("workspace")
  return (
    <LiveDeck
      activeTab={activeTab}
      onTabChange={setActiveTab}
      projectId="project-1"
      sessionId="session-1"
      runId="run-1"
      dag={fixtureDag}
      adapter={adapter}
    />
  )
}

describe("LiveDeck wiring", () => {
  it("connects real panel implementations to tabs and fixture data", async () => {
    const user = userEvent.setup()
    const adapter = fixtureAdapter()
    render(<FixtureLiveDeck adapter={adapter} />)

    expect(await screen.findByText("pipeline.nf")).toBeInTheDocument()
    await user.click(screen.getByRole("tab", { name: "Browser" }))
    await user.type(screen.getByRole("textbox", { name: "Browser address" }), "example.com:8080")
    await user.click(screen.getByRole("button", { name: "Open address" }))
    expect(screen.getByTitle("Browser")).toHaveAttribute("src", "https://example.com:8080/")

    await user.click(screen.getByRole("tab", { name: "Artifacts" }))
    expect(await screen.findByRole("article", { name: "qc-report.json" })).toBeInTheDocument()
    await user.click(screen.getByRole("tab", { name: "Workflow" }))
    expect(await screen.findByTestId("fixture-dag")).toHaveTextContent("FASTQC")
  })
})

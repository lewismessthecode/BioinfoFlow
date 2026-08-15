import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentContextInputs } from "@/components/bioinfoflow/agent/context-inputs"
import type { AgentContextInput } from "@/lib/agent/context"

vi.mock("next-intl", () => ({
  useTranslations: () =>
    (key: string, values?: Record<string, string>) =>
      key === "remove" ? `Remove ${values?.label}` : key,
}))

const inputs: AgentContextInput[] = [
  {
    id: "attachment:attachment-1",
    kind: "attachment",
    label: "notes.txt",
    input_part: { type: "attachment_ref", attachment_id: "attachment-1" },
  },
  {
    id: "project:project-1:reads.fastq",
    kind: "file",
    label: "reads.fastq",
    input_part: {
      type: "file_ref",
      project_id: "project-1",
      path: "reads.fastq",
    },
  },
  {
    id: "project:project-1:results",
    kind: "directory",
    label: "results",
    input_part: {
      type: "directory_ref",
      project_id: "project-1",
      path: "results",
    },
  },
  {
    id: "workflow:workflow-1",
    kind: "workflow",
    label: "RNA-seq",
    input_part: {
      type: "workflow_ref",
      workflow_id: "workflow-1",
      scope: "global",
    },
  },
  {
    id: "run:run-1",
    kind: "run",
    label: "run-1",
    input_part: { type: "run_ref", run_id: "run-1" },
  },
]

describe("AgentContextInputs", () => {
  it("renders each public context kind as a compact removable chip", () => {
    const onRemove = vi.fn()
    render(<AgentContextInputs inputs={inputs} onRemove={onRemove} />)

    for (const input of inputs) {
      expect(screen.getByText(input.label)).toBeInTheDocument()
    }

    fireEvent.click(screen.getByRole("button", { name: "Remove RNA-seq" }))
    expect(onRemove).toHaveBeenCalledWith("workflow:workflow-1")
  })

  it("hides empty context and disables removal while a command is sending", () => {
    const { rerender } = render(
      <AgentContextInputs inputs={[]} onRemove={vi.fn()} />,
    )
    expect(screen.queryByRole("list")).not.toBeInTheDocument()

    rerender(
      <AgentContextInputs inputs={inputs.slice(0, 1)} onRemove={vi.fn()} disabled />,
    )
    expect(
      screen.getByRole("button", { name: "Remove notes.txt" }),
    ).toBeDisabled()
  })
})

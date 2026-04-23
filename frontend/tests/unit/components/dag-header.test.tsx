import * as React from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import type { ProjectWorkflowGroup, Run } from "@/lib/types"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      "runSelect.ariaLabel": "Run history",
      "runSelect.placeholder": "Pick a run",
      "runSelect.groups.runs": "Runs",
      "runSelect.loading": "Loading runs",
      "runSelect.empty": "No runs yet",
    }
    return labels[key] ?? key
  },
}))

vi.mock("@/components/ui/select", () => {
  const SelectContext = React.createContext<{
    value: string
    onValueChange: (value: string) => void
  } | null>(null)

  return {
    Select: ({
      value,
      onValueChange,
      children,
    }: {
      value: string
      onValueChange: (value: string) => void
      children: React.ReactNode
    }) => (
      <SelectContext.Provider value={{ value, onValueChange }}>
        <div>{children}</div>
      </SelectContext.Provider>
    ),
    SelectTrigger: ({
      children,
      ...props
    }: React.ButtonHTMLAttributes<HTMLButtonElement> & { children: React.ReactNode }) => (
      <button type="button" {...props}>
        {children}
      </button>
    ),
    SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
    SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    SelectGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    SelectLabel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    SelectItem: ({
      value,
      children,
    }: {
      value: string
      children: React.ReactNode
    }) => {
      const context = React.useContext(SelectContext)
      return (
        <button
          type="button"
          aria-label={`select:${value}`}
          onClick={() => context?.onValueChange(value)}
        >
          {children}
        </button>
      )
    },
  }
})

import { DagHeader } from "@/components/bioinfoflow/dag/dag-header"

const workflowGroups: ProjectWorkflowGroup[] = [
  {
    source: "github",
    name: "RNA-seq",
    pinned_workflow: {
      id: "wf-1",
      name: "RNA-seq",
      source: "github",
      engine: "nextflow",
      version: "1.0.0",
    },
    versions: [],
  },
  {
    source: "local",
    name: "QC",
    pinned_workflow: {
      id: "wf-2",
      name: "QC",
      source: "local",
      engine: "nextflow",
      version: "1.1.0",
    },
    versions: [],
  },
]

const runs: Run[] = [
  {
    id: "db-1",
    run_id: "run-1",
    project_id: "project-1",
    status: "running",
    config: {},
    samples_count: 0,
    tasks_total: 4,
    tasks_completed: 2,
  },
  {
    id: "db-2",
    run_id: "run-2",
    project_id: "project-1",
    status: "completed",
    config: {},
    samples_count: 0,
    tasks_total: 4,
    tasks_completed: 4,
  },
]

describe("DagHeader", () => {
  it("lets the user switch workflow groups when multiple versions are available", async () => {
    const user = userEvent.setup()
    const onGroupChange = vi.fn()

    render(
      <DagHeader
        displayName="RNA-seq"
        workflowGroups={workflowGroups}
        selectedGroupIndex={0}
        onGroupChange={onGroupChange}
        workflowGroupsLoading={false}
        isLoading={false}
        showRunSelect={false}
        runId={null}
        runs={[]}
        runsLoading={false}
        runsError={null}
      />,
    )

    await user.click(screen.getByRole("button", { name: "select:1" }))
    expect(onGroupChange).toHaveBeenCalledWith(1)
  })

  it("maps a selected run id back to the full run record", async () => {
    const user = userEvent.setup()
    const onRunSelect = vi.fn()

    render(
      <DagHeader
        displayName="RNA-seq"
        workflowGroups={[workflowGroups[0]]}
        selectedGroupIndex={0}
        onGroupChange={vi.fn()}
        workflowGroupsLoading={false}
        isLoading={false}
        showRunSelect
        runId={null}
        runs={runs}
        runsLoading={false}
        runsError={null}
        onRunSelect={onRunSelect}
      />,
    )

    await user.click(screen.getByRole("button", { name: "select:run-2" }))

    expect(onRunSelect).toHaveBeenCalledWith(runs[1])
  })

  it("surfaces run-loading errors instead of rendering an empty menu silently", () => {
    render(
      <DagHeader
        displayName="RNA-seq"
        workflowGroups={[workflowGroups[0]]}
        selectedGroupIndex={0}
        onGroupChange={vi.fn()}
        workflowGroupsLoading={false}
        isLoading={false}
        showRunSelect
        runId={null}
        runs={[]}
        runsLoading={false}
        runsError="Unable to load runs"
        onRunSelect={vi.fn()}
      />,
    )

    expect(screen.getByText("Unable to load runs")).toBeInTheDocument()
  })
})

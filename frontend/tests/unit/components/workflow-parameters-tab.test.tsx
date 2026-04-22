import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { WorkflowParametersTab } from "@/app/(app)/workflows/[id]/components/workflow-parameters-tab"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const copy: Record<string, string> = {
      "detail.overview.inputs": "Inputs",
      "detail.overview.outputs": "Outputs",
      "detail.parameters.noInfoTitle": "No parameter info",
      "detail.parameters.noInfoDescription": "No details available",
      "detail.parameters.columns.name": "Name",
      "detail.parameters.columns.type": "Type",
      "detail.parameters.columns.required": "Required",
      "detail.parameters.columns.default": "Default",
      "detail.parameters.columns.description": "Description",
      "detail.parameters.columns.optional": "Optional",
      "detail.parameters.optional": "Optional",
      "detail.parameters.required": "Required",
      "detail.parameters.managed": "Platform managed",
      "detail.parameters.artifact": "Artifact",
      "detail.parameters.fileSource.project": "Project data",
      "detail.parameters.fileSource.deliveries": "Deliveries",
      "detail.parameters.fileSource.reference": "Reference library",
      "detail.parameters.noInputs": "No inputs",
      "detail.parameters.noOutputs": "No outputs",
    }
    return copy[key] ?? key
  },
}))

describe("WorkflowParametersTab", () => {
  it("marks internal inputs as platform managed and outputs as artifacts", () => {
    render(
      <WorkflowParametersTab
        schema={{
          workflow_name: "Deaf_20",
          version: "1.0",
          description: null,
          inputs: [
            {
              name: "outdir",
              type: "String",
              optional: false,
              default: null,
              description: null,
              is_internal: true,
              value_kind: "scalar",
            },
            {
              name: "sequence_list",
              type: "File",
              optional: false,
              default: null,
              description: null,
              value_kind: "file",
              source_hint: "deliveries",
              is_internal: false,
            },
          ],
          outputs: [
            {
              name: "zip_result",
              type: "File",
              optional: false,
              default: null,
              description: null,
              value_kind: "file",
            },
          ],
          tasks: [],
          dependencies: [],
        }}
      />,
    )

    expect(screen.getByText("Platform managed")).toBeInTheDocument()
    expect(screen.getByText("Deliveries")).toBeInTheDocument()
    expect(screen.getByText("Artifact")).toBeInTheDocument()
    expect(screen.getByText("zip_result")).toBeInTheDocument()
  })
})

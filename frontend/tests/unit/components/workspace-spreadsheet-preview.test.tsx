import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  loadSpreadsheetWorkbook: vi.fn(),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}))

vi.mock("@/lib/agent/spreadsheet-workbook", () => ({
  loadSpreadsheetWorkbook: mocks.loadSpreadsheetWorkbook,
}))

import { WorkspaceSpreadsheetPreview } from "@/components/bioinfoflow/workspace-spreadsheet-preview"

describe("WorkspaceSpreadsheetPreview", () => {
  beforeEach(() => {
    mocks.loadSpreadsheetWorkbook.mockReset()
    mocks.loadSpreadsheetWorkbook.mockResolvedValue({
      sheets: [
        {
          name: "Samples",
          rows: [
            ["Sample ID", "Reads"],
            ["sample-a", "1200000"],
          ],
        },
        {
          name: "Runs",
          rows: [
            ["Run ID", "Status"],
            ["run-001", "Succeeded"],
          ],
        },
      ],
    })
  })

  it("renders workbook cells and switches worksheets", async () => {
    render(
      <WorkspaceSpreadsheetPreview
        blob={new Blob(["xlsx"])}
        filename="bioinfoflow_demo.xlsx"
      />,
    )

    expect(await screen.findByRole("tab", { name: "Samples" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByText("sample-a")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("tab", { name: "Runs" }))

    expect(screen.getByText("run-001")).toBeInTheDocument()
    expect(screen.queryByText("sample-a")).not.toBeInTheDocument()
  })

  it("shows a compact error state for an invalid workbook", async () => {
    mocks.loadSpreadsheetWorkbook.mockRejectedValueOnce(new Error("invalid xlsx"))

    render(
      <WorkspaceSpreadsheetPreview
        blob={new Blob(["not a workbook"])}
        filename="broken.xlsx"
      />,
    )

    expect(await screen.findByText("spreadsheetFailed")).toBeInTheDocument()
  })
})

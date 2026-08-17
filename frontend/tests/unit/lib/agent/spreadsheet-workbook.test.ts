import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  read: vi.fn(),
  sheetToJson: vi.fn(),
}))

vi.mock("@e965/xlsx", () => ({
  read: mocks.read,
  utils: {
    sheet_to_json: mocks.sheetToJson,
  },
}))

import { loadSpreadsheetWorkbook } from "@/lib/agent/spreadsheet-workbook"

describe("loadSpreadsheetWorkbook", () => {
  beforeEach(() => {
    mocks.read.mockReset()
    mocks.sheetToJson.mockReset()
  })

  it("normalizes library worksheets into a renderer-neutral workbook", async () => {
    const samples = { id: "samples" }
    const runs = { id: "runs" }
    mocks.read.mockReturnValue({
      SheetNames: ["Samples", "Runs"],
      Sheets: { Samples: samples, Runs: runs },
    })
    mocks.sheetToJson
      .mockReturnValueOnce([
        ["Sample ID", "Reads"],
        ["sample-a", 1_200_000],
      ])
      .mockReturnValueOnce([["run-001", true]])

    const workbook = await loadSpreadsheetWorkbook(new Blob(["xlsx bytes"]))

    expect(mocks.read).toHaveBeenCalledWith(expect.any(ArrayBuffer), {
      type: "array",
      cellDates: true,
      dense: true,
    })
    expect(mocks.sheetToJson).toHaveBeenNthCalledWith(1, samples, {
      header: 1,
      raw: false,
      defval: "",
      blankrows: false,
    })
    expect(workbook).toEqual({
      sheets: [
        {
          name: "Samples",
          rows: [
            ["Sample ID", "Reads"],
            ["sample-a", "1200000"],
          ],
        },
        { name: "Runs", rows: [["run-001", "true"]] },
      ],
    })
  })
})

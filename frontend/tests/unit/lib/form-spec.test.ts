import { describe, expect, it } from "vitest"

import {
  countFilledFields,
  validateValues,
  type FormSpec,
} from "@/lib/form-spec"

const TABLE_SPEC: FormSpec = {
  fields: [
    {
      id: "sheet",
      label: "Samplesheet",
      section: "data",
      kind: "table",
      required: true,
      default: null,
      platform_managed: false,
      columns: [
        { name: "sample", required: true, kind: "string" },
        { name: "fastq_1", required: true, kind: "path" },
      ],
    },
  ],
}

describe("form-spec helpers", () => {
  it("treats a required table with zero meaningful rows as missing", () => {
    const result = validateValues(TABLE_SPEC, {
      sheet: { filename: "samplesheet.csv", rows: [] },
    })

    expect(result.ok).toBe(false)
    expect(result.issues).toEqual([
      { fieldId: "sheet", message: "Samplesheet is required" },
    ])
  })

  it("does not count an empty table value as a filled field", () => {
    expect(
      countFilledFields(TABLE_SPEC, {
        sheet: { filename: "samplesheet.csv", rows: [] },
      }),
    ).toBe(0)
  })
})

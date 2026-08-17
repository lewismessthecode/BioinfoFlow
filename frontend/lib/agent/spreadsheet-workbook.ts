export type SpreadsheetSheet = {
  name: string
  rows: string[][]
}

export type SpreadsheetWorkbook = {
  sheets: SpreadsheetSheet[]
}

const MAX_PREVIEW_ROWS = 500
const MAX_PREVIEW_COLUMNS = 80
const MAX_CELL_CHARACTERS = 2_000

export async function loadSpreadsheetWorkbook(
  blob: Blob,
): Promise<SpreadsheetWorkbook> {
  const XLSX = await import("@e965/xlsx")
  const workbook = XLSX.read(await blob.arrayBuffer(), {
    type: "array",
    cellDates: true,
    dense: true,
  })

  return {
    sheets: workbook.SheetNames.map((name) => {
      const worksheet = workbook.Sheets[name]
      const rows = worksheet
        ? XLSX.utils.sheet_to_json<unknown[]>(worksheet, {
            header: 1,
            raw: false,
            defval: "",
            blankrows: false,
          })
        : []

      return {
        name,
        rows: rows.slice(0, MAX_PREVIEW_ROWS).map((row) =>
          row
            .slice(0, MAX_PREVIEW_COLUMNS)
            .map((cell) => formatSpreadsheetCell(cell)),
        ),
      }
    }),
  }
}

function formatSpreadsheetCell(value: unknown) {
  if (value === null || value === undefined) return ""
  const text = value instanceof Date ? value.toISOString() : String(value)
  return text.length > MAX_CELL_CHARACTERS
    ? `${text.slice(0, MAX_CELL_CHARACTERS)}…`
    : text
}

export type UniversalFileKind =
  | "markdown"
  | "html"
  | "pdf"
  | "image"
  | "spreadsheet"
  | "json"
  | "text"
  | "unsupported"

export type UniversalFileLike = {
  path: string
  type?: string | null
  language?: string | null
  mimeType?: string | null
  binary?: boolean | null
}

export type SpreadsheetRows = string[][]

const PREVIEW_ROW_LIMIT = 200
const PREVIEW_COLUMN_LIMIT = 80
export const WORKBOOK_SIZE_LIMIT_BYTES = 10 * 1024 * 1024
export const TEXT_PREVIEW_SIZE_LIMIT_BYTES = 2 * 1024 * 1024

const SPREADSHEET_EXTENSIONS = [
  ".csv",
  ".tsv",
  ".xls",
  ".xlsx",
  ".xlsm",
  ".ods",
]

const IMAGE_EXTENSIONS = [
  ".apng",
  ".avif",
  ".gif",
  ".jpg",
  ".jpeg",
  ".png",
  ".svg",
  ".tif",
  ".tiff",
  ".webp",
]

const TEXT_EXTENSIONS = [
  ".log",
  ".out",
  ".err",
  ".txt",
  ".yaml",
  ".yml",
  ".toml",
  ".ini",
  ".nf",
  ".wdl",
  ".py",
  ".r",
  ".sh",
  ".bash",
  ".zsh",
  ".js",
  ".jsx",
  ".ts",
  ".tsx",
  ".css",
  ".scss",
  ".sql",
]

export function filePreviewKind(file: UniversalFileLike): UniversalFileKind {
  const lowerPath = file.path.toLowerCase()
  const language = file.language?.toLowerCase() ?? ""
  const mimeType = file.mimeType?.toLowerCase() ?? ""
  const type = file.type?.toLowerCase() ?? ""

  if (
    type === "markdown" ||
    language === "markdown" ||
    mimeType.includes("markdown") ||
    lowerPath.endsWith(".md") ||
    lowerPath.endsWith(".markdown")
  ) {
    return "markdown"
  }

  if (
    type === "html" ||
    language === "html" ||
    mimeType.includes("html") ||
    lowerPath.endsWith(".html") ||
    lowerPath.endsWith(".htm")
  ) {
    return "html"
  }

  if (
    type === "pdf" ||
    language === "pdf" ||
    mimeType.includes("pdf") ||
    lowerPath.endsWith(".pdf")
  ) {
    return "pdf"
  }

  if (
    type === "image" ||
    mimeType.startsWith("image/") ||
    IMAGE_EXTENSIONS.some((extension) => lowerPath.endsWith(extension))
  ) {
    return "image"
  }

  if (
    type === "sheet" ||
    type === "spreadsheet" ||
    language === "csv" ||
    language === "tsv" ||
    language === "spreadsheet" ||
    mimeType.includes("csv") ||
    mimeType.includes("spreadsheet") ||
    mimeType.includes("excel") ||
    mimeType.includes("tab-separated") ||
    SPREADSHEET_EXTENSIONS.some((extension) => lowerPath.endsWith(extension))
  ) {
    return "spreadsheet"
  }

  if (
    type === "json" ||
    language === "json" ||
    mimeType.includes("json") ||
    lowerPath.endsWith(".json")
  ) {
    return "json"
  }

  if (!file.binary || TEXT_EXTENSIONS.some((extension) => lowerPath.endsWith(extension))) {
    return "text"
  }

  return "unsupported"
}

export function isWorkbookPath(path: string) {
  const lowerPath = path.toLowerCase()
  return (
    lowerPath.endsWith(".xls") ||
    lowerPath.endsWith(".xlsx") ||
    lowerPath.endsWith(".xlsm") ||
    lowerPath.endsWith(".ods")
  )
}

export function isDelimitedPath(path: string, language?: string | null, mimeType?: string | null) {
  const lowerPath = path.toLowerCase()
  const lowerLanguage = language?.toLowerCase() ?? ""
  const lowerMimeType = mimeType?.toLowerCase() ?? ""
  return (
    lowerLanguage === "csv" ||
    lowerLanguage === "tsv" ||
    lowerMimeType.includes("csv") ||
    lowerMimeType.includes("tab-separated") ||
    lowerPath.endsWith(".csv") ||
    lowerPath.endsWith(".tsv")
  )
}

export function delimiterForPath(path: string, mimeType?: string | null) {
  const lowerPath = path.toLowerCase()
  const lowerMimeType = mimeType?.toLowerCase() ?? ""
  return lowerPath.endsWith(".tsv") || lowerMimeType.includes("tab-separated") ? "\t" : ","
}

export function parseDelimitedRows(
  content: string,
  delimiter: "," | "\t",
  limit = PREVIEW_ROW_LIMIT,
): SpreadsheetRows {
  if (!content.trim()) return []
  const rows: SpreadsheetRows = []
  let row: string[] = []
  let current = ""
  let quoted = false

  for (let index = 0; index < content.length; index += 1) {
    const char = content[index]
    const next = content[index + 1]

    if (char === '"') {
      if (quoted && next === '"') {
        current += '"'
        index += 1
      } else {
        quoted = !quoted
      }
      continue
    }

    if (char === delimiter && !quoted) {
      row.push(current)
      current = ""
      continue
    }

    if ((char === "\n" || char === "\r") && !quoted) {
      row.push(current)
      if (row.some((cell) => cell.trim().length > 0)) rows.push(trimColumns(row))
      row = []
      current = ""
      if (char === "\r" && next === "\n") index += 1
      if (rows.length >= limit) break
      continue
    }

    current += char
  }

  if (rows.length < limit && (current.length > 0 || row.length > 0)) {
    row.push(current)
    if (row.some((cell) => cell.trim().length > 0)) rows.push(trimColumns(row))
  }

  return rows.slice(0, limit)
}

export function normalizeSpreadsheetRows(rows: unknown, limit = PREVIEW_ROW_LIMIT) {
  if (!Array.isArray(rows)) return null
  const normalized = rows
    .filter(Array.isArray)
    .slice(0, limit)
    .map((row) => trimColumns(row.map((cell) => String(cell ?? ""))))
    .filter((row) => row.some((cell) => cell.trim().length > 0))
  return normalized.length ? normalized : null
}

export function columnLabel(index: number) {
  let label = ""
  let value = index + 1
  while (value > 0) {
    const remainder = (value - 1) % 26
    label = String.fromCharCode(65 + remainder) + label
    value = Math.floor((value - remainder) / 26)
  }
  return label
}

export function truncateRowsAndColumns(rows: SpreadsheetRows) {
  return rows
    .slice(0, PREVIEW_ROW_LIMIT)
    .map((row) => row.slice(0, PREVIEW_COLUMN_LIMIT))
}

function trimColumns(row: string[]) {
  return row.slice(0, PREVIEW_COLUMN_LIMIT)
}

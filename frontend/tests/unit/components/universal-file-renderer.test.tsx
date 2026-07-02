import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  columnLabel,
  filePreviewKind,
  parseDelimitedRows,
} from "@/components/bioinfoflow/agent-runtime/file-renderer-utils"
import { UniversalFileRenderer } from "@/components/bioinfoflow/agent-runtime/universal-file-renderer"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, number>) => {
    const labels: Record<string, string> = {
      "renderer.previewUnavailable": "Preview unavailable",
      "renderer.previewUnsupported": "Preview unsupported",
      "renderer.openDefaultDescription": "Open or download the file.",
      "renderer.noRenderableSource": "No renderable source.",
      "renderer.defaultSheetName": "Sheet",
      "renderer.previewLimit": `${values?.rows ?? 0} rows · ${values?.columns ?? 0} columns shown`,
      "renderer.workbookLoading": "Loading workbook",
      "renderer.workbookLoadingDescription": "Preparing workbook preview.",
      "renderer.workbookFetchFailed": "Could not download workbook.",
      "renderer.workbookFailed": "Could not preview workbook.",
      "renderer.workbookEmpty": "Workbook has no visible rows.",
      "renderer.workbookEmptyDescription": "Open in a spreadsheet app.",
      "renderer.workbookTooLarge": "Workbook too large.",
      "renderer.kinds.markdown": "Markdown",
      "renderer.kinds.html": "HTML",
      "renderer.kinds.pdf": "PDF",
      "renderer.kinds.image": "Image",
      "renderer.kinds.spreadsheet": "Spreadsheet",
      "renderer.kinds.json": "JSON",
      "renderer.kinds.text": "Text",
      "renderer.kinds.unsupported": "File",
    }
    return labels[key] ?? key
  },
}))

describe("file renderer helpers", () => {
  it("detects common preview kinds from path, language, and MIME type", () => {
    expect(filePreviewKind({ path: "report.md", language: "markdown" })).toBe("markdown")
    expect(filePreviewKind({ path: "report.html", mimeType: "text/html" })).toBe("html")
    expect(filePreviewKind({ path: "review.pdf", binary: true })).toBe("pdf")
    expect(filePreviewKind({ path: "plot.png", mimeType: "image/png", binary: true })).toBe("image")
    expect(filePreviewKind({ path: "metrics.xlsx", binary: true })).toBe("spreadsheet")
    expect(filePreviewKind({ path: "config.json", mimeType: "application/json" })).toBe("json")
    expect(filePreviewKind({ path: "reads.bam", binary: true })).toBe("unsupported")
  })

  it("parses quoted delimited rows and spreadsheet column labels", () => {
    expect(parseDelimitedRows('sample,notes\nA,"kept, quoted"\nB,"two\nlines"', ",")).toEqual([
      ["sample", "notes"],
      ["A", "kept, quoted"],
      ["B", "two\nlines"],
    ])
    expect(columnLabel(0)).toBe("A")
    expect(columnLabel(25)).toBe("Z")
    expect(columnLabel(26)).toBe("AA")
  })
})

describe("UniversalFileRenderer", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it("renders html in a sandboxed iframe", () => {
    render(
      <UniversalFileRenderer
        file={{ path: "report.html", content: "<h1>Interactive report</h1>" }}
      />,
    )

    const frame = screen.getByTitle("report.html")
    expect(frame).toHaveAttribute("sandbox", "")
    expect(frame).toHaveAttribute("srcdoc", "<h1>Interactive report</h1>")
  })

  it("renders CSV content with spreadsheet row and column headers", () => {
    render(
      <UniversalFileRenderer
        file={{ path: "metrics.csv", content: "sample,reads\nA,42", language: "csv" }}
      />,
    )

    expect(screen.getByRole("table")).toHaveTextContent("sample")
    expect(screen.getByRole("table")).toHaveTextContent("42")
    expect(screen.getByRole("button", { name: "Sheet" })).toHaveAttribute("type", "button")
  })

  it("renders images and pretty-prints JSON", () => {
    const { rerender } = render(
      <UniversalFileRenderer
        file={{
          path: "plot.png",
          title: "UMAP plot",
          mimeType: "image/png",
          binary: true,
          inlineUrl: "/agent/fs/download?plot",
        }}
      />,
    )

    expect(screen.getByRole("img", { name: "UMAP plot" })).toHaveAttribute(
      "src",
      "/agent/fs/download?plot",
    )

    rerender(
      <UniversalFileRenderer
        file={{ path: "summary.json", content: "{\"sample\":\"A\",\"reads\":42}" }}
      />,
    )
    expect(screen.getByText(/"sample": "A"/)).toBeInTheDocument()
    expect(screen.getByText(/"reads": 42/)).toBeInTheDocument()
  })

  it("lazy-loads and renders XLSX workbooks", async () => {
    const XLSX = await import("xlsx")
    const workbook = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(
      workbook,
      XLSX.utils.aoa_to_sheet([
        ["sample", "reads"],
        ["A", 42],
      ]),
      "QC",
    )
    const buffer = XLSX.write(workbook, { bookType: "xlsx", type: "array" }) as ArrayBuffer
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      arrayBuffer: async () => buffer,
    } as Response)

    render(
      <UniversalFileRenderer
        file={{
          path: "metrics.xlsx",
          size: 1024,
          binary: true,
          inlineUrl: "/agent/fs/download?metrics&inline=true",
        }}
      />,
    )

    expect(screen.getByText("Loading workbook")).toBeInTheDocument()
    expect(await screen.findByRole("button", { name: "QC" })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole("table")).toHaveTextContent("sample")
    })
    expect(screen.getByRole("table")).toHaveTextContent("42")
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/agent/fs/download?metrics&inline=true",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })
})

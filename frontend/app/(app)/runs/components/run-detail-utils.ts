import type { RunOutputs } from "@/lib/types"

// ── Types ──────────────────────────────────────────────────────────

export type OutputTreeNode = {
  name: string
  path: string
  uri?: string | null
  type: "file" | "directory"
  size_bytes?: number | null
  children?: OutputTreeNode[]
}

export type PreviewState =
  | { kind: "none" }
  | { kind: "loading"; path: string }
  | { kind: "error"; path: string; message: string }
  | { kind: "binary"; path: string }
  | { kind: "image"; path: string; src: string }
  | { kind: "text"; path: string; content: string }
  | { kind: "json"; path: string; content: string }
  | { kind: "table"; path: string; header: string[]; rows: string[][]; truncated: boolean }

// ── Constants ──────────────────────────────────────────────────────

export const MAX_PREVIEW_LINES = 200
export const MAX_TABLE_ROWS = 50
const MAX_TABLE_COLS = 12

const BINARY_EXTENSIONS = [
  ".bam",
  ".bai",
  ".cram",
  ".crai",
  ".vcf.gz",
  ".bcf",
  ".zip",
  ".tar",
  ".tar.gz",
  ".gz",
  ".bgz",
  ".bz2",
  ".7z",
  ".pdf",
] as const

// ── File type helpers ──────────────────────────────────────────────

export function isBinaryPath(path: string) {
  const lower = path.toLowerCase()
  return BINARY_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

export function isImagePath(path: string) {
  const lower = path.toLowerCase()
  return [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"].some((ext) => lower.endsWith(ext))
}

export function isJsonPath(path: string) {
  return path.toLowerCase().endsWith(".json")
}

export function isTablePath(path: string) {
  const lower = path.toLowerCase()
  return lower.endsWith(".csv") || lower.endsWith(".tsv")
}

// ── Tree builder ───────────────────────────────────────────────────

export function buildOutputTree(files: RunOutputs["files"]): OutputTreeNode[] {
  const index = new Map<string, OutputTreeNode>()
  const top = new Map<string, OutputTreeNode>()

  const getOrCreate = (
    fullPath: string,
    name: string,
    type: "file" | "directory",
    size?: number | null,
    uri?: string | null,
  ) => {
    const existing = index.get(fullPath)
    if (existing) {
      if (type === "file" && uri) existing.uri = uri
      return existing
    }
    const created: OutputTreeNode = {
      name,
      path: fullPath,
      uri,
      type,
      size_bytes: type === "file" ? size ?? null : null,
      children: type === "directory" ? [] : undefined,
    }
    index.set(fullPath, created)
    return created
  }

  for (const item of files) {
    const parts = item.path.split("/").filter(Boolean)
    let parentPath = ""
    for (let i = 0; i < parts.length; i++) {
      const name = parts[i]
      const fullPath = parentPath ? `${parentPath}/${name}` : name
      const isLeaf = i === parts.length - 1
      const type: "file" | "directory" = isLeaf ? item.type : "directory"
      const node = getOrCreate(
        fullPath,
        name,
        type,
        item.size_bytes ?? null,
        isLeaf ? item.uri ?? null : null,
      )
      if (!parentPath) {
        top.set(fullPath, node)
      } else {
        const parent = getOrCreate(parentPath, parentPath.split("/").pop() || parentPath, "directory")
        parent.children = parent.children ?? []
        if (!parent.children.some((c) => c.path === node.path)) parent.children.push(node)
      }
      parentPath = fullPath
    }
  }

  const sortTree = (nodes: OutputTreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === "directory" ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    for (const n of nodes) {
      if (n.children) sortTree(n.children)
    }
  }

  const result = Array.from(top.values())
  sortTree(result)
  return result
}

// ── Table parser ───────────────────────────────────────────────────

export function parseDelimitedTable(content: string, delimiter: "," | "\t") {
  const lines = content.split(/\r?\n/).filter((l) => l.length > 0)
  if (lines.length === 0) return { header: [] as string[], rows: [] as string[][], truncated: false as const }
  const rawRows = lines.map((line) => line.split(delimiter))
  const header = rawRows[0].slice(0, MAX_TABLE_COLS)
  const rows = rawRows.slice(1, 1 + MAX_TABLE_ROWS).map((r) => r.slice(0, MAX_TABLE_COLS))
  const truncated = rawRows.length - 1 > MAX_TABLE_ROWS
  return { header, rows, truncated }
}

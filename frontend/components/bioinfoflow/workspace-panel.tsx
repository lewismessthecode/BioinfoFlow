"use client"

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  ChevronDown,
  ChevronRight,
  Download,
  FileArchive,
  FileCode,
  FileJson,
  FileText,
  Folder,
  FolderOpen,
  Loader2,
  RefreshCw,
  Search,
} from "@/lib/icons"
import {
  bioinfoFlowAgentWorkspaceAdapter,
  type AgentWorkspaceAdapter,
  type WorkspaceFileNode,
  type WorkspaceFilePreview,
} from "@/lib/agent/workspace-adapter"
import { cn } from "@/lib/utils"
import { WorkspaceCodePreview } from "./workspace-code-preview"

const ROOT_PATH = "."

export function WorkspacePanel({
  projectId,
  adapter = bioinfoFlowAgentWorkspaceAdapter,
}: {
  projectId?: string | null
  adapter?: AgentWorkspaceAdapter
}) {
  const t = useTranslations("workspace")
  const [nodes, setNodes] = useState<WorkspaceFileNode[]>([])
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set())
  const [loadingPaths, setLoadingPaths] = useState<Set<string>>(new Set())
  const [selectedFile, setSelectedFile] = useState<WorkspaceFileNode | null>(null)
  const [preview, setPreview] = useState<WorkspaceFilePreview | null>(null)
  const [query, setQuery] = useState("")
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading")
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading" | "ready" | "error">("idle")

  const loadRoot = useCallback(async () => {
    if (!projectId) {
      setNodes([])
      setStatus("ready")
      return
    }
    setStatus("loading")
    try {
      const next = await adapter.listFiles({ projectId, path: ROOT_PATH })
      setNodes(sortNodes(next))
      setStatus("ready")
    } catch {
      setNodes([])
      setStatus("error")
    }
  }, [adapter, projectId])

  useEffect(() => {
    setSelectedFile(null)
    setPreview(null)
    setPreviewStatus("idle")
    setExpandedPaths(new Set())
    void loadRoot()
  }, [loadRoot])

  const loadChildren = useCallback(
    async (node: WorkspaceFileNode) => {
      if (!projectId || node.type !== "directory" || node.children) return
      setLoadingPaths((current) => new Set(current).add(node.path))
      try {
        const children = await adapter.listFiles({ projectId, path: node.path })
        setNodes((current) => replaceChildren(current, node.path, sortNodes(children)))
      } finally {
        setLoadingPaths((current) => {
          const next = new Set(current)
          next.delete(node.path)
          return next
        })
      }
    },
    [adapter, projectId],
  )

  const selectFile = useCallback(
    async (node: WorkspaceFileNode) => {
      if (!projectId || node.type !== "file") return
      setSelectedFile(node)
      setPreview(null)
      setPreviewStatus("loading")
      try {
        const next = await adapter.readFile({ projectId, path: node.path })
        setPreview(next)
        setPreviewStatus("ready")
      } catch {
        setPreviewStatus("error")
      }
    },
    [adapter, projectId],
  )

  const visibleNodes = useMemo(
    () => filterNodes(nodes, query.trim().toLowerCase()),
    [nodes, query],
  )
  const crumbs = selectedFile?.path.split("/").filter(Boolean) ?? []

  return (
    <section className="flex h-full min-h-0 flex-col bg-background" aria-label={t("files.label")}>
      <div className="flex h-11 shrink-0 items-center gap-1 border-b border-border/55 px-2.5">
        <button
          type="button"
          onClick={() => setSelectedFile(null)}
          className="min-w-0 truncate rounded-md px-1.5 py-1 text-xs text-muted-foreground hover:bg-muted/50 hover:text-foreground"
        >
          {t("files.root")}
        </button>
        {crumbs.map((crumb, index) => (
          <span key={`${crumb}-${index}`} className="flex min-w-0 items-center">
            <ChevronRight aria-hidden="true" className="h-3 w-3 shrink-0 text-muted-foreground/55" />
            <span
              className={cn(
                "max-w-36 truncate px-1.5 py-1 text-xs",
                index === crumbs.length - 1 ? "font-medium text-foreground" : "text-muted-foreground",
              )}
              title={crumb}
            >
              {crumb}
            </span>
          </span>
        ))}
        <div className="ml-auto flex shrink-0 items-center gap-0.5">
          {selectedFile && projectId ? (
            <Button variant="ghost" size="icon" className="size-8 rounded-md" asChild>
              <a
                href={adapter.fileDownloadUrl({ projectId, path: selectedFile.path })}
                download
                aria-label={t("files.download")}
              >
                <Download aria-hidden="true" className="h-3.5 w-3.5" />
              </a>
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-8 rounded-md"
            onClick={() => void loadRoot()}
            aria-label={t("files.refresh")}
          >
            <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(10.5rem,38%)]">
        <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">
          {!selectedFile ? (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
              {t("files.select")}
            </div>
          ) : previewStatus === "loading" ? (
            <div className="flex h-full items-center justify-center" role="status" aria-label={t("preview.loading")}>
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground motion-reduce:animate-none" />
            </div>
          ) : previewStatus === "error" ? (
            <div className="flex h-full items-center justify-center px-6 text-center text-xs text-muted-foreground">
              {t("preview.unable")}
            </div>
          ) : preview ? (
            <>
              <WorkspaceCodePreview content={preview.content} path={preview.path} />
              {preview.truncated ? (
                <div className="shrink-0 border-t border-border/45 px-3 py-1.5 text-[11px] text-muted-foreground">
                  {t("files.truncated", { count: preview.totalLines })}
                </div>
              ) : null}
            </>
          ) : null}
        </div>

        <aside className="flex min-h-0 min-w-0 flex-col border-l border-border/55 bg-muted/[0.08]" aria-label={t("files.tree")}>
          <label className="relative mx-2.5 my-2 block">
            <Search aria-hidden="true" className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/70" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("files.filter")}
              aria-label={t("files.filter")}
              className="h-8 w-full rounded-md border border-border/60 bg-background pl-7 pr-2 text-xs outline-none placeholder:text-muted-foreground/65 focus-visible:border-foreground/25 focus-visible:ring-2 focus-visible:ring-ring/20"
            />
          </label>
          <div className="min-h-0 flex-1 overflow-auto px-1.5 pb-2">
            {!projectId ? (
              <TreeState>{t("files.noProject")}</TreeState>
            ) : status === "loading" ? (
              <TreeState>{t("loading")}</TreeState>
            ) : status === "error" ? (
              <TreeState>{t("errors.loadFilesFailed")}</TreeState>
            ) : visibleNodes.length === 0 ? (
              <TreeState>{query ? t("files.noMatches") : t("noFiles")}</TreeState>
            ) : (
              visibleNodes.map((node) => (
                <FileTreeRow
                  key={node.path}
                  node={node}
                  depth={0}
                  selectedPath={selectedFile?.path ?? null}
                  expandedPaths={expandedPaths}
                  loadingPaths={loadingPaths}
                  queryActive={Boolean(query)}
                  onToggle={(directory) => {
                    const expanded = expandedPaths.has(directory.path)
                    setExpandedPaths((current) => {
                      const next = new Set(current)
                      if (expanded) next.delete(directory.path)
                      else next.add(directory.path)
                      return next
                    })
                    if (!expanded) void loadChildren(directory)
                  }}
                  onSelect={(file) => void selectFile(file)}
                />
              ))
            )}
          </div>
        </aside>
      </div>
    </section>
  )
}

function FileTreeRow({
  node,
  depth,
  selectedPath,
  expandedPaths,
  loadingPaths,
  queryActive,
  onToggle,
  onSelect,
}: {
  node: WorkspaceFileNode
  depth: number
  selectedPath: string | null
  expandedPaths: Set<string>
  loadingPaths: Set<string>
  queryActive: boolean
  onToggle: (node: WorkspaceFileNode) => void
  onSelect: (node: WorkspaceFileNode) => void
}) {
  const directory = node.type === "directory"
  const expanded = queryActive || expandedPaths.has(node.path)
  const loading = loadingPaths.has(node.path)

  return (
    <div>
      <button
        type="button"
        onClick={() => (directory ? onToggle(node) : onSelect(node))}
        className={cn(
          "flex h-7 w-full min-w-0 items-center gap-1 rounded-md pr-1.5 text-left text-xs transition-colors hover:bg-muted/55",
          selectedPath === node.path && "bg-muted/70 text-foreground",
        )}
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
        aria-expanded={directory ? expanded : undefined}
        title={node.path}
      >
        {directory ? (
          loading ? (
            <Loader2 className="h-3 w-3 shrink-0 animate-spin text-muted-foreground motion-reduce:animate-none" />
          ) : expanded ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
          )
        ) : (
          <span className="w-3 shrink-0" />
        )}
        {directory ? (
          expanded ? (
            <FolderOpen className="h-3.5 w-3.5 shrink-0 text-sky-600/80 dark:text-sky-400/75" />
          ) : (
            <Folder className="h-3.5 w-3.5 shrink-0 text-sky-600/80 dark:text-sky-400/75" />
          )
        ) : (
          <FileGlyph name={node.name} />
        )}
        <span className="min-w-0 flex-1 truncate">{node.name}</span>
      </button>
      {directory && expanded
        ? node.children?.map((child) => (
            <FileTreeRow
              key={child.path}
              node={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              expandedPaths={expandedPaths}
              loadingPaths={loadingPaths}
              queryActive={queryActive}
              onToggle={onToggle}
              onSelect={onSelect}
            />
          ))
        : null}
    </div>
  )
}

function TreeState({ children }: { children: ReactNode }) {
  return <div className="px-2 py-3 text-xs text-muted-foreground">{children}</div>
}

function replaceChildren(
  nodes: WorkspaceFileNode[],
  path: string,
  children: WorkspaceFileNode[],
): WorkspaceFileNode[] {
  return nodes.map((node) =>
    node.path === path
      ? { ...node, children }
      : node.children
        ? { ...node, children: replaceChildren(node.children, path, children) }
        : node,
  )
}

function sortNodes(nodes: WorkspaceFileNode[]) {
  return [...nodes].sort((left, right) => {
    if (left.type !== right.type) return left.type === "directory" ? -1 : 1
    return left.name.localeCompare(right.name, undefined, { sensitivity: "base" })
  })
}

function filterNodes(nodes: WorkspaceFileNode[], query: string): WorkspaceFileNode[] {
  if (!query) return nodes
  return nodes.flatMap((node) => {
    const children = node.children ? filterNodes(node.children, query) : []
    if (node.name.toLowerCase().includes(query) || children.length > 0) {
      return [{ ...node, children }]
    }
    return []
  })
}

function FileGlyph({ name }: { name: string }) {
  const extension = name.split(".").pop()?.toLowerCase()
  const className = "h-3.5 w-3.5 shrink-0 text-muted-foreground"
  if (["json", "jsonl", "yaml", "yml", "toml"].includes(extension ?? "")) {
    return <FileJson className={className} />
  }
  if (["zip", "tar", "gz", "bz2", "xz"].includes(extension ?? "")) {
    return <FileArchive className={className} />
  }
  if (["js", "jsx", "ts", "tsx", "py", "r", "go", "rs", "java", "c", "cpp", "nf", "wdl", "sh"].includes(extension ?? "")) {
    return <FileCode className={className} />
  }
  return <FileText className={className} />
}

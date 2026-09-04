"use client"

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  ChevronDown,
  ChevronRight,
  Check,
  Copy,
  Download,
  ExternalLink,
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
export type WorkspaceFileSelection = Pick<WorkspaceFileNode, "name" | "path">

export function WorkspacePanel({
  projectId,
  adapter = bioinfoFlowAgentWorkspaceAdapter,
  selectedFilePath,
  onSelectedFileChange,
}: {
  projectId?: string | null
  adapter?: AgentWorkspaceAdapter
  selectedFilePath?: string | null
  onSelectedFileChange?: (file: WorkspaceFileSelection | null) => void
}) {
  const t = useTranslations("workspace")
  const tCommon = useTranslations("common")
  const [nodes, setNodes] = useState<WorkspaceFileNode[]>([])
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set())
  const [loadingPaths, setLoadingPaths] = useState<Set<string>>(new Set())
  const [childErrors, setChildErrors] = useState<Set<string>>(new Set())
  const [selectedFile, setSelectedFile] = useState<WorkspaceFileNode | null>(null)
  const [preview, setPreview] = useState<WorkspaceFilePreview | null>(null)
  const [copied, setCopied] = useState(false)
  const [clipboardAvailable, setClipboardAvailable] = useState(false)
  const [query, setQuery] = useState("")
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading")
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading" | "ready" | "error">("idle")
  const requestGenerationRef = useRef(0)
  const rootControllerRef = useRef<AbortController | null>(null)
  const previewControllerRef = useRef<AbortController | null>(null)
  const childControllersRef = useRef(new Map<string, AbortController>())

  useEffect(() => {
    setClipboardAvailable(Boolean(navigator.clipboard?.writeText))
  }, [])

  const loadRoot = useCallback(async () => {
    rootControllerRef.current?.abort()
    const controller = new AbortController()
    rootControllerRef.current = controller
    const generation = requestGenerationRef.current
    if (!projectId) {
      setNodes([])
      setStatus("ready")
      return
    }
    setStatus("loading")
    try {
      const next = await adapter.listFiles({
        projectId,
        path: ROOT_PATH,
        signal: controller.signal,
      })
      if (controller.signal.aborted || generation !== requestGenerationRef.current) return
      setNodes(sortNodes(next))
      setStatus("ready")
    } catch {
      if (controller.signal.aborted || generation !== requestGenerationRef.current) return
      setNodes([])
      setStatus("error")
    } finally {
      if (rootControllerRef.current === controller) rootControllerRef.current = null
    }
  }, [adapter, projectId])

  useEffect(() => {
    setSelectedFile(null)
    setPreview(null)
    setPreviewStatus("idle")
    setExpandedPaths(new Set())
    setChildErrors(new Set())
    void loadRoot()
    const childControllers = childControllersRef.current
    return () => {
      requestGenerationRef.current += 1
      rootControllerRef.current?.abort()
      previewControllerRef.current?.abort()
      childControllers.forEach((controller) => controller.abort())
      childControllers.clear()
      setLoadingPaths(new Set())
    }
  }, [loadRoot])

  useEffect(() => {
    if (selectedFilePath !== null || !selectedFile) return
    setSelectedFile(null)
    setPreview(null)
    setCopied(false)
    setPreviewStatus("idle")
  }, [selectedFile, selectedFilePath])

  const loadChildren = useCallback(
    async (node: WorkspaceFileNode) => {
      if (!projectId || node.type !== "directory" || node.children) return
      childControllersRef.current.get(node.path)?.abort()
      const controller = new AbortController()
      childControllersRef.current.set(node.path, controller)
      const generation = requestGenerationRef.current
      setLoadingPaths((current) => new Set(current).add(node.path))
      try {
        const children = await adapter.listFiles({
          projectId,
          path: node.path,
          signal: controller.signal,
        })
        if (controller.signal.aborted || generation !== requestGenerationRef.current) return
        setChildErrors((current) => {
          const next = new Set(current)
          next.delete(node.path)
          return next
        })
        setNodes((current) => replaceChildren(current, node.path, sortNodes(children)))
      } catch (error) {
        if (!controller.signal.aborted && generation === requestGenerationRef.current) {
          setChildErrors((current) => new Set(current).add(node.path))
          throw error
        }
      } finally {
        if (
          childControllersRef.current.get(node.path) === controller &&
          generation === requestGenerationRef.current
        ) {
          childControllersRef.current.delete(node.path)
          setLoadingPaths((current) => {
            const next = new Set(current)
            next.delete(node.path)
            return next
          })
        }
      }
    },
    [adapter, projectId],
  )

  const selectFile = useCallback(
    async (node: WorkspaceFileNode) => {
      if (!projectId || node.type !== "file") return
      previewControllerRef.current?.abort()
      const controller = new AbortController()
      previewControllerRef.current = controller
      const generation = requestGenerationRef.current
      setSelectedFile(node)
      onSelectedFileChange?.({ name: node.name, path: node.path })
      setPreview(null)
      setCopied(false)
      setPreviewStatus("loading")
      try {
        const next = await adapter.readFile({
          projectId,
          path: node.path,
          signal: controller.signal,
        })
        if (controller.signal.aborted || generation !== requestGenerationRef.current) return
        setPreview(next)
        setPreviewStatus("ready")
      } catch {
        if (controller.signal.aborted || generation !== requestGenerationRef.current) return
        setPreviewStatus("error")
      } finally {
        if (previewControllerRef.current === controller) {
          previewControllerRef.current = null
        }
      }
    },
    [adapter, onSelectedFileChange, projectId],
  )

  const visibleNodes = useMemo(
    () => filterNodes(nodes, query.trim().toLowerCase()),
    [nodes, query],
  )
  const crumbs = selectedFile?.path.split("/").filter(Boolean).slice(0, -1) ?? []
  const selectedFileUrl = useMemo(
    () => {
      if (!selectedFile || !projectId) return null
      return safeFileUrl(adapter.fileDownloadUrl({ projectId, path: selectedFile.path }))
    },
    [adapter, projectId, selectedFile],
  )
  const closeSelectedFile = useCallback(() => {
    setSelectedFile(null)
    onSelectedFileChange?.(null)
    setPreview(null)
    setCopied(false)
    setPreviewStatus("idle")
  }, [onSelectedFileChange])
  const copyPreview = useCallback(async () => {
    if (!preview || !clipboardAvailable || !navigator.clipboard?.writeText) return
    try {
      await navigator.clipboard.writeText(preview.content)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }, [clipboardAvailable, preview])

  return (
    <section className="flex h-full min-h-0 flex-col bg-background" aria-label={t("files.label")}>
      <div
        className="flex h-10 shrink-0 items-center gap-1 border-b border-border/70 bg-muted/[0.08] px-2.5"
        data-testid="workspace-panel-header"
      >
        <button
          type="button"
          onClick={closeSelectedFile}
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
        <div className="ml-auto flex shrink-0 items-center gap-0.5" data-testid="workspace-file-actions">
          {selectedFileUrl ? (
            <Button variant="ghost" size="icon" className="size-8 rounded-md" asChild>
              <a
                href={selectedFileUrl}
                download
                aria-label={t("files.download")}
              >
                <Download aria-hidden="true" className="h-3.5 w-3.5" />
              </a>
            </Button>
          ) : null}
          {selectedFile ? (
            selectedFileUrl ? (
              <Button variant="ghost" size="icon" className="size-8 rounded-md" asChild>
                <a
                  href={selectedFileUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={t("browser.openExternal")}
                >
                  <ExternalLink aria-hidden="true" className="size-3.5" />
                </a>
              </Button>
            ) : (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8 rounded-md"
                disabled
                aria-label={t("browser.openExternal")}
              >
                <ExternalLink aria-hidden="true" className="size-3.5" />
              </Button>
            )
          ) : null}
          {selectedFile ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-8 rounded-md"
              onClick={() => void copyPreview()}
              disabled={!preview || previewStatus !== "ready" || !clipboardAvailable}
              aria-label={copied ? tCommon("copiedToClipboard") : tCommon("copy")}
            >
              {copied ? <Check aria-hidden="true" className="size-3.5" /> : <Copy aria-hidden="true" className="size-3.5" />}
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

      <div
        className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(8rem,32%)]"
        data-layout="editor-dominant"
        data-testid="workspace-split-view"
      >
        <div
          className="flex min-h-0 min-w-0 flex-col overflow-hidden bg-background"
          data-testid="workspace-editor-pane"
        >
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

        <aside
          className="flex min-h-0 min-w-0 flex-col border-l border-border/75 bg-muted/[0.12] shadow-[-1px_0_0_hsl(var(--border)/0.18)]"
          aria-label={t("files.tree")}
          data-testid="workspace-file-tree"
        >
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
                  childErrors={childErrors}
                  childErrorLabel={t("errors.loadFilesFailed")}
                  retryLabel={t("files.refresh")}
                  queryActive={Boolean(query)}
                  onToggle={(directory) => {
                    const expanded = expandedPaths.has(directory.path)
                    setExpandedPaths((current) => {
                      const next = new Set(current)
                      if (expanded) next.delete(directory.path)
                      else next.add(directory.path)
                      return next
                    })
                    if (!expanded) {
                      void loadChildren(directory).catch(() => undefined)
                    }
                  }}
                  onRetry={(directory) => void loadChildren(directory).catch(() => undefined)}
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
  childErrors,
  childErrorLabel,
  retryLabel,
  queryActive,
  onToggle,
  onRetry,
  onSelect,
}: {
  node: WorkspaceFileNode
  depth: number
  selectedPath: string | null
  expandedPaths: Set<string>
  loadingPaths: Set<string>
  childErrors: Set<string>
  childErrorLabel: string
  retryLabel: string
  queryActive: boolean
  onToggle: (node: WorkspaceFileNode) => void
  onRetry: (node: WorkspaceFileNode) => void
  onSelect: (node: WorkspaceFileNode) => void
}) {
  const directory = node.type === "directory"
  const expanded = queryActive || expandedPaths.has(node.path)
  const loading = loadingPaths.has(node.path)

  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={() => (directory ? onToggle(node) : onSelect(node))}
        className={cn(
          "flex h-7 w-full min-w-0 items-center gap-1 rounded-[5px] border border-transparent pr-1.5 text-left text-xs text-foreground/80 transition-colors hover:bg-muted/60 hover:text-foreground",
          selectedPath === node.path &&
            "border-border/45 bg-accent/75 text-accent-foreground shadow-sm",
        )}
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
        aria-expanded={directory ? expanded : undefined}
        aria-current={selectedPath === node.path ? "true" : undefined}
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
            <FolderOpen
              data-file-accent="folder"
              className="h-3.5 w-3.5 shrink-0 text-sky-600 dark:text-sky-400"
            />
          ) : (
            <Folder
              data-file-accent="folder"
              className="h-3.5 w-3.5 shrink-0 text-sky-600 dark:text-sky-400"
            />
          )
        ) : (
          <FileGlyph name={node.name} />
        )}
        <span className="min-w-0 flex-1 truncate">{node.name}</span>
      </button>
      {childErrors.has(node.path) ? (
        <span className="ml-7 inline-flex items-center gap-1 text-[10px] text-destructive">
          <span role="status">{childErrorLabel}</span>
          <button
            type="button"
            className="underline underline-offset-2"
            aria-label={retryLabel}
            onClick={() => onRetry(node)}
          >
            {retryLabel}
          </button>
        </span>
      ) : null}
      {directory && expanded
        ? node.children?.map((child) => (
            <FileTreeRow
              key={child.path}
              node={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              expandedPaths={expandedPaths}
              loadingPaths={loadingPaths}
              childErrors={childErrors}
              childErrorLabel={childErrorLabel}
              retryLabel={retryLabel}
              queryActive={queryActive}
              onToggle={onToggle}
              onRetry={onRetry}
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

function safeFileUrl(value: string) {
  if (value.startsWith("/") && !value.startsWith("//")) return value
  try {
    const url = new URL(value)
    return url.protocol === "http:" || url.protocol === "https:" ? value : null
  } catch {
    return null
  }
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
  const baseClassName = "h-3.5 w-3.5 shrink-0"
  if (["json", "jsonl", "yaml", "yml", "toml"].includes(extension ?? "")) {
    return (
      <FileJson
        data-file-accent="data"
        className={cn(baseClassName, "text-amber-500 dark:text-amber-400")}
      />
    )
  }
  if (["zip", "tar", "gz", "bz2", "xz"].includes(extension ?? "")) {
    return (
      <FileArchive
        data-file-accent="archive"
        className={cn(baseClassName, "text-violet-500 dark:text-violet-400")}
      />
    )
  }
  if (["js", "jsx", "ts", "tsx", "py", "r", "go", "rs", "java", "c", "cpp", "nf", "wdl", "sh"].includes(extension ?? "")) {
    return (
      <FileCode
        data-file-accent="code"
        className={cn(baseClassName, "text-sky-500 dark:text-sky-400")}
      />
    )
  }
  if (["md", "mdx", "txt", "log"].includes(extension ?? "")) {
    return (
      <FileText
        data-file-accent="text"
        className={cn(baseClassName, "text-blue-500 dark:text-blue-400")}
      />
    )
  }
  return (
    <FileText
      data-file-accent="file"
      className={cn(baseClassName, "text-muted-foreground")}
    />
  )
}

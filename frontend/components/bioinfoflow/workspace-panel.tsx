"use client"

import { useCallback, useEffect, useState } from "react"
import { ChevronRight, ChevronDown, Folder, FileText, RefreshCw, Download, Trash2, Eye, Loader2 } from "lucide-react"
import { useTranslations } from "next-intl"
import { cn } from "@/lib/utils"
import { formatSize } from "@/lib/format-utils"
import { Button } from "@/components/ui/button"
import { apiRequest, getApiErrorMessage, buildApiUrl } from "@/lib/api"
import { openInNewTab } from "@/lib/window-utils"
import { toast } from "sonner"
import { useProjectContext } from "@/components/bioinfoflow/project-context"

interface FileNode {
  name: string
  type: "file" | "directory"
  size_bytes?: number | null
  children?: FileNode[]
  path?: string
}

interface FileTreeItemProps {
  node: FileNode
  depth: number
  selectedFile: string | null
  onSelect: (node: FileNode) => void
  onToggle: (node: FileNode) => void
  loadingPaths: Set<string>
}

function FileTreeItem({ node, depth, selectedFile, onSelect, onToggle, loadingPaths }: FileTreeItemProps) {
  const tWorkspace = useTranslations("workspace")
  const [expanded, setExpanded] = useState(false)
  const isFolder = node.type === "directory"
  const isSelected = selectedFile === node.path
  const nodePath = node.path ?? node.name
  const isLoadingChildren = isFolder && loadingPaths.has(nodePath)

  return (
    <div>
      <button
        onClick={() => {
          if (isFolder) {
            const nextExpanded = !expanded
            setExpanded(nextExpanded)
            if (nextExpanded && node.children == null) {
              onToggle(node)
            }
          } else {
            onSelect(node)
          }
        }}
        className={cn(
          "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-secondary transition-colors",
          isSelected && "bg-secondary",
        )}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
      >
        {isFolder ? (
          <>
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            )}
            <Folder className="h-4 w-4 text-muted-foreground" />
          </>
        ) : (
          <>
            <span className="w-3.5" />
            <FileText className="h-4 w-4 text-muted-foreground" />
          </>
        )}
        <span className="flex-1 truncate text-left text-foreground">{node.name}</span>
        {node.size_bytes ? (
          <span className="text-xs text-muted-foreground">
            {formatSize(node.size_bytes)}
          </span>
        ) : null}
      </button>

      {isFolder && expanded && (
        <div>
          {node.children?.length ? (
            node.children.map((child) => (
              <FileTreeItem
                key={child.path ?? `${nodePath}-${child.name}`}
                node={child}
                depth={depth + 1}
                selectedFile={selectedFile}
                onSelect={onSelect}
                onToggle={onToggle}
                loadingPaths={loadingPaths}
              />
            ))
          ) : isLoadingChildren ? (
            <div className="px-4 py-1.5 text-xs text-muted-foreground" style={{ paddingLeft: `${(depth + 1) * 12 + 8}px` }}>
              {tWorkspace("tree.loading")}
            </div>
          ) : (
            <div className="px-4 py-1.5 text-xs text-muted-foreground" style={{ paddingLeft: `${(depth + 1) * 12 + 8}px` }}>
              {tWorkspace("tree.empty")}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function WorkspacePanel() {
  const tWorkspace = useTranslations("workspace")
  const tCommon = useTranslations("common")
  const tAccessibility = useTranslations("accessibility")

  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null)
  const { activeProjectId } = useProjectContext()
  const [rootPath] = useState(".")
  const [fileTree, setFileTree] = useState<FileNode[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadingPaths, setLoadingPaths] = useState<Set<string>>(new Set())
  const [previewContent, setPreviewContent] = useState<string | null>(null)
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading" | "ready" | "error">("idle")
  const [previewError, setPreviewError] = useState<string | null>(null)
  const previewLines = 80

  const fetchFiles = useCallback(async () => {
    if (!activeProjectId) {
      setFileTree([])
      setLoadingPaths(new Set())
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    setLoadingPaths(new Set())
    try {
      const { data } = await apiRequest<{ path: string; files: FileNode[] }>("/files", {
        params: { project_id: activeProjectId, path: rootPath, recursive: false },
      })
      setFileTree(data.files)
    } catch (error) {
      const message = getApiErrorMessage(error, tWorkspace("errors.loadFilesFailed"))
      toast.error(message)
      // Fallback to empty array on error
      setFileTree([])
    } finally {
      setIsLoading(false)
    }
  }, [activeProjectId, rootPath, tWorkspace])

  const updateTreeNodes = (
    nodes: FileNode[],
    targetPath: string,
    children: FileNode[]
  ): FileNode[] =>
    nodes.map((node) => {
      if (node.path === targetPath) {
        return { ...node, children }
      }
      if (node.children) {
        return { ...node, children: updateTreeNodes(node.children, targetPath, children) }
      }
      return node
    })

  const loadChildren = async (node: FileNode) => {
    if (!activeProjectId || node.type !== "directory" || !node.path) return
    if (loadingPaths.has(node.path)) return
    setLoadingPaths((prev) => new Set(prev).add(node.path as string))
    try {
      const { data } = await apiRequest<{ path: string; files: FileNode[] }>("/files", {
        params: { project_id: activeProjectId, path: node.path, recursive: false },
      })
      setFileTree((prev) => updateTreeNodes(prev, node.path as string, data.files.filter((f) => !f.name.startsWith("."))))
    } catch (error) {
      const message = getApiErrorMessage(error, tWorkspace("errors.loadFolderFailed"))
      toast.error(message)
    } finally {
      setLoadingPaths((prev) => {
        const next = new Set(prev)
        next.delete(node.path as string)
        return next
      })
    }
  }

  useEffect(() => {
    fetchFiles()
  }, [fetchFiles])

  useEffect(() => {
    setPreviewContent(null)
    setPreviewStatus("idle")
    setPreviewError(null)
  }, [selectedFile?.path])

  const handlePreview = async () => {
    if (!selectedFile?.path || !activeProjectId) return
    if (selectedFile.type !== "file") return
    setPreviewStatus("loading")
    setPreviewError(null)
    try {
      const { data } = await apiRequest<{ content: string }>("/files/read", {
        params: { project_id: activeProjectId, path: selectedFile.path, lines: previewLines },
      })
      setPreviewContent(data.content || "")
      setPreviewStatus("ready")
    } catch (error) {
      const message = getApiErrorMessage(error, tWorkspace("errors.previewFailed"))
      setPreviewError(message)
      setPreviewStatus("error")
      toast.error(message)
    }
  }

  const handleDownload = () => {
    if (!selectedFile?.path || !activeProjectId) return
    const url = buildApiUrl("/files/download", {
      project_id: activeProjectId,
      path: selectedFile.path,
    })
    openInNewTab(url)
  }

  const handleDelete = () => {
    if (!selectedFile?.path || !activeProjectId) return
    toast.warning(tWorkspace("toasts.deleteConfirmTitle", { name: selectedFile.name }), {
      description: tWorkspace("toasts.deleteConfirmDescription"),
      action: {
        label: tCommon("confirm"),
        onClick: async () => {
          try {
            await apiRequest("/files", {
              method: "DELETE",
              params: { project_id: activeProjectId, path: selectedFile.path },
            })
            setSelectedFile(null)
            fetchFiles()
          } catch (error) {
            const message = getApiErrorMessage(error, tWorkspace("errors.deleteFailed"))
            toast.error(message)
          }
        },
      },
    })
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="text-sm font-medium text-foreground truncate">{rootPath}</span>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-foreground"
          onClick={fetchFiles}
          aria-label={tAccessibility("refreshWorkspace")}
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* File Tree */}
      <div className="flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <div className="px-3 py-2 text-xs text-muted-foreground">{tWorkspace("loading")}</div>
        ) : fileTree.length ? (
          fileTree.filter((n) => !n.name.startsWith(".")).map((node, index) => (
            <FileTreeItem
              key={node.path ?? `${node.name}-${index}`}
              node={node}
              depth={0}
              selectedFile={selectedFile?.path ?? null}
              onSelect={setSelectedFile}
              onToggle={loadChildren}
              loadingPaths={loadingPaths}
            />
          ))
        ) : (
          <div className="px-3 py-2 text-xs text-muted-foreground">{tWorkspace("noFiles")}</div>
        )}
      </div>

      {/* Selected File Actions */}
      {selectedFile && (
        <div className="border-t border-border p-4 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">{tWorkspace("selected")}</p>
              <p className="text-sm font-medium text-foreground">{selectedFile.name}</p>
              {selectedFile.path && (
                <p className="text-xs font-mono text-muted-foreground break-all">{selectedFile.path}</p>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 bg-transparent"
                onClick={handlePreview}
                disabled={selectedFile.type !== "file" || previewStatus === "loading"}
              >
                {previewStatus === "loading" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
                ) : (
                  <Eye className="h-3.5 w-3.5" />
                )}
                {tWorkspace("actions.preview")}
              </Button>
              <Button variant="outline" size="sm" className="gap-1.5 bg-transparent" onClick={handleDownload}>
                <Download className="h-3.5 w-3.5" />
                {tCommon("download")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 text-destructive hover:text-destructive bg-transparent"
                onClick={handleDelete}
              >
                <Trash2 className="h-3.5 w-3.5" />
                {tCommon("delete")}
              </Button>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-secondary/20 p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
              <span className="uppercase tracking-wider">{tWorkspace("preview.title")}</span>
              <span>{selectedFile.type === "file" ? tWorkspace("preview.lines", { count: previewLines }) : tWorkspace("preview.folder")}</span>
            </div>
            {selectedFile.type !== "file" ? (
              <div className="text-xs text-muted-foreground">{tWorkspace("preview.filesOnly")}</div>
            ) : previewStatus === "loading" ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
                {tWorkspace("preview.loading")}
              </div>
            ) : previewStatus === "error" ? (
              <div className="text-xs text-destructive">{previewError || tWorkspace("preview.unable")}</div>
            ) : previewContent ? (
              <pre className="max-h-40 overflow-auto rounded-lg bg-background/80 p-2 text-xs-tight leading-relaxed text-foreground font-mono whitespace-pre-wrap">
                {previewContent}
              </pre>
            ) : (
              <div className="text-xs text-muted-foreground">{tWorkspace("preview.clickToLoad")}</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

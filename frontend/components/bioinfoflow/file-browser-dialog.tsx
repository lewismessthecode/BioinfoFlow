"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { Folder, FileIcon, ChevronRight, ArrowUp, Home, Loader2, Upload, FolderOpen, FolderSearch, Package, BookOpen, Database, PlayCircle } from "@/lib/icons"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { apiRequest } from "@/lib/api"
import type { StorageSourceKind } from "@/lib/storage-source-policy"
import { cn } from "@/lib/utils"
import { useTranslations } from "next-intl"

type StorageSource = {
  id: string
  label: string
  kind: StorageSourceKind
  upload_allowed?: boolean
}

type FileInfo = {
  name: string
  path: string
  uri: string
  type: "file" | "directory"
  size_bytes?: number | null
}

interface FileBrowserDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectId: string
  basePath: string
  onSelect: (assetUri: string) => void
  allowSuffixes?: string[]
  allowedSourceKinds?: StorageSourceKind[]
  title?: string
  preferredSourceKind?: StorageSourceKind
}

export function FileBrowserDialog({
  open,
  onOpenChange,
  projectId,
  basePath,
  onSelect,
  allowSuffixes,
  allowedSourceKinds,
  title,
  preferredSourceKind,
}: FileBrowserDialogProps) {
  const t = useTranslations("common")
  const tFb = useTranslations("fileBrowser")
  const [sources, setSources] = useState<StorageSource[]>([])
  const [activeSourceId, setActiveSourceId] = useState<string>("project")
  const [currentPath, setCurrentPath] = useState(basePath)
  const [items, setItems] = useState<FileInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pathInput, setPathInput] = useState(basePath === "." ? "" : basePath)
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const activeSource = sources.find((source) => source.id === activeSourceId) ?? null

  const fetchSources = useCallback(async () => {
    if (!open || !projectId) return
    try {
      const { data } = await apiRequest<StorageSource[]>("/storage/sources", {
        params: { project_id: projectId },
      })
      const ordered = [...data].sort(
        (a, b) => sourceKindOrder(a.kind) - sourceKindOrder(b.kind),
      )
      const allowedSet =
        allowedSourceKinds && allowedSourceKinds.length > 0
          ? new Set(allowedSourceKinds)
          : null
      const visible = allowedSet
        ? ordered.filter((source) => allowedSet.has(source.kind))
        : ordered
      setSources(visible)
      const preferred =
        visible.find((source) => source.kind === preferredSourceKind)
        ?? visible.find((source) => source.id === "project")
        ?? visible[0]
      setActiveSourceId(preferred?.id ?? "")
    } catch {
      setSources([])
      setError(tFb("errors.loadSources"))
    }
    // tFb is stable in production next-intl but recreates each render
    // under the test mock; depending on it here re-fires the effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowedSourceKinds, open, preferredSourceKind, projectId])

  const fetchFiles = useCallback(async () => {
    if (!open || !projectId || !activeSourceId) return
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, string | boolean> = {
        project_id: projectId,
        source_id: activeSourceId,
        path: currentPath,
        recursive: false,
      }
      const { data } = await apiRequest<{ path: string; files: FileInfo[] }>("/storage/browse", {
        params,
      })
      let files = data.files ?? []
      // Hide engine-local scratch files if a source ever exposes them directly.
      files = files.filter((f) => {
        const n = f.name
        if (n === ".nextflow" || n.startsWith(".nextflow.log")) return false
        return true
      })
      files.sort((a, b) => {
        if (a.type !== b.type) return a.type === "directory" ? -1 : 1
        return a.name.localeCompare(b.name)
      })
      setItems(files)
      setError(null)
    } catch {
      setError(tFb("errors.loadDirectory"))
      setItems([])
    } finally {
      setLoading(false)
    }
    // See fetchSources above — tFb is intentionally omitted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSourceId, currentPath, open, projectId])

  // Reset to basePath when dialog opens
  useEffect(() => {
    if (open) {
      setCurrentPath(basePath)
      setPathInput(basePath === "." ? "" : basePath)
    }
  }, [open, basePath])

  useEffect(() => {
    void fetchSources()
  }, [fetchSources])

  useEffect(() => {
    void fetchFiles()
  }, [fetchFiles])

  const navigateTo = (path: string) => {
    setCurrentPath(path)
    setPathInput(path === "." ? "" : path)
  }

  const handleNavigateInto = (dirName: string) => {
    const next = currentPath === "." ? dirName : `${currentPath}/${dirName}`
    navigateTo(next)
  }

  const handleUp = () => {
    if (currentPath === "." || currentPath === "") return
    const parts = currentPath.split("/")
    parts.pop()
    navigateTo(parts.length === 0 ? "." : parts.join("/"))
  }

  const handleHome = () => {
    navigateTo(".")
  }

  const handlePathSubmit = () => {
    const p = pathInput.trim()
    navigateTo(p || ".")
  }

  const handleSelect = (file: FileInfo) => {
    if (file.type === "directory") {
      handleNavigateInto(file.name)
      return
    }
    onSelect(file.uri)
    onOpenChange(false)
  }

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      const formData = new FormData()
      formData.set("project_id", projectId)
      formData.set("source_id", activeSourceId)
      formData.set("path", currentPath)
      formData.set("file", file)
      const { data } = await apiRequest<{ uri: string }>("/storage/upload", {
        method: "POST",
        body: formData,
      })
      await fetchFiles()
      onSelect(data.uri)
      onOpenChange(false)
    } catch {
      setError(tFb("errors.upload"))
    } finally {
      event.target.value = ""
    }
  }

  const matchesSuffix = (name: string) => {
    if (!allowSuffixes?.length) return true
    const lower = name.toLowerCase()
    return allowSuffixes.some((s) => lower.endsWith(s.toLowerCase()))
  }

  const visibleItems = items.filter((f) =>
    f.type === "directory" ? true : matchesSuffix(f.name),
  )

  // Breadcrumb segments
  const pathSegments = currentPath === "." ? [] : currentPath.split("/")

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[560px] p-0 flex flex-col gap-0 rounded-lg overflow-hidden">
        <DialogHeader className="shrink-0 px-4 pt-3.5 pb-2">
          <DialogTitle className="text-sm font-semibold tracking-tight">
            {title ?? tFb("title")}
          </DialogTitle>
        </DialogHeader>

        {/* Storage source — segmented control */}
        {sources.length > 0 && (
          <div className="px-4 pb-2 shrink-0">
            <div className="inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-lg bg-muted/60 p-1">
              {sources.map((source) => {
                const Icon = sourceKindIcon(source.kind)
                const isActive = activeSourceId === source.id
                return (
                  <button
                    key={source.id}
                    type="button"
                    aria-pressed={isActive}
                    className={cn(
                      "inline-flex shrink-0 items-center gap-1.5 h-7 px-2.5 rounded-md text-xs-tight font-medium transition-colors",
                      isActive
                        ? "bg-background shadow-sm text-foreground ring-1 ring-border/40"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                    onClick={() => {
                      setActiveSourceId(source.id)
                      navigateTo(".")
                    }}
                  >
                    <Icon className="h-3.5 w-3.5 shrink-0" />
                    {source.label}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Navigation bar */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border/40 shrink-0">
          <div className="inline-flex shrink-0 rounded-md border border-border/60 bg-background divide-x divide-border/60 overflow-hidden">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 rounded-none"
              onClick={handleHome}
              title={tFb("home")}
              aria-label={tFb("home")}
            >
              <Home className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 rounded-none"
              onClick={handleUp}
              disabled={currentPath === "." || currentPath === ""}
              title={tFb("up")}
              aria-label={tFb("up")}
            >
              <ArrowUp className="h-3.5 w-3.5" />
            </Button>
          </div>
          <form
            className="flex-1 min-w-0"
            onSubmit={(e) => {
              e.preventDefault()
              handlePathSubmit()
            }}
          >
            <Input
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              placeholder="."
              className="h-7 rounded-md text-xs-tight font-mono"
            />
          </form>
          {activeSource?.upload_allowed ? (
            <>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0 rounded-md"
                onClick={() => uploadInputRef.current?.click()}
                title={t("upload")}
              >
                <Upload className="h-3.5 w-3.5" />
              </Button>
              <input
                ref={uploadInputRef}
                type="file"
                className="hidden"
                onChange={handleUpload}
              />
            </>
          ) : null}
          {allowSuffixes && (
            <Badge variant="outline" className="text-2xs font-mono shrink-0">
              {allowSuffixes.slice(0, 2).join(" ")}
            </Badge>
          )}
        </div>

        {/* Breadcrumb */}
        {pathSegments.length > 0 && (
          <div className="flex items-center gap-1 px-4 py-2 text-[11px] text-muted-foreground border-b border-border/40 shrink-0 overflow-x-auto">
            <button
              type="button"
              className="shrink-0 font-medium hover:text-foreground"
              onClick={handleHome}
            >
              ~
            </button>
            {pathSegments.map((seg, i) => (
              <span key={i} className="flex items-center gap-1 shrink-0">
                <ChevronRight className="h-3 w-3 opacity-60" />
                <button
                  type="button"
                  className="hover:text-foreground"
                  onClick={() => navigateTo(pathSegments.slice(0, i + 1).join("/"))}
                >
                  {seg}
                </button>
              </span>
            ))}
          </div>
        )}

        {/* File list */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {loading ? (
            <div className="flex min-h-full items-center justify-center py-10 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          ) : error ? (
            <div className="flex min-h-full items-center justify-center px-4 py-10 text-center text-xs text-destructive">
              {error}
            </div>
          ) : visibleItems.length === 0 ? (
            <div className="flex min-h-full flex-col items-center justify-center gap-2 px-4 py-10 text-center">
              <FolderSearch className="h-8 w-8 text-muted-foreground/40" strokeWidth={1.5} />
              <p className="text-sm text-foreground/80">
                {items.length > 0
                  ? `No files matching ${allowSuffixes?.join(", ") ?? "filter"}`
                  : tFb("emptyHere")}
              </p>
              <p className="text-xs text-muted-foreground">
                {activeSource
                  ? tFb("emptyAtSource", { source: activeSource.label })
                  : tFb("emptyHere")}
              </p>
            </div>
          ) : (
            <div className="py-0.5">
              {visibleItems.map((item) => (
                <button
                  key={item.path}
                  type="button"
                  className={cn(
                    "w-full flex items-center gap-2 px-4 py-1.5 text-xs hover:bg-accent/50 transition-colors",
                    item.type === "file" && "hover:bg-primary/5",
                  )}
                  onClick={() => handleSelect(item)}
                >
                  {item.type === "directory" ? (
                    <Folder className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                  ) : (
                    <FileIcon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  )}
                  <span className="truncate font-mono text-xs-tight">{item.name}</span>
                  {item.type === "directory" && (
                    <ChevronRight className="h-3 w-3 text-muted-foreground/30 ml-auto shrink-0" />
                  )}
                  {item.type === "file" && item.size_bytes != null && (
                    <span className="text-2xs text-muted-foreground/50 ml-auto shrink-0 tabular-nums">
                      {formatSize(item.size_bytes)}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="shrink-0 flex items-center justify-end gap-2 px-4 py-2.5 border-t border-border/40">
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs-tight"
            onClick={() => onOpenChange(false)}
          >
            {t("cancel")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const SOURCE_KIND_ORDER: Record<StorageSourceKind, number> = {
  deliveries: 0,
  reference: 1,
  database: 2,
  project: 3,
  results: 4,
}

function sourceKindOrder(kind: StorageSourceKind): number {
  return SOURCE_KIND_ORDER[kind] ?? 99
}

function sourceKindIcon(kind: StorageSourceKind) {
  switch (kind) {
    case "project":
      return FolderOpen
    case "deliveries":
      return Package
    case "reference":
      return BookOpen
    case "database":
      return Database
    case "results":
      return PlayCircle
    default:
      return Folder
  }
}

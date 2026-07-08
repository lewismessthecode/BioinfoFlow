"use client"

import {
  Braces,
  ChevronDown,
  ChevronRight,
  ChevronsUp,
  Copy,
  File as FileIcon,
  FileCode2,
  FileSpreadsheet,
  FileText,
  Folder,
  Loader2,
  Paperclip,
  RefreshCw,
  Search,
  TerminalSquare,
  X,
} from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentFsEntry } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function AgentWorkspaceTree({
  entries,
  className,
  filter,
  onFilterChange,
  rootLoading = false,
  expandedPaths,
  childrenByPath,
  loadingPaths,
  errorByPath,
  selectedPath,
  loadedNodeCount,
  onRefresh,
  onCollapseAll,
  onToggleDirectory,
  onOpenFile,
  onAddFile,
  onCopyPath,
}: {
  entries: AgentFsEntry[]
  className?: string
  filter: string
  onFilterChange: (value: string) => void
  rootLoading?: boolean
  expandedPaths: Set<string>
  childrenByPath: Record<string, AgentFsEntry[]>
  loadingPaths: Set<string>
  errorByPath: Record<string, string>
  selectedPath: string | null
  loadedNodeCount: number
  onRefresh: () => void
  onCollapseAll: () => void
  onToggleDirectory: (entry: AgentFsEntry) => void
  onOpenFile: (entry: AgentFsEntry) => void
  onAddFile: (path: string) => void
  onCopyPath: (path: string) => void
}) {
  const t = useTranslations("agentRuntime")
  const normalized = filter.trim().toLowerCase()
  const visibleEntries = filterEntries(entries, normalized, childrenByPath)

  return (
    <div
      className={cn("flex min-h-0 min-w-0 flex-col overflow-hidden", className)}
      data-testid="agent-workspace-tree"
    >
      <div className="flex shrink-0 items-center gap-1 border-b border-border/55 px-2 py-2">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">{t("files.search")}</span>
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={filter}
            onChange={(event) => onFilterChange(event.target.value)}
            placeholder={t("files.search")}
            aria-label={t("files.search")}
            className="h-8 w-full rounded-[6px] border border-border/65 bg-background px-7 text-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring"
          />
          {filter ? (
            <button
              type="button"
              className="absolute right-1.5 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-[5px] text-muted-foreground hover:bg-muted/55 hover:text-foreground"
              onClick={() => onFilterChange("")}
              aria-label={t("files.clearSearch")}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </label>
        <button
          type="button"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[6px] text-muted-foreground hover:bg-muted/55 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
          onClick={onRefresh}
          aria-label={t("files.refresh")}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", rootLoading && "animate-spin")} />
        </button>
        <button
          type="button"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[6px] text-muted-foreground hover:bg-muted/55 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
          onClick={onCollapseAll}
          aria-label={t("files.collapseAll")}
        >
          <ChevronsUp className="h-4 w-4" />
        </button>
      </div>
      {normalized ? (
        <div className="shrink-0 border-b border-border/55 px-3 py-1.5 text-[11px] text-muted-foreground">
          {t("files.loadedOnly", { count: loadedNodeCount })}
        </div>
      ) : null}
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden px-1.5 py-2">
        <div className="grid min-w-0 gap-0.5">
        <TreeRows
          entries={visibleEntries}
          depth={0}
          normalizedFilter={normalized}
          expandedPaths={expandedPaths}
          childrenByPath={childrenByPath}
          loadingPaths={loadingPaths}
          errorByPath={errorByPath}
          selectedPath={selectedPath}
          onToggleDirectory={onToggleDirectory}
          onOpenFile={onOpenFile}
          onAddFile={onAddFile}
          onCopyPath={onCopyPath}
        />
        {!visibleEntries.length ? (
          <p className="text-sm text-muted-foreground">{t("files.empty")}</p>
        ) : null}
        </div>
      </div>
    </div>
  )
}

function TreeRows({
  entries,
  depth,
  normalizedFilter,
  expandedPaths,
  childrenByPath,
  loadingPaths,
  errorByPath,
  selectedPath,
  onToggleDirectory,
  onOpenFile,
  onAddFile,
  onCopyPath,
}: {
  entries: AgentFsEntry[]
  depth: number
  normalizedFilter: string
  expandedPaths: Set<string>
  childrenByPath: Record<string, AgentFsEntry[]>
  loadingPaths: Set<string>
  errorByPath: Record<string, string>
  selectedPath: string | null
  onToggleDirectory: (entry: AgentFsEntry) => void
  onOpenFile: (entry: AgentFsEntry) => void
  onAddFile: (path: string) => void
  onCopyPath: (path: string) => void
}) {
  const t = useTranslations("agentRuntime")

  return entries.map((entry) => {
    const expanded = expandedPaths.has(entry.path)
    const children = childrenByPath[entry.path] ?? []
    const visibleChildren = filterEntries(children, normalizedFilter, childrenByPath)
    const revealChildren = entry.type === "dir" && (
      expanded || Boolean(normalizedFilter && visibleChildren.length)
    )
    const loading = loadingPaths.has(entry.path)
    const error = errorByPath[entry.path] ?? null
    const isSelected = selectedPath === entry.path
    const fileKind = entry.type === "dir" ? "folder" : fileKindFromName(entry.name)
    const FileGlyph = fileIconForKind(fileKind)

    return (
      <div key={entry.path} className="grid min-w-0 gap-0.5">
        <div
          aria-label={entry.name}
          aria-expanded={entry.type === "dir" ? expanded : undefined}
          data-selected={isSelected ? "true" : undefined}
          data-file-kind={fileKind}
          className={cn(
            "group flex min-h-7 min-w-0 items-center gap-1 rounded-[6px] py-1 pr-1 text-sm transition-colors hover:bg-muted/45",
            isSelected && "bg-muted/60 text-foreground",
          )}
          style={{ paddingLeft: `${depth * 14 + 8}px` }}
        >
          <button
            type="button"
            onClick={() => entry.type === "dir" ? onToggleDirectory(entry) : onOpenFile(entry)}
            className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden text-left"
            aria-label={entry.name}
            aria-current={isSelected ? "true" : undefined}
            title={entry.path}
          >
            {entry.type === "dir" ? (
              <>
                {expanded ? (
                  <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                )}
                <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
              </>
            ) : (
              <>
                <span className="h-3.5 w-3.5 shrink-0" />
                <FileGlyph className={cn("h-4 w-4 shrink-0", fileIconClassName(fileKind))} />
              </>
            )}
            <span className="min-w-0 flex-1 truncate text-foreground">{entry.name}</span>
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" /> : null}
          </button>
          <div
            className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100"
            data-testid="agent-workspace-tree-row-actions"
          >
            <button
              type="button"
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[5px] text-muted-foreground hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
              onClick={() => onCopyPath(entry.path)}
              aria-label={t("files.copyPath")}
            >
              <Copy className="h-3.5 w-3.5" />
            </button>
            {entry.type === "file" ? (
              <button
                type="button"
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[5px] text-muted-foreground hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
                onClick={() => onAddFile(entry.path)}
                aria-label={t("files.addToContext")}
              >
                <Paperclip className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
        </div>
        {error ? (
          <p className="px-2 text-xs text-destructive" style={{ paddingLeft: `${(depth + 1) * 14 + 8}px` }}>
            {error}
          </p>
        ) : null}
        {revealChildren ? (
          loading && !children.length ? (
            <div
              className="flex items-center gap-2 py-1.5 text-xs text-muted-foreground"
              style={{ paddingLeft: `${(depth + 1) * 14 + 8}px` }}
            >
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {t("files.loading")}
            </div>
          ) : visibleChildren.length ? (
            <TreeRows
              entries={visibleChildren}
              depth={depth + 1}
              normalizedFilter={normalizedFilter}
              expandedPaths={expandedPaths}
              childrenByPath={childrenByPath}
              loadingPaths={loadingPaths}
              errorByPath={errorByPath}
              selectedPath={selectedPath}
              onToggleDirectory={onToggleDirectory}
              onOpenFile={onOpenFile}
              onAddFile={onAddFile}
              onCopyPath={onCopyPath}
            />
          ) : (
            <div
              className="py-1.5 text-xs text-muted-foreground"
              style={{ paddingLeft: `${(depth + 1) * 14 + 8}px` }}
            >
              {t("files.empty")}
            </div>
          )
        ) : null}
      </div>
    )
  })
}

function fileKindFromName(name: string) {
  const lower = name.toLowerCase()
  if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "markdown"
  if (lower.endsWith(".wdl") || lower.endsWith(".nf") || lower.endsWith(".nextflow")) return "workflow"
  if (lower.endsWith(".json") || lower.endsWith(".jsonl") || lower.endsWith(".yaml") || lower.endsWith(".yml")) return "data"
  if (lower.endsWith(".csv") || lower.endsWith(".tsv") || lower.endsWith(".xlsx") || lower.endsWith(".xls")) return "table"
  if (lower.endsWith(".sh") || lower.endsWith(".bash") || lower === "dockerfile" || lower.includes("docker-compose")) return "shell"
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "code"
  if (lower.endsWith(".pdf") || lower.endsWith(".txt") || lower.endsWith(".log")) return "document"
  return "file"
}

function fileIconForKind(kind: string) {
  switch (kind) {
    case "markdown":
    case "document":
      return FileText
    case "workflow":
    case "code":
      return FileCode2
    case "data":
      return Braces
    case "table":
      return FileSpreadsheet
    case "shell":
      return TerminalSquare
    default:
      return FileIcon
  }
}

function fileIconClassName(kind: string) {
  switch (kind) {
    case "workflow":
    case "markdown":
    case "data":
    case "table":
    case "shell":
    case "code":
    case "document":
    default:
      return "text-muted-foreground"
  }
}

function filterEntries(
  entries: AgentFsEntry[],
  normalized: string,
  childrenByPath: Record<string, AgentFsEntry[]>,
): AgentFsEntry[] {
  if (!normalized) return entries
  return entries.filter((entry) => {
    if (entry.name.toLowerCase().includes(normalized)) return true
    if (entry.path.toLowerCase().includes(normalized)) return true
    return filterEntries(childrenByPath[entry.path] ?? [], normalized, childrenByPath).length > 0
  })
}

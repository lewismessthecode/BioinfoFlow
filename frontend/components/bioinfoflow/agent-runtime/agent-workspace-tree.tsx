"use client"

import { ChevronDown, ChevronRight, Copy, File as FileIcon, Folder, Loader2, Paperclip } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentFsEntry } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function AgentWorkspaceTree({
  entries,
  filter,
  onFilterChange,
  expandedPaths,
  childrenByPath,
  loadingPaths,
  errorByPath,
  selectedPath,
  loadedNodeCount,
  onToggleDirectory,
  onOpenFile,
  onAddFile,
  onCopyPath,
}: {
  entries: AgentFsEntry[]
  filter: string
  onFilterChange: (value: string) => void
  expandedPaths: Set<string>
  childrenByPath: Record<string, AgentFsEntry[]>
  loadingPaths: Set<string>
  errorByPath: Record<string, string>
  selectedPath: string | null
  loadedNodeCount: number
  onToggleDirectory: (entry: AgentFsEntry) => void
  onOpenFile: (entry: AgentFsEntry) => void
  onAddFile: (path: string) => void
  onCopyPath: (path: string) => void
}) {
  const t = useTranslations("agentRuntime")
  const normalized = filter.trim().toLowerCase()
  const visibleEntries = filterEntries(entries, normalized, childrenByPath)

  return (
    <div className="grid gap-2" data-testid="agent-workspace-tree">
      <input
        value={filter}
        onChange={(event) => onFilterChange(event.target.value)}
        placeholder={t("files.search")}
        className="h-9 rounded-full border border-border/70 bg-background px-3 text-sm outline-none placeholder:text-muted-foreground"
      />
      {normalized ? (
        <div className="text-[11px] text-muted-foreground">
          {t("files.loadedOnly", { count: loadedNodeCount })}
        </div>
      ) : null}
      <div className="grid gap-0.5">
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
    const loading = loadingPaths.has(entry.path)
    const error = errorByPath[entry.path] ?? null
    const isSelected = selectedPath === entry.path

    return (
      <div key={entry.path} className="grid gap-0.5">
        <div
          className={cn(
            "group flex items-center gap-1 rounded-lg py-1.5 pr-2 text-sm transition-colors hover:bg-muted/50",
            isSelected && "bg-muted text-foreground",
          )}
          style={{ paddingLeft: `${depth * 14 + 8}px` }}
        >
          <button
            type="button"
            onClick={() => entry.type === "dir" ? onToggleDirectory(entry) : onOpenFile(entry)}
            className="flex min-w-0 flex-1 items-center gap-2 text-left"
            aria-label={entry.name}
          >
            {entry.type === "dir" ? (
              <>
                {expanded ? (
                  <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                )}
                <Folder className="h-4 w-4 shrink-0 text-sky-500" />
              </>
            ) : (
              <>
                <span className="h-3.5 w-3.5 shrink-0" />
                <FileIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
              </>
            )}
            <span className="min-w-0 flex-1 truncate text-foreground">{entry.name}</span>
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" /> : null}
          </button>
          <button
            type="button"
            className="rounded-full p-1 text-muted-foreground opacity-70 hover:bg-background hover:text-foreground group-hover:opacity-100"
            onClick={() => onCopyPath(entry.path)}
            aria-label={t("files.copyPath")}
          >
            <Copy className="h-3.5 w-3.5" />
          </button>
          {entry.type === "file" ? (
            <button
              type="button"
              className="rounded-full p-1 text-muted-foreground opacity-70 hover:bg-background hover:text-foreground group-hover:opacity-100"
              onClick={() => onAddFile(entry.path)}
              aria-label={t("files.addToContext")}
            >
              <Paperclip className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
        {error ? (
          <p className="px-2 text-xs text-destructive" style={{ paddingLeft: `${(depth + 1) * 14 + 8}px` }}>
            {error}
          </p>
        ) : null}
        {entry.type === "dir" && expanded ? (
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

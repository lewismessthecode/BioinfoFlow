"use client"

import { Copy, File as FileIcon, Folder, Paperclip } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentFsEntry } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function AgentWorkspaceTree({
  entries,
  filter,
  onFilterChange,
  onOpenEntry,
  onAddFile,
  onCopyPath,
}: {
  entries: AgentFsEntry[]
  filter: string
  onFilterChange: (value: string) => void
  onOpenEntry: (entry: AgentFsEntry) => void
  onAddFile: (path: string) => void
  onCopyPath: (path: string) => void
}) {
  const t = useTranslations("agentRuntime")
  const normalized = filter.trim().toLowerCase()
  const visibleEntries = normalized
    ? entries.filter((entry) => entry.name.toLowerCase().includes(normalized) || entry.path.toLowerCase().includes(normalized))
    : entries

  return (
    <div className="grid gap-2" data-testid="agent-workspace-tree">
      <input
        value={filter}
        onChange={(event) => onFilterChange(event.target.value)}
        placeholder={t("files.search")}
        className="h-9 rounded-full border border-border/70 bg-background px-3 text-sm outline-none placeholder:text-muted-foreground"
      />
      <div className="grid gap-0.5">
        {visibleEntries.map((entry) => (
          <div
            key={entry.path}
            className="group flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm transition-colors hover:bg-muted/50"
          >
            <button
              type="button"
              onClick={() => onOpenEntry(entry)}
              className="flex min-w-0 flex-1 items-center gap-2 text-left"
            >
              {entry.type === "dir" ? (
                <Folder className="h-4 w-4 shrink-0 text-sky-500" />
              ) : (
                <FileIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
              )}
              <span className="min-w-0 flex-1 truncate text-foreground">{entry.name}</span>
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
                className={cn(
                  "rounded-full p-1 text-muted-foreground opacity-70 hover:bg-background hover:text-foreground group-hover:opacity-100",
                )}
                onClick={() => onAddFile(entry.path)}
                aria-label={t("files.addToContext")}
              >
                <Paperclip className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
        ))}
        {!visibleEntries.length ? (
          <p className="text-sm text-muted-foreground">{t("files.empty")}</p>
        ) : null}
      </div>
    </div>
  )
}

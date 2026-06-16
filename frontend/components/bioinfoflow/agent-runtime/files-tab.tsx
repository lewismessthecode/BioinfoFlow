"use client"

import { useCallback, useEffect, useState } from "react"
import { ChevronLeft, RefreshCw } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  getAgentFsFile,
  getAgentFsTree,
  type AgentFsEntry,
  type AgentFsFile,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { AgentFilePreview } from "./agent-file-preview"
import { AgentWorkspaceTree } from "./agent-workspace-tree"

type FilesTabProps = {
  projectId?: string | null
  onAddContext?: (path: string) => void
}

export function FilesTab({ projectId, onAddContext }: FilesTabProps) {
  const t = useTranslations("agentRuntime")
  const [dir, setDir] = useState<string | null>(null)
  const [entries, setEntries] = useState<AgentFsEntry[]>([])
  const [file, setFile] = useState<AgentFsFile | null>(null)
  const [filter, setFilter] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadDir = useCallback(
    async (path: string | null) => {
      setLoading(true)
      setError(null)
      try {
        const tree = await getAgentFsTree(path, projectId)
        setDir(tree.path)
        setEntries(tree.entries)
        setFile(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load files.")
      } finally {
        setLoading(false)
      }
    },
    [projectId],
  )

  useEffect(() => {
    void loadDir(null)
  }, [loadDir])

  const openFile = useCallback(
    async (path: string) => {
      setLoading(true)
      setError(null)
      try {
        setFile(await getAgentFsFile(path))
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load files.")
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  const openEntry = useCallback(
    (entry: AgentFsEntry) => {
      if (entry.type === "dir") {
        void loadDir(entry.path)
        return
      }
      void openFile(entry.path)
    },
    [loadDir, openFile],
  )

  const copyPath = useCallback((path: string) => {
    void navigator.clipboard?.writeText(path)
  }, [])

  const parentDir = dir ? dir.split("/").slice(0, -1).join("/") : null

  if (file) {
    return (
      <AgentFilePreview
        file={file}
        onBack={() => setFile(null)}
        onAddToContext={(path) => onAddContext?.(path)}
        onCopyPath={copyPath}
      />
    )
  }

  return (
    <div className="grid gap-2" data-testid="files-tab">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {parentDir ? (
            <button
              type="button"
              className="flex items-center gap-1 text-sm font-medium text-foreground"
              onClick={() => void loadDir(parentDir)}
            >
              <ChevronLeft className="h-4 w-4" />
              {t("files.up")}
            </button>
          ) : (
            <span className="text-sm font-medium text-foreground">{t("files.title")}</span>
          )}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 rounded-full text-muted-foreground"
          onClick={() => void loadDir(dir)}
          aria-label={t("files.refresh")}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
        </Button>
      </div>
      {dir ? (
        <div className="truncate font-mono text-[11px] text-muted-foreground">{dir}</div>
      ) : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <AgentWorkspaceTree
        entries={entries}
        filter={filter}
        onFilterChange={setFilter}
        onOpenEntry={openEntry}
        onAddFile={(path) => onAddContext?.(path)}
        onCopyPath={copyPath}
      />
    </div>
  )
}

"use client"

import { useCallback, useEffect, useState } from "react"
import { ChevronLeft, File as FileIcon, Folder, RefreshCw } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  getAgentFsFile,
  getAgentFsTree,
  type AgentFsEntry,
  type AgentFsFile,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function FilesTab() {
  const t = useTranslations("agentRuntime")
  const [dir, setDir] = useState<string | null>(null)
  const [entries, setEntries] = useState<AgentFsEntry[]>([])
  const [file, setFile] = useState<AgentFsFile | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadDir = useCallback(async (path: string | null) => {
    setLoading(true)
    setError(null)
    try {
      const tree = await getAgentFsTree(path)
      setDir(tree.path)
      setEntries(tree.entries)
      setFile(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : t("files.error"))
    } finally {
      setLoading(false)
    }
  }, [t])

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
        setError(err instanceof Error ? err.message : t("files.error"))
      } finally {
        setLoading(false)
      }
    },
    [t],
  )

  const parentDir = dir ? dir.split("/").slice(0, -1).join("/") : null

  if (file) {
    return (
      <div className="grid gap-3" data-testid="files-tab">
        <button
          type="button"
          className="flex w-fit items-center gap-1.5 text-sm font-medium text-foreground"
          onClick={() => setFile(null)}
        >
          <ChevronLeft className="h-4 w-4" />
          {t("files.back")}
        </button>
        <div className="break-words font-mono text-xs text-muted-foreground">{file.path}</div>
        <pre className="max-h-[62vh] overflow-auto rounded-2xl border border-border/70 bg-muted/30 p-3 text-xs leading-5 text-foreground">
          <code>{file.content || "—"}</code>
        </pre>
        {file.truncated ? (
          <p className="text-xs text-muted-foreground">{t("files.truncated")}</p>
        ) : null}
      </div>
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
      <div className="grid gap-0.5">
        {entries.map((entry) => (
          <button
            key={entry.path}
            type="button"
            onClick={() =>
              entry.type === "dir" ? void loadDir(entry.path) : void openFile(entry.path)
            }
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted/50"
          >
            {entry.type === "dir" ? (
              <Folder className="h-4 w-4 shrink-0 text-sky-500" />
            ) : (
              <FileIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
            )}
            <span className="min-w-0 flex-1 truncate text-foreground">{entry.name}</span>
          </button>
        ))}
        {!entries.length && !loading && !error ? (
          <p className="text-sm text-muted-foreground">{t("files.empty")}</p>
        ) : null}
      </div>
    </div>
  )
}

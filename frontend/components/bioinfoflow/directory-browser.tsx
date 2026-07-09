"use client"

import { useCallback, useEffect, useState } from "react"
import { useTranslations } from "next-intl"
import { ArrowUp, Folder, FolderOpen, Loader2 } from "@/lib/icons"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { apiRequest } from "@/lib/api"
import { browseRemoteConnectionDirectory } from "@/lib/demo-connections"

interface DirectoryEntry {
  name: string
  path: string
}

interface DirectoryListData {
  path: string
  parent: string | null
  directories: DirectoryEntry[]
}

interface DirectoryBrowserProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialPath?: string
  onSelect: (path: string) => void
  source?: "local" | "remote"
  remoteConnectionId?: string
}

export function DirectoryBrowser({
  open,
  onOpenChange,
  initialPath,
  onSelect,
  source = "local",
  remoteConnectionId,
}: DirectoryBrowserProps) {
  const t = useTranslations("sidebar")
  const tCommon = useTranslations("common")
  const tDir = useTranslations("directoryBrowser")
  const [currentPath, setCurrentPath] = useState<string>("")
  const [parentPath, setParentPath] = useState<string | null>(null)
  const [directories, setDirectories] = useState<DirectoryEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchDirectories = useCallback(async (path: string, fallbackToHome = false) => {
    setLoading(true)
    setError(null)
    try {
      if (source === "remote") {
        if (!remoteConnectionId) throw new Error(tDir("errors.remoteConnectionRequired"))
        const data = await browseRemoteConnectionDirectory(remoteConnectionId, path || "/")
        setCurrentPath(data.path)
        setParentPath(remoteParentPath(data.path))
        setDirectories(
          data.entries
            .filter((entry) => entry.type === "dir" || entry.kind === "directory")
            .map((entry) => ({ name: entry.name, path: entry.path })),
        )
      } else {
        const { data } = await apiRequest<DirectoryListData>(
          "/system/directories",
          { params: { path } }
        )
        setCurrentPath(data.path)
        setParentPath(data.parent)
        setDirectories(data.directories)
      }
    } catch (err) {
      if (fallbackToHome && source === "local" && path !== "~") {
        return fetchDirectories("~")
      }
      setCurrentPath("")
      setParentPath(null)
      setDirectories([])
      setError(err instanceof Error ? err.message : tDir("errors.load"))
    } finally {
      setLoading(false)
    }
    // tDir is stable in production next-intl but recreates on every
    // render in the test mock; depending on it here caused an infinite
    // refetch loop under vitest.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remoteConnectionId, source])

  useEffect(() => {
    if (open) {
      fetchDirectories(initialPath || (source === "remote" ? "/" : "~"), true)
    }
  }, [open, initialPath, source, fetchDirectories])

  const handleNavigate = (path: string) => {
    fetchDirectories(path)
  }

  const handleGoUp = () => {
    if (parentPath) {
      fetchDirectories(parentPath)
    }
  }

  const handleSelect = () => {
    onSelect(currentPath)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("directoryBrowser")}</DialogTitle>
          <DialogDescription>{t("selectDirectoryDescription")}</DialogDescription>
        </DialogHeader>

        {/* Current path breadcrumb */}
        <div className="rounded-md bg-muted px-3 py-2 text-sm font-mono text-muted-foreground truncate">
          {currentPath}
        </div>

        {/* Directory listing */}
        <div className="min-h-[200px] max-h-[300px] overflow-y-auto rounded-md border">
          {loading ? (
            <div className="flex items-center justify-center h-[200px]">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-[200px] text-sm text-destructive px-4 text-center">
              {error}
            </div>
          ) : (
            <div className="divide-y">
              {parentPath && (
                <button
                  type="button"
                  className="flex w-full items-center gap-3 px-3 py-2 text-sm hover:bg-secondary/50 transition-colors"
                  onClick={handleGoUp}
                  aria-label={t("goUp")}
                >
                  <ArrowUp className="h-4 w-4 text-muted-foreground" />
                  <span className="text-muted-foreground">..</span>
                </button>
              )}
              {directories.map((dir) => (
                <button
                  key={dir.path}
                  type="button"
                  className="flex w-full items-center gap-3 px-3 py-2 text-sm hover:bg-secondary/50 transition-colors group"
                  onClick={() => handleNavigate(dir.path)}
                >
                  <Folder className="h-4 w-4 text-muted-foreground group-hover:hidden" />
                  <FolderOpen className="h-4 w-4 text-muted-foreground hidden group-hover:block" />
                  <span>{dir.name}</span>
                </button>
              ))}
              {directories.length === 0 && !parentPath && (
                <div className="flex items-center justify-center h-[200px] text-sm text-muted-foreground">
                  {tDir("empty")}
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("cancel")}
          </Button>
          <Button onClick={handleSelect} disabled={loading || !currentPath}>
            {t("selectDirectory")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function remoteParentPath(path: string): string | null {
  const normalized = (path || "/").replace(/\/+$/, "") || "/"
  if (normalized === "/" || normalized === ".") return null
  const index = normalized.lastIndexOf("/")
  if (index <= 0) return "/"
  return normalized.slice(0, index)
}

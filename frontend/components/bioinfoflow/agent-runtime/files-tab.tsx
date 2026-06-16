"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { RefreshCw } from "lucide-react"
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

const ROOT_LOADING_KEY = "__root__"

export function FilesTab({ projectId, onAddContext }: FilesTabProps) {
  const t = useTranslations("agentRuntime")
  const [rootPath, setRootPath] = useState<string | null>(null)
  const [rootEntries, setRootEntries] = useState<AgentFsEntry[]>([])
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(() => new Set())
  const [childrenByPath, setChildrenByPath] = useState<Record<string, AgentFsEntry[]>>({})
  const [loadingPaths, setLoadingPaths] = useState<Set<string>>(() => new Set())
  const [errorByPath, setErrorByPath] = useState<Record<string, string>>({})
  const [selectedFile, setSelectedFile] = useState<AgentFsFile | null>(null)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [filter, setFilter] = useState("")

  const loadRoot = useCallback(async () => {
    setLoading(ROOT_LOADING_KEY, true)
    setErrorByPath((current) => omitKey(current, ROOT_LOADING_KEY))
    try {
      const tree = await getAgentFsTree(null, projectId)
      setRootPath(tree.path)
      setRootEntries(tree.entries)
    } catch (err) {
      setErrorByPath((current) => ({
        ...current,
        [ROOT_LOADING_KEY]: err instanceof Error ? err.message : "Could not load files.",
      }))
    } finally {
      setLoading(ROOT_LOADING_KEY, false)
    }
  }, [projectId])

  const loadChildren = useCallback(
    async (path: string) => {
      setLoading(path, true)
      setErrorByPath((current) => omitKey(current, path))
      try {
        const tree = await getAgentFsTree(path, projectId)
        setChildrenByPath((current) => ({ ...current, [path]: tree.entries }))
      } catch (err) {
        setErrorByPath((current) => ({
          ...current,
          [path]: err instanceof Error ? err.message : "Could not load files.",
        }))
      } finally {
        setLoading(path, false)
      }
    },
    [projectId],
  )

  useEffect(() => {
    void loadRoot()
  }, [loadRoot])

  const refresh = useCallback(async () => {
    await loadRoot()
    await Promise.all([...expandedPaths].map((path) => loadChildren(path)))
  }, [expandedPaths, loadChildren, loadRoot])

  const toggleDirectory = useCallback(
    (entry: AgentFsEntry) => {
      setExpandedPaths((current) => {
        const next = new Set(current)
        if (next.has(entry.path)) {
          next.delete(entry.path)
          return next
        }
        next.add(entry.path)
        return next
      })
      if (!childrenByPath[entry.path]) {
        void loadChildren(entry.path)
      }
    },
    [childrenByPath, loadChildren],
  )

  const openFile = useCallback(async (entry: AgentFsEntry) => {
    setSelectedPath(entry.path)
    setLoading(entry.path, true)
    setErrorByPath((current) => omitKey(current, entry.path))
    try {
      setSelectedFile(await getAgentFsFile(entry.path))
    } catch (err) {
      setErrorByPath((current) => ({
        ...current,
        [entry.path]: err instanceof Error ? err.message : "Could not load files.",
      }))
    } finally {
      setLoading(entry.path, false)
    }
  }, [])

  const copyPath = useCallback((path: string) => {
    void navigator.clipboard?.writeText(path)
  }, [])

  const rootError = errorByPath[ROOT_LOADING_KEY] ?? null
  const rootLoading = loadingPaths.has(ROOT_LOADING_KEY)
  const loadedNodeCount = useMemo(
    () => rootEntries.length + Object.values(childrenByPath).reduce((sum, entries) => sum + entries.length, 0),
    [childrenByPath, rootEntries],
  )

  return (
    <div className="grid gap-3" data-testid="files-tab">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-medium text-foreground">{t("files.title")}</div>
          {rootPath ? (
            <div className="truncate font-mono text-[11px] text-muted-foreground">
              {rootPath}
            </div>
          ) : null}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 rounded-full text-muted-foreground"
          onClick={() => void refresh()}
          aria-label={t("files.refresh")}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", rootLoading && "animate-spin")} />
        </Button>
      </div>

      {rootError ? <p className="text-sm text-destructive">{rootError}</p> : null}
      <AgentWorkspaceTree
        entries={rootEntries}
        filter={filter}
        onFilterChange={setFilter}
        expandedPaths={expandedPaths}
        childrenByPath={childrenByPath}
        loadingPaths={loadingPaths}
        errorByPath={errorByPath}
        selectedPath={selectedPath}
        loadedNodeCount={loadedNodeCount}
        onToggleDirectory={toggleDirectory}
        onOpenFile={openFile}
        onAddFile={(path) => onAddContext?.(path)}
        onCopyPath={copyPath}
      />

      {selectedFile ? (
        <AgentFilePreview
          file={selectedFile}
          onBack={() => {
            setSelectedFile(null)
            setSelectedPath(null)
          }}
          onAddToContext={(path) => onAddContext?.(path)}
          onCopyPath={copyPath}
        />
      ) : null}
    </div>
  )

  function setLoading(path: string, loading: boolean) {
    setLoadingPaths((current) => {
      const next = new Set(current)
      if (loading) next.add(path)
      else next.delete(path)
      return next
    })
  }
}

function omitKey<T>(record: Record<string, T>, key: string) {
  return Object.fromEntries(
    Object.entries(record).filter(([entryKey]) => entryKey !== key),
  ) as Record<string, T>
}

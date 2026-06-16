"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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
  const fileRequestId = useRef(0)
  const fileRequestByPath = useRef<Record<string, number>>({})
  const treeRequestId = useRef(0)
  const treeRequestByPath = useRef<Record<string, number>>({})

  const resetTree = useCallback(() => {
    fileRequestId.current += 1
    fileRequestByPath.current = {}
    treeRequestByPath.current = {}
    setRootPath(null)
    setRootEntries([])
    setExpandedPaths(new Set())
    setChildrenByPath({})
    setLoadingPaths(new Set())
    setErrorByPath({})
    setSelectedFile(null)
    setSelectedPath(null)
  }, [])

  const loadRoot = useCallback(async () => {
    const requestId = beginTreeRequest(ROOT_LOADING_KEY)
    setLoading(ROOT_LOADING_KEY, true)
    setErrorByPath((current) => omitKey(current, ROOT_LOADING_KEY))
    try {
      const tree = await getAgentFsTree(null, projectId)
      if (isCurrentTreeRequest(ROOT_LOADING_KEY, requestId)) {
        setRootPath(tree.path)
        setRootEntries(tree.entries)
      }
    } catch (err) {
      if (isCurrentTreeRequest(ROOT_LOADING_KEY, requestId)) {
        setErrorByPath((current) => ({
          ...current,
          [ROOT_LOADING_KEY]: err instanceof Error ? err.message : "Could not load files.",
        }))
      }
    } finally {
      if (isCurrentTreeRequest(ROOT_LOADING_KEY, requestId)) setLoading(ROOT_LOADING_KEY, false)
    }
  }, [projectId])

  const loadChildren = useCallback(
    async (path: string) => {
      const requestId = beginTreeRequest(path)
      setLoading(path, true)
      setErrorByPath((current) => omitKey(current, path))
      try {
        const tree = await getAgentFsTree(path, projectId)
        if (isCurrentTreeRequest(path, requestId)) {
          setChildrenByPath((current) => ({ ...current, [path]: tree.entries }))
        }
      } catch (err) {
        if (isCurrentTreeRequest(path, requestId)) {
          setErrorByPath((current) => ({
            ...current,
            [path]: err instanceof Error ? err.message : "Could not load files.",
          }))
        }
      } finally {
        if (isCurrentTreeRequest(path, requestId)) setLoading(path, false)
      }
    },
    [projectId],
  )

  const loadFile = useCallback(async (path: string) => {
    const requestId = beginFileRequest(path)
    setSelectedPath(path)
    setSelectedFile(null)
    setLoading(path, true)
    setErrorByPath((current) => omitKey(current, path))
    try {
      const file = await getAgentFsFile(path)
      if (isCurrentFileRequest(requestId)) setSelectedFile(file)
    } catch (err) {
      if (isCurrentFileRequest(requestId)) {
        setErrorByPath((current) => ({
          ...current,
          [path]: err instanceof Error ? err.message : "Could not load files.",
        }))
      }
    } finally {
      if (isCurrentFilePathRequest(path, requestId)) setLoading(path, false)
    }
  }, [])

  useEffect(() => {
    resetTree()
    void loadRoot()
  }, [loadRoot, resetTree])

  const refresh = useCallback(async () => {
    const pathsToReload = [...new Set([...Object.keys(childrenByPath), ...expandedPaths])]
    const filePath = selectedPath
    await Promise.all([
      loadRoot(),
      ...pathsToReload.map((path) => loadChildren(path)),
      filePath ? loadFile(filePath) : Promise.resolve(),
    ])
  }, [childrenByPath, expandedPaths, loadChildren, loadFile, loadRoot, selectedPath])

  const toggleDirectory = useCallback(
    (entry: AgentFsEntry) => {
      const isExpanded = expandedPaths.has(entry.path)
      setExpandedPaths((current) => {
        const next = new Set(current)
        if (next.has(entry.path)) {
          next.delete(entry.path)
          return next
        }
        next.add(entry.path)
        return next
      })
      if (!isExpanded && !childrenByPath[entry.path] && !loadingPaths.has(entry.path)) {
        void loadChildren(entry.path)
      }
    },
    [childrenByPath, expandedPaths, loadingPaths, loadChildren],
  )

  const openFile = useCallback((entry: AgentFsEntry) => {
    void loadFile(entry.path)
  }, [loadFile])

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

  function beginTreeRequest(path: string) {
    const requestId = treeRequestId.current + 1
    treeRequestId.current = requestId
    treeRequestByPath.current[path] = requestId
    return requestId
  }

  function isCurrentTreeRequest(path: string, requestId: number) {
    return treeRequestByPath.current[path] === requestId
  }

  function beginFileRequest(path: string) {
    const requestId = fileRequestId.current + 1
    fileRequestId.current = requestId
    fileRequestByPath.current[path] = requestId
    return requestId
  }

  function isCurrentFileRequest(requestId: number) {
    return fileRequestId.current === requestId
  }

  function isCurrentFilePathRequest(path: string, requestId: number) {
    return fileRequestByPath.current[path] === requestId
  }
}

function omitKey<T>(record: Record<string, T>, key: string) {
  return Object.fromEntries(
    Object.entries(record).filter(([entryKey]) => entryKey !== key),
  ) as Record<string, T>
}

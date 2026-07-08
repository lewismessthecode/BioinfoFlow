"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react"
import { useTranslations } from "next-intl"

import {
  getAgentFsFile,
  getAgentFsTree,
  type AgentFsEntry,
  type AgentFsFile,
} from "@/lib/agent-runtime"
import { AgentFilePreview } from "./agent-file-preview"
import { AgentWorkspaceTree } from "./agent-workspace-tree"

type FilesTabProps = {
  projectId?: string | null
  onAddContext?: (path: string) => void
}

const ROOT_LOADING_KEY = "__root__"
const TREE_WIDTH_STORAGE_KEY = "agent-files-tree-width"
const DEFAULT_TREE_WIDTH = 280
const MIN_TREE_WIDTH = 240
const MAX_TREE_WIDTH = 400
const MIN_PREVIEW_WIDTH = 360
const RESIZER_WIDTH = 2

export function FilesTab({ projectId, onAddContext }: FilesTabProps) {
  const t = useTranslations("agentRuntime")
  const [rootEntries, setRootEntries] = useState<AgentFsEntry[]>([])
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(() => new Set())
  const [childrenByPath, setChildrenByPath] = useState<Record<string, AgentFsEntry[]>>({})
  const [loadingPaths, setLoadingPaths] = useState<Set<string>>(() => new Set())
  const [errorByPath, setErrorByPath] = useState<Record<string, string>>({})
  const [selectedFile, setSelectedFile] = useState<AgentFsFile | null>(null)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [filter, setFilter] = useState("")
  const [treeWidth, setTreeWidth] = useState(DEFAULT_TREE_WIDTH)
  const splitRef = useRef<HTMLDivElement | null>(null)
  const treeWidthStorageReady = useRef(false)
  const fileRequestId = useRef(0)
  const fileRequestByPath = useRef<Record<string, number>>({})
  const treeRequestId = useRef(0)
  const treeRequestByPath = useRef<Record<string, number>>({})

  const resetTree = useCallback(() => {
    fileRequestId.current += 1
    fileRequestByPath.current = {}
    treeRequestByPath.current = {}
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

  const collapseAll = useCallback(() => {
    setExpandedPaths(new Set())
  }, [])

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
  const splitStyle = {
    "--files-split-columns": `minmax(0,1fr) ${RESIZER_WIDTH}px minmax(${MIN_TREE_WIDTH}px, ${treeWidth}px)`,
  } as CSSProperties

  useEffect(() => {
    const storedValue = window.localStorage.getItem(TREE_WIDTH_STORAGE_KEY)
    if (storedValue) {
      const stored = Number(storedValue)
      if (Number.isFinite(stored)) {
        setTreeWidth(clampTreeWidth(stored, maxTreeWidthForSplit(splitRef.current)))
      }
    }
    treeWidthStorageReady.current = true
  }, [])

  useEffect(() => {
    const clampToAvailableSpace = () => {
      setTreeWidth((current) => clampTreeWidth(current, maxTreeWidthForSplit(splitRef.current)))
    }
    clampToAvailableSpace()
    window.addEventListener("resize", clampToAvailableSpace)
    return () => window.removeEventListener("resize", clampToAvailableSpace)
  }, [])

  useEffect(() => {
    if (!treeWidthStorageReady.current) return
    window.localStorage.setItem(TREE_WIDTH_STORAGE_KEY, String(treeWidth))
  }, [treeWidth])

  const updateTreeWidthFromPointer = useCallback((clientX: number) => {
    const split = splitRef.current
    if (!split) return
    const rect = split.getBoundingClientRect()
    setTreeWidth(clampTreeWidth(rect.right - clientX, maxTreeWidthForSplit(split)))
  }, [])

  const beginResize = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault()
      updateTreeWidthFromPointer(event.clientX)
      const handlePointerMove = (moveEvent: PointerEvent) => {
        updateTreeWidthFromPointer(moveEvent.clientX)
      }
      const stopResize = () => {
        window.removeEventListener("pointermove", handlePointerMove)
        window.removeEventListener("pointerup", stopResize)
      }
      window.addEventListener("pointermove", handlePointerMove)
      window.addEventListener("pointerup", stopResize, { once: true })
    },
    [updateTreeWidthFromPointer],
  )

  const nudgeTreeWidth = useCallback((delta: number) => {
    setTreeWidth((current) => clampTreeWidth(current + delta, maxTreeWidthForSplit(splitRef.current)))
  }, [])

  const setMaxTreeWidth = useCallback(() => {
    setTreeWidth(clampTreeWidth(MAX_TREE_WIDTH, maxTreeWidthForSplit(splitRef.current)))
  }, [])

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col" data-testid="files-tab">
      {rootError ? <p className="border-b border-border/55 px-3 py-2 text-sm text-destructive">{rootError}</p> : null}
      <div
        ref={splitRef}
        className="grid min-h-0 min-w-0 flex-1 grid-cols-1 overflow-hidden bg-background lg:grid-cols-[var(--files-split-columns)]"
        style={splitStyle}
        data-testid="files-tab-split"
      >
        <section
          className="min-h-[240px] min-w-0 overflow-hidden bg-background lg:min-h-0"
          data-testid="file-preview-pane"
        >
          {selectedFile ? (
            <AgentFilePreview
              file={selectedFile}
              className="h-full"
              onBack={() => {
                setSelectedFile(null)
                setSelectedPath(null)
              }}
              onAddToContext={(path) => onAddContext?.(path)}
              onCopyPath={copyPath}
            />
          ) : (
            <div className="flex h-full min-h-[240px] items-center justify-center p-4 text-center text-sm text-muted-foreground">
              {t("files.selectPreview")}
            </div>
          )}
        </section>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={t("files.resizeTree")}
          aria-valuemin={MIN_TREE_WIDTH}
          aria-valuemax={MAX_TREE_WIDTH}
          aria-valuenow={treeWidth}
          tabIndex={0}
          className="group hidden cursor-col-resize items-stretch justify-center bg-border/40 outline-none transition-colors hover:bg-border/70 focus-visible:bg-ring/45 lg:flex"
          data-testid="files-split-resizer"
          onPointerDown={beginResize}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") {
              event.preventDefault()
              nudgeTreeWidth(24)
            }
            if (event.key === "ArrowRight") {
              event.preventDefault()
              nudgeTreeWidth(-24)
            }
            if (event.key === "Home") {
              event.preventDefault()
              setTreeWidth(MIN_TREE_WIDTH)
            }
            if (event.key === "End") {
              event.preventDefault()
              setMaxTreeWidth()
            }
          }}
        >
          <span className="my-3 block w-px bg-border group-hover:bg-foreground/30" />
        </div>
        <section
          className="min-h-[260px] min-w-0 overflow-hidden border-t border-border/55 bg-background lg:min-h-0 lg:border-l lg:border-t-0"
          data-testid="file-tree-pane"
        >
          <AgentWorkspaceTree
            entries={rootEntries}
            className="h-full"
            filter={filter}
            onFilterChange={setFilter}
            rootLoading={rootLoading}
            expandedPaths={expandedPaths}
            childrenByPath={childrenByPath}
            loadingPaths={loadingPaths}
            errorByPath={errorByPath}
            selectedPath={selectedPath}
            loadedNodeCount={loadedNodeCount}
            onRefresh={() => void refresh()}
            onCollapseAll={collapseAll}
            onToggleDirectory={toggleDirectory}
            onOpenFile={openFile}
            onAddFile={(path) => onAddContext?.(path)}
            onCopyPath={copyPath}
          />
        </section>
      </div>
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

function clampTreeWidth(width: number, max = MAX_TREE_WIDTH) {
  return Math.min(Math.max(width, MIN_TREE_WIDTH), max)
}

function maxTreeWidthForSplit(split: HTMLDivElement | null) {
  if (!split) return MAX_TREE_WIDTH
  const width = split.getBoundingClientRect().width
  if (width <= 0) return MAX_TREE_WIDTH
  return Math.max(
    MIN_TREE_WIDTH,
    Math.min(MAX_TREE_WIDTH, width - MIN_PREVIEW_WIDTH - RESIZER_WIDTH),
  )
}

function omitKey<T>(record: Record<string, T>, key: string) {
  return Object.fromEntries(
    Object.entries(record).filter(([entryKey]) => entryKey !== key),
  ) as Record<string, T>
}

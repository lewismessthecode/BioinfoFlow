"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"
import { useOptionalWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"

type TerminalDockCommand = {
  id: number
  projectId: string
  type: "chdir"
  path: string
}

type TerminalDockContextValue = {
  enabled: boolean
  isMobile: boolean
  projectId?: string
  isOpen: boolean
  dockHeight: number
  pendingCommand: TerminalDockCommand | null
  openTerminal: () => void
  closeTerminal: () => void
  toggleTerminal: () => void
  setDockHeight: (height: number) => void
  clearPendingCommand: (id: number) => void
  chdir: (path: string) => void
}

const DEFAULT_DOCK_HEIGHT = 300
const MIN_DOCK_HEIGHT = 220
const MAX_DOCK_HEIGHT = 640

const TerminalDockContext = createContext<TerminalDockContextValue | null>(null)

const storageKey = (projectId: string, key: string) =>
  `terminal-dock:${projectId}:${key}`

const clampDockHeight = (height: number) =>
  Math.min(MAX_DOCK_HEIGHT, Math.max(MIN_DOCK_HEIGHT, height))

export function TerminalDockProvider({
  children,
  projectId,
  enabled,
  isMobile,
  routeSessionId,
}: {
  children: React.ReactNode
  projectId?: string
  enabled: boolean
  isMobile: boolean
  routeSessionId?: string | null
}) {
  const workspaceShell = useOptionalWorkspaceShell()
  const routeSession = routeSessionId
    ? Array.from(workspaceShell?.projectConversations.values() ?? [])
        .flat()
        .find((session) => session.id === routeSessionId)
    : null
  const routeScopeReady =
    !routeSessionId ||
    workspaceShell === null ||
    routeSession !== undefined
  const effectiveProjectId = routeSessionId
    ? workspaceShell === null
      ? projectId
      : routeSession?.project_id ?? undefined
    : projectId
  const effectiveEnabled = enabled && routeScopeReady && Boolean(effectiveProjectId)
  const [isOpen, setIsOpen] = useState(false)
  const [dockHeight, setDockHeightState] = useState(DEFAULT_DOCK_HEIGHT)
  const [pendingCommand, setPendingCommand] =
    useState<TerminalDockCommand | null>(null)

  useEffect(() => {
    if (!effectiveProjectId) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setIsOpen(false)
      setDockHeightState(DEFAULT_DOCK_HEIGHT)
      setPendingCommand(null)
      /* eslint-enable react-hooks/set-state-in-effect */
      return
    }
    const storedHeight = localStorage.getItem(storageKey(effectiveProjectId, "height"))
    const parsedHeight = storedHeight ? Number(storedHeight) : Number.NaN
    localStorage.removeItem(storageKey(effectiveProjectId, "open"))
    setIsOpen(false)
    setPendingCommand(null)
    setDockHeightState(
      Number.isFinite(parsedHeight)
        ? clampDockHeight(parsedHeight)
        : DEFAULT_DOCK_HEIGHT
    )
  }, [effectiveProjectId])

  useEffect(() => {
    if (!effectiveProjectId) return
    localStorage.setItem(storageKey(effectiveProjectId, "height"), String(dockHeight))
  }, [dockHeight, effectiveProjectId])

  useEffect(() => {
    if (!effectiveEnabled) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setIsOpen(false)
      setPendingCommand(null)
      /* eslint-enable react-hooks/set-state-in-effect */
    }
  }, [effectiveEnabled])

  const openTerminal = useCallback(() => {
    if (!effectiveEnabled || !effectiveProjectId) return
    setIsOpen(true)
  }, [effectiveEnabled, effectiveProjectId])

  const closeTerminal = useCallback(() => {
    setIsOpen(false)
  }, [])

  const toggleTerminal = useCallback(() => {
    if (!effectiveEnabled || !effectiveProjectId) return
    setIsOpen((prev) => !prev)
  }, [effectiveEnabled, effectiveProjectId])

  const setDockHeight = useCallback((height: number) => {
    setDockHeightState(clampDockHeight(height))
  }, [])

  const clearPendingCommand = useCallback((id: number) => {
    setPendingCommand((prev) => (prev?.id === id ? null : prev))
  }, [])

  const chdir = useCallback(
    (path: string) => {
      if (!effectiveEnabled || !effectiveProjectId || !isOpen) return
      setPendingCommand({
        id: Date.now(),
        projectId: effectiveProjectId,
        type: "chdir",
        path,
      })
    },
    [effectiveEnabled, effectiveProjectId, isOpen]
  )

  const value = useMemo(
    () => ({
      enabled: effectiveEnabled,
      isMobile,
      projectId: effectiveProjectId,
      isOpen,
      dockHeight,
      pendingCommand,
      openTerminal,
      closeTerminal,
      toggleTerminal,
      setDockHeight,
      clearPendingCommand,
      chdir,
    }),
    [
      effectiveEnabled,
      isMobile,
      effectiveProjectId,
      isOpen,
      dockHeight,
      pendingCommand,
      openTerminal,
      closeTerminal,
      toggleTerminal,
      setDockHeight,
      clearPendingCommand,
      chdir,
    ]
  )

  return (
    <TerminalDockContext.Provider value={value}>
      {children}
    </TerminalDockContext.Provider>
  )
}

export function useTerminalDock() {
  const context = useContext(TerminalDockContext)
  if (!context) {
    throw new Error("TerminalDockContext must be used within TerminalDockProvider")
  }
  return context
}

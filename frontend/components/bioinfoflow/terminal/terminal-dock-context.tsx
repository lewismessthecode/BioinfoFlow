"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"

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
}: {
  children: React.ReactNode
  projectId?: string
  enabled: boolean
  isMobile: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [dockHeight, setDockHeightState] = useState(DEFAULT_DOCK_HEIGHT)
  const [pendingCommand, setPendingCommand] =
    useState<TerminalDockCommand | null>(null)

  useEffect(() => {
    if (!projectId) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setIsOpen(false)
      setDockHeightState(DEFAULT_DOCK_HEIGHT)
      setPendingCommand(null)
      /* eslint-enable react-hooks/set-state-in-effect */
      return
    }
    const storedHeight = localStorage.getItem(storageKey(projectId, "height"))
    const parsedHeight = storedHeight ? Number(storedHeight) : Number.NaN
    localStorage.removeItem(storageKey(projectId, "open"))
    setIsOpen(false)
    setPendingCommand(null)
    setDockHeightState(
      Number.isFinite(parsedHeight)
        ? clampDockHeight(parsedHeight)
        : DEFAULT_DOCK_HEIGHT
    )
  }, [projectId])

  useEffect(() => {
    if (!projectId) return
    localStorage.setItem(storageKey(projectId, "height"), String(dockHeight))
  }, [dockHeight, projectId])

  useEffect(() => {
    if (!enabled) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setIsOpen(false)
      setPendingCommand(null)
      /* eslint-enable react-hooks/set-state-in-effect */
    }
  }, [enabled])

  const openTerminal = useCallback(() => {
    if (!enabled || !projectId) return
    setIsOpen(true)
  }, [enabled, projectId])

  const closeTerminal = useCallback(() => {
    setIsOpen(false)
  }, [])

  const toggleTerminal = useCallback(() => {
    if (!enabled || !projectId) return
    setIsOpen((prev) => !prev)
  }, [enabled, projectId])

  const setDockHeight = useCallback((height: number) => {
    setDockHeightState(clampDockHeight(height))
  }, [])

  const clearPendingCommand = useCallback((id: number) => {
    setPendingCommand((prev) => (prev?.id === id ? null : prev))
  }, [])

  const chdir = useCallback(
    (path: string) => {
      if (!enabled || !projectId || !isOpen) return
      setPendingCommand({
        id: Date.now(),
        projectId,
        type: "chdir",
        path,
      })
    },
    [enabled, isOpen, projectId]
  )

  const value = useMemo(
    () => ({
      enabled,
      isMobile,
      projectId,
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
      enabled,
      isMobile,
      projectId,
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

export function useOptionalTerminalDock() {
  return useContext(TerminalDockContext)
}

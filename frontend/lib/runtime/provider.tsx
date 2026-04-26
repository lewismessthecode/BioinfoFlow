"use client"

import {
  createContext,
  useContext,
  useMemo,
} from "react"

import { createLiveRuntime } from "./live-runtime"
import { getDemoRuntimeSingleton } from "./demo-runtime"
import { resolveRuntimeMode } from "./resolve-mode"
import type { AppRuntime, RuntimeMode } from "./types"

let activeRuntime: AppRuntime | null = null

function createRuntime(mode: RuntimeMode): AppRuntime {
  if (mode === "demo") {
    return getDemoRuntimeSingleton()
  }
  return createLiveRuntime()
}

const RuntimeContext = createContext<AppRuntime | null>(null)

export function setActiveRuntimeForTests(runtime: AppRuntime | null) {
  activeRuntime = runtime
}

export function getActiveRuntime(mode: RuntimeMode = "live") {
  if (!activeRuntime || activeRuntime.mode !== mode) {
    activeRuntime = createRuntime(mode)
  }
  return activeRuntime
}

export function RuntimeProvider({
  children,
  mode,
}: {
  children: React.ReactNode
  mode: RuntimeMode
}) {
  const runtime = useMemo(() => getActiveRuntime(mode), [mode])

  return (
    <RuntimeContext.Provider value={runtime}>
      {children}
    </RuntimeContext.Provider>
  )
}

export function useRuntime() {
  const runtime = useContext(RuntimeContext)
  if (!runtime) {
    throw new Error("useRuntime must be used within RuntimeProvider")
  }
  return runtime
}

export function getCurrentRuntime() {
  if (!activeRuntime) {
    activeRuntime = createRuntime(resolveRuntimeMode())
  }
  return activeRuntime
}

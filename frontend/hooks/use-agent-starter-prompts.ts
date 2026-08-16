"use client"

import { useEffect, useState } from "react"

import {
  getAgentStarterPrompts,
  type AgentStarterPromptSource,
} from "@/lib/agent/starter-prompts"

export type AgentStarterPromptState = {
  prompts: string[]
  source: AgentStarterPromptSource | null
  refreshPending: boolean
  isLoading: boolean
  error: Error | null
}

const EMPTY_STATE: AgentStarterPromptState = {
  prompts: [],
  source: null,
  refreshPending: false,
  isLoading: false,
  error: null,
}

export function useAgentStarterPrompts(
  projectId: string | null | undefined,
  locale: string,
  options?: { pollIntervalMs?: number; maxRefreshAttempts?: number },
): AgentStarterPromptState {
  const [state, setState] = useState<AgentStarterPromptState>(() => ({
    ...EMPTY_STATE,
    isLoading: Boolean(projectId),
  }))
  const pollIntervalMs = options?.pollIntervalMs ?? 1_500
  const maxRefreshAttempts = options?.maxRefreshAttempts ?? 3

  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout> | null = null
    let refreshAttempts = 0
    const controller = new AbortController()

    if (!projectId) {
      queueMicrotask(() => {
        if (active) setState(EMPTY_STATE)
      })
      return () => {
        active = false
        controller.abort()
      }
    }

    queueMicrotask(() => {
      if (active) {
        setState((current) => ({ ...current, isLoading: true, error: null }))
      }
    })

    const load = async () => {
      try {
        const result = await getAgentStarterPrompts({
          projectId,
          locale,
          signal: controller.signal,
        })
        if (!active) return
        setState({
          prompts: result.prompts,
          source: result.source,
          refreshPending: result.refresh_pending,
          isLoading: false,
          error: null,
        })
        if (
          result.refresh_pending &&
          refreshAttempts < maxRefreshAttempts
        ) {
          refreshAttempts += 1
          timer = setTimeout(() => void load(), pollIntervalMs)
        }
      } catch (caught) {
        if (!active || controller.signal.aborted) return
        setState((current) => ({
          ...current,
          refreshPending: false,
          isLoading: false,
          error:
            caught instanceof Error
              ? caught
              : new Error("Unable to load starter prompts"),
        }))
      }
    }

    void load()
    return () => {
      active = false
      controller.abort()
      if (timer !== null) clearTimeout(timer)
    }
  }, [locale, maxRefreshAttempts, pollIntervalMs, projectId])

  return state
}

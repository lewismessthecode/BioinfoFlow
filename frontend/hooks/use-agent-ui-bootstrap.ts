"use client"

import { useEffect, useState } from "react"
import { useLocale } from "next-intl"

import {
  getAgentUiBootstrap,
  normalizeAgentUiBootstrap,
  type AgentUiBootstrap,
} from "@/lib/agent/bootstrap"

export function useAgentUiBootstrap(projectId: string | null) {
  const locale = useLocale()
  const [state, setState] = useState<{
    key: string
    bootstrap: AgentUiBootstrap | null
    isLoading: boolean
  }>(() => ({ key: `${projectId ?? "workspace"}:${locale}`, bootstrap: null, isLoading: true }))
  const key = `${projectId ?? "workspace"}:${locale}`

  useEffect(() => {
    let active = true
    void getAgentUiBootstrap(projectId, locale)
      .catch(() => normalizeAgentUiBootstrap(null, locale))
      .then((bootstrap) => {
        if (active) setState({ key, bootstrap, isLoading: false })
      })
    return () => {
      active = false
    }
  }, [key, locale, projectId])

  return state.key === key
    ? state
    : { key, bootstrap: null, isLoading: true }
}

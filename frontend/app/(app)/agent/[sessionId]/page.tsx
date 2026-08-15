"use client"

import { useMemo } from "react"
import { useParams } from "next/navigation"

import { AgentPageContent } from "../page"

export default function AgentSessionPage() {
  const params = useParams<{ sessionId: string | string[] }>()
  const sessionId = useMemo(() => {
    const value = params.sessionId
    return Array.isArray(value) ? value[0] : value
  }, [params.sessionId])

  return <AgentPageContent routeSessionId={sessionId} />
}

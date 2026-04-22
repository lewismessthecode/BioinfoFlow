"use client"

import { useEffect, useState } from "react"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import type { FormSpec } from "@/lib/form-spec"

type FetchedState =
  | { status: "loading" }
  | { status: "ready"; spec: FormSpec }
  | { status: "error"; message: string }

export type FormSpecState =
  | { status: "idle" }
  | FetchedState

const IDLE: FormSpecState = { status: "idle" }

export function useFormSpec(workflowId: string | null | undefined): FormSpecState {
  const [state, setState] = useState<FetchedState | null>(null)

  useEffect(() => {
    if (!workflowId) {
      return
    }

    let cancelled = false
    const id = workflowId

    void (async () => {
      try {
        const { data } = await apiRequest<FormSpec>(`/workflows/${id}/form-spec`)
        if (!cancelled) {
          setState({ status: "ready", spec: data })
        }
      } catch (error) {
        if (!cancelled) {
          setState({
            status: "error",
            message: getApiErrorMessage(error, "Failed to load workflow form"),
          })
        }
      }
    })()

    return () => {
      cancelled = true
      setState(null)
    }
  }, [workflowId])

  if (!workflowId) return IDLE
  return state ?? { status: "loading" }
}

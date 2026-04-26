"use client"

import { useEffect, useRef, useState } from "react"
import { getCurrentRuntime } from "@/lib/runtime"

export type ConnectionState =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"

type UseEventsOptions = Parameters<
  ReturnType<typeof getCurrentRuntime>["subscribe"]
>[0]

export function useEvents({
  projectId,
  conversationId,
  runId,
  imageId,
  onRunStatus,
  onRunLog,
  onRunDag,
  onImageProgress,
  onAgentEvent,
  onOpen,
  onError,
}: UseEventsOptions) {
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("disconnected")
  const handlersRef = useRef({
    onRunStatus,
    onRunLog,
    onRunDag,
    onImageProgress,
    onAgentEvent,
    onOpen,
    onError,
  })

  useEffect(() => {
    handlersRef.current = {
      onRunStatus,
      onRunLog,
      onRunDag,
      onImageProgress,
      onAgentEvent,
      onOpen,
      onError,
    }
  }, [
    onRunStatus,
    onRunLog,
    onRunDag,
    onImageProgress,
    onAgentEvent,
    onOpen,
    onError,
  ])

  useEffect(() => {
    if (!projectId) {
      return
    }

    const runtime = getCurrentRuntime()

    const unsubscribe = runtime.subscribe({
      projectId,
      conversationId,
      runId,
      imageId,
      onRunStatus: (event) => {
        handlersRef.current.onRunStatus?.(event)
      },
      onRunLog: (event) => {
        handlersRef.current.onRunLog?.(event)
      },
      onRunDag: (event) => {
        handlersRef.current.onRunDag?.(event)
      },
      onImageProgress: (event) => {
        handlersRef.current.onImageProgress?.(event)
      },
      onAgentEvent: (event) => {
        handlersRef.current.onAgentEvent?.(event)
      },
      onOpen: () => {
        setConnectionState("connected")
        handlersRef.current.onOpen?.()
      },
      onError: (event) => {
        setConnectionState("reconnecting")
        handlersRef.current.onError?.(event)
      },
    })

    return () => {
      unsubscribe()
      setConnectionState("disconnected")
    }
  }, [
    projectId,
    conversationId,
    runId,
    imageId,
  ])

  const visibleConnectionState: ConnectionState = !projectId
    ? "disconnected"
    : connectionState === "disconnected"
      ? "connecting"
      : connectionState

  return { connectionState: visibleConnectionState }
}

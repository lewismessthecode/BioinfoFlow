"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { apiRequest, buildWebSocketUrl, getApiErrorMessage } from "@/lib/api"
import type {
  TerminalConnectionState,
  TerminalServerMessage,
  TerminalSession,
} from "@/lib/types"

type UseTerminalSessionOptions = {
  projectId?: string
  enabled: boolean
  onMessage?: (message: TerminalServerMessage) => void
}

export function useTerminalSession({
  projectId,
  enabled,
  onMessage,
}: UseTerminalSessionOptions) {
  const [session, setSession] = useState<TerminalSession | null>(null)
  const [connectionState, setConnectionState] =
    useState<TerminalConnectionState>("idle")
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)
  const socketRef = useRef<WebSocket | null>(null)
  const onMessageRef = useRef(onMessage)

  useEffect(() => {
    onMessageRef.current = onMessage
  }, [onMessage])

  const closeSocket = useCallback(() => {
    socketRef.current?.close()
    socketRef.current = null
  }, [])

  useEffect(() => {
    if (!enabled || !projectId) {
      closeSocket()
      /* eslint-disable react-hooks/set-state-in-effect */
      setSession(null)
      setError(null)
      setConnectionState("idle")
      /* eslint-enable react-hooks/set-state-in-effect */
      return
    }

    let cancelled = false
    setConnectionState("connecting")
    setError(null)

    const connect = async () => {
      try {
        const { data } = await apiRequest<TerminalSession>("/terminal/sessions", {
          method: "POST",
          body: JSON.stringify({ project_id: projectId }),
        })
        if (cancelled) return

        setSession(data)

        const socket = new WebSocket(
          buildWebSocketUrl(`/terminal/sessions/${data.id}/ws`)
        )
        socketRef.current = socket

        socket.onopen = () => {
          if (cancelled) return
          setConnectionState("connected")
        }

        socket.onmessage = (event) => {
          if (cancelled) return
          try {
            const message = JSON.parse(event.data) as TerminalServerMessage
            if (message.type === "ready") {
              setSession(message.session)
            } else if (message.type === "cwd") {
              setSession((prev) =>
                prev ? { ...prev, cwd: message.cwd } : prev
              )
            } else if (message.type === "exit") {
              setConnectionState("exited")
            } else if (message.type === "error") {
              setError(message.message)
            }
            onMessageRef.current?.(message)
          } catch {
            setError("Failed to parse terminal event")
            setConnectionState("error")
          }
        }

        socket.onerror = () => {
          if (cancelled) return
          setConnectionState("error")
          setError("Terminal connection failed")
        }

        socket.onclose = () => {
          if (cancelled) return
          setConnectionState((prev) =>
            prev === "exited" ? "exited" : "disconnected"
          )
        }
      } catch (err) {
        if (cancelled) return
        const message = getApiErrorMessage(err, "Failed to start terminal")
        setConnectionState("error")
        setError(message)
      }
    }

    connect()

    return () => {
      cancelled = true
      closeSocket()
    }
  }, [closeSocket, enabled, nonce, projectId])

  const send = useCallback((payload: Record<string, unknown>) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return false
    socketRef.current.send(JSON.stringify(payload))
    return true
  }, [])

  const sendInput = useCallback(
    (data: string) => send({ type: "input", data }),
    [send]
  )

  const resize = useCallback(
    (cols: number, rows: number) => send({ type: "resize", cols, rows }),
    [send]
  )

  const chdir = useCallback(
    (path: string) => send({ type: "chdir", path }),
    [send]
  )

  const reconnect = useCallback(() => {
    closeSocket()
    setNonce((prev) => prev + 1)
  }, [closeSocket])

  return {
    session,
    connectionState,
    error,
    sendInput,
    resize,
    chdir,
    reconnect,
  }
}

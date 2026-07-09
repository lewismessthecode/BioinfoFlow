"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslations } from "next-intl"
import { RotateCcw, Terminal as TerminalIcon } from "@/lib/icons"

import { Button } from "@/components/ui/button"
import { readTerminalTheme } from "@/lib/appearance/terminal-theme"
import { useAppearance } from "@/lib/appearance/use-appearance"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { buildWebSocketUrl } from "@/lib/api"

type AdvancedDrawerProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type TerminalModule = typeof import("@xterm/xterm")
type FitAddonModule = typeof import("@xterm/addon-fit")
type TerminalInstance = InstanceType<TerminalModule["Terminal"]>
type FitAddonInstance = InstanceType<FitAddonModule["FitAddon"]>

type ConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "disconnected"
  | "exited"
  | "unavailable"
  | "error"

const TERMINAL_FONT_FAMILY =
  '"SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", ui-monospace, monospace'

/**
 * Right-hand drawer that streams `btop -p 1` over the scheduler btop
 * WebSocket. The pty + process lifecycle lives server-side.
 */
export function AdvancedDrawer({ open, onOpenChange }: AdvancedDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-[min(820px,92vw)] flex-col gap-0 sm:max-w-none"
      >
        {/*
          Radix portals SheetContent when open=true — its DOM mounts
          AFTER this parent effect would fire. Rendering the panel as
          a conditional child means its effects run after its own
          commit, so `viewportRef.current` is populated by the time
          boot() runs.
        */}
        {open && <BtopPanel />}
      </SheetContent>
    </Sheet>
  )
}

function BtopPanel() {
  const t = useTranslations("scheduler")
  const { activePreset, resolvedMode } = useAppearance()

  const viewportRef = useRef<HTMLDivElement | null>(null)
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const terminalRef = useRef<TerminalInstance | null>(null)
  const fitAddonRef = useRef<FitAddonInstance | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const rafRef = useRef<number | null>(null)

  const [connectionState, setConnectionState] = useState<ConnectionState>("idle")
  const [unavailableDetail, setUnavailableDetail] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  const terminalTheme = useMemo(
    () => readTerminalTheme(resolvedMode, activePreset),
    [activePreset, resolvedMode],
  )

  const scheduleFit = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null
      const terminal = terminalRef.current
      const fitAddon = fitAddonRef.current
      const viewport = viewportRef.current
      const socket = socketRef.current
      if (!terminal || !fitAddon || !viewport) return
      const { width, height } = viewport.getBoundingClientRect()
      if (width <= 0 || height <= 0) return
      fitAddon.fit()
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(
          JSON.stringify({
            type: "resize",
            cols: terminal.cols,
            rows: terminal.rows,
          }),
        )
      }
    })
  }, [])

  useEffect(() => {
    let disposed = false

    const openSocket = (cols: number, rows: number) => {
      setConnectionState("connecting")
      const socket = new WebSocket(buildWebSocketUrl("/scheduler/btop/ws"))
      socketRef.current = socket

      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "resize", cols, rows }))
        setConnectionState("connected")
      }

      socket.onmessage = (event) => {
        let message:
          | {
              type?: string
              data?: string
              code?: string
              exit_code?: number
              message?: string
              attempted_paths?: string[]
            }
          | null = null
        try {
          message = JSON.parse(event.data) as typeof message
        } catch {
          return
        }
        if (!message) return
        const terminal = terminalRef.current
        if (message.type === "output" && typeof message.data === "string") {
          terminal?.write(message.data)
          return
        }
        if (message.type === "error") {
          if (message.code === "btop_unavailable") {
            const paths = message.attempted_paths?.filter(Boolean).join(", ")
            setUnavailableDetail(paths ? t("advanced.attemptedPaths", { paths }) : null)
          }
          setConnectionState(
            message.code === "btop_unavailable" ? "unavailable" : "error",
          )
          return
        }
        if (message.type === "exit") {
          terminal?.writeln(`\r\n[exit ${message.exit_code ?? 0}]`)
          setConnectionState("exited")
        }
      }

      socket.onerror = () => {
        setConnectionState((prev) =>
          prev === "unavailable" || prev === "exited" ? prev : "error",
        )
      }

      socket.onclose = () => {
        setConnectionState((prev) => {
          if (prev === "unavailable" || prev === "exited" || prev === "error") {
            return prev
          }
          return "disconnected"
        })
      }
    }

    const boot = async () => {
      const [{ Terminal }, { FitAddon }] = await Promise.all([
        import("@xterm/xterm"),
        import("@xterm/addon-fit"),
      ])
      if (disposed || !viewportRef.current) return

      const terminal = new Terminal({
        fontFamily: TERMINAL_FONT_FAMILY,
        fontSize: 13,
        lineHeight: 1.25,
        cursorBlink: false,
        scrollback: 500,
        allowProposedApi: true,
        theme: terminalTheme,
      })
      const fitAddon = new FitAddon()
      terminal.loadAddon(fitAddon)
      terminal.open(viewportRef.current)

      terminalRef.current = terminal
      fitAddonRef.current = fitAddon

      requestAnimationFrame(() => {
        if (disposed) return
        fitAddon.fit()
        openSocket(terminal.cols, terminal.rows)
      })

      terminal.onData((data) => {
        const socket = socketRef.current
        if (socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "input", data }))
        }
      })
    }

    void boot()

    return () => {
      disposed = true
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      const socket = socketRef.current
      socketRef.current = null
      if (socket && socket.readyState <= WebSocket.OPEN) {
        socket.close()
      }
      setUnavailableDetail(null)
      fitAddonRef.current = null
      terminalRef.current?.dispose()
      terminalRef.current = null
      setConnectionState("idle")
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt])

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.options.theme = terminalTheme
    }
  }, [terminalTheme])

  useEffect(() => {
    const node = bodyRef.current
    if (!node) return
    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => scheduleFit())
        : null
    observer?.observe(node)
    return () => observer?.disconnect()
  }, [scheduleFit])

  const statusLabel = statusLabelFor(connectionState, t)
  const showOverlay =
    connectionState === "unavailable" ||
    connectionState === "connecting" ||
    connectionState === "idle"

  return (
    <>
      <SheetHeader className="border-b border-divider p-4 pr-10">
        <div className="flex items-center justify-between gap-3">
          <SheetTitle>{t("advanced.drawerTitle")}</SheetTitle>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10.5px] font-medium ${statusToneFor(connectionState)}`}
            >
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full ${statusDotFor(connectionState)}`}
                aria-hidden="true"
              />
              {statusLabel}
            </span>
            {(connectionState === "disconnected" ||
              connectionState === "exited" ||
              connectionState === "unavailable" ||
              connectionState === "error") && (
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 px-2 text-[11px]"
                onClick={() => setAttempt((a) => a + 1)}
              >
                <RotateCcw className="h-3 w-3" aria-hidden="true" />
                {t("advanced.retry")}
              </Button>
            )}
          </div>
        </div>
        <SheetDescription className="font-mono text-[11px]">
          {t("advanced.drawerMeta")}
        </SheetDescription>
      </SheetHeader>
      <div
        ref={bodyRef}
        className="relative flex min-h-0 flex-1 flex-col bg-surface-subtle"
      >
        <div
          ref={viewportRef}
          className="btop-xterm-viewport min-h-0 flex-1"
          onClick={() => terminalRef.current?.focus()}
          data-testid="btop-xterm-viewport"
        />
        {showOverlay && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-surface-subtle/80 backdrop-blur-[1px]">
            <div className="flex max-w-sm flex-col items-center gap-3 px-6 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-card text-muted-foreground">
                <TerminalIcon className="h-5 w-5" aria-hidden="true" />
              </div>
              <div className="text-sm font-medium text-foreground">
                {connectionState === "unavailable"
                  ? t("advanced.unavailable")
                  : t("advanced.connecting")}
              </div>
              {connectionState === "unavailable" && (
                <div className="text-xs text-muted-foreground">
                  {t("advanced.unavailableBody")}
                  {unavailableDetail ? (
                    <span className="mt-2 block font-mono text-[10px] leading-4">
                      {unavailableDetail}
                    </span>
                  ) : null}
                </div>
              )}
            </div>
          </div>
        )}
        <style>{`
          .btop-xterm-viewport { padding: 8px 10px; }
          .btop-xterm-viewport .xterm,
          .btop-xterm-viewport .xterm-viewport {
            background: transparent !important;
          }
          .btop-xterm-viewport .xterm-viewport {
            scrollbar-width: thin;
            scrollbar-color: color-mix(in srgb, var(--muted-foreground) 30%, transparent)
              transparent;
          }
        `}</style>
      </div>
    </>
  )
}

function statusLabelFor(
  state: ConnectionState,
  t: ReturnType<typeof useTranslations>,
): string {
  switch (state) {
    case "connecting":
    case "idle":
      return t("advanced.connecting")
    case "connected":
      return t("advanced.connected")
    case "disconnected":
    case "error":
      return t("advanced.disconnected")
    case "exited":
      return t("advanced.exited")
    case "unavailable":
      return t("advanced.unavailable")
  }
}

function statusToneFor(state: ConnectionState): string {
  switch (state) {
    case "connected":
      return "border-success/30 bg-success/10 text-success"
    case "connecting":
    case "idle":
      return "border-warning/30 bg-warning/10 text-warning"
    case "unavailable":
    case "error":
      return "border-destructive/25 bg-destructive/10 text-destructive"
    case "disconnected":
    case "exited":
    default:
      return "border-border/60 bg-muted/60 text-muted-foreground"
  }
}

function statusDotFor(state: ConnectionState): string {
  switch (state) {
    case "connected":
      return "bg-success"
    case "connecting":
    case "idle":
      return "bg-warning animate-pulse motion-reduce:animate-none"
    case "unavailable":
    case "error":
      return "bg-destructive"
    default:
      return "bg-muted-foreground/60"
  }
}

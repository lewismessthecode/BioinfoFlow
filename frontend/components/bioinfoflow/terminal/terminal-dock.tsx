"use client"

import { useCallback, useEffect, useMemo, useRef } from "react"
import { Eraser, RotateCcw, TerminalSquare, X } from "lucide-react"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent } from "@/components/ui/sheet"
import { ResizeHandle } from "@/components/ui/resize-handle"
import { readTerminalTheme } from "@/lib/appearance/terminal-theme"
import { useAppearance } from "@/lib/appearance/use-appearance"
import { cn } from "@/lib/utils"
import type { TerminalServerMessage } from "@/lib/types"
import { useTerminalSession } from "@/hooks/use-terminal-session"
import { useTerminalDock } from "./terminal-dock-context"

type TerminalModule = typeof import("@xterm/xterm")
type FitAddonModule = typeof import("@xterm/addon-fit")
type TerminalInstance = InstanceType<TerminalModule["Terminal"]>
type FitAddonInstance = InstanceType<FitAddonModule["FitAddon"]>

const TERMINAL_FONT_FAMILY =
  '"SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", ui-monospace, monospace'

const CONNECTION_LABELS: Record<string, string> = {
  idle: "Idle",
  connecting: "Connecting",
  connected: "",
  disconnected: "Disconnected",
  error: "Error",
  exited: "Exited",
}

function connectionDotClassName(state: string): string {
  if (state === "connected") return "bg-success"
  if (state === "error") return "bg-destructive"
  if (state === "connecting") return "bg-warning animate-pulse"
  return "bg-muted-foreground/40"
}

function connectionBadgeClassName(state: string): string {
  if (state === "error") {
    return "border-destructive/25 bg-destructive/10 text-destructive"
  }
  if (state === "disconnected" || state === "exited") {
    return "border-border/60 bg-muted/60 text-muted-foreground"
  }
  if (state === "connecting") {
    return "border-warning/25 bg-warning/10 text-warning"
  }
  return ""
}

const getShellLabel = (shell?: string) => {
  if (!shell) return "shell"
  const parts = shell.split("/").filter(Boolean)
  return parts.at(-1) ?? shell
}

type FontStatusDocument = Document & {
  fonts?: {
    ready?: Promise<unknown>
  }
}

export function TerminalDock() {
  const {
    enabled,
    isMobile,
    projectId,
    isOpen,
    dockHeight,
    pendingCommand,
    closeTerminal,
    setDockHeight,
    clearPendingCommand,
  } = useTerminalDock()
  const tAccessibility = useTranslations("accessibility")
  const tTerminal = useTranslations("terminal")
  const { activePreset, resolvedMode } = useAppearance()
  const terminalViewportRef = useRef<HTMLDivElement | null>(null)
  const terminalBodyRef = useRef<HTMLDivElement | null>(null)
  const terminalRef = useRef<TerminalInstance | null>(null)
  const fitAddonRef = useRef<FitAddonInstance | null>(null)
  const outputBufferRef = useRef<string[]>([])
  const animationFrameRef = useRef<number | null>(null)
  const shouldConnect =
    enabled && Boolean(projectId) && (isOpen || pendingCommand !== null)

  const terminalTheme = useMemo(
    () => readTerminalTheme(resolvedMode, activePreset),
    [activePreset, resolvedMode]
  )
  const terminalThemeRef = useRef(terminalTheme)

  const handleMessage = useCallback((message: TerminalServerMessage) => {
    if (message.type === "output") {
      if (terminalRef.current) {
        terminalRef.current.write(message.data)
      } else {
        outputBufferRef.current.push(message.data)
      }
    }
    if (message.type === "error" && terminalRef.current) {
      terminalRef.current.writeln(`\r\n[error] ${message.message}`)
    }
    if (message.type === "exit" && terminalRef.current) {
      terminalRef.current.writeln(`\r\n[exit ${message.exit_code}]`)
    }
  }, [])

  const {
    session,
    connectionState,
    error,
    sendInput,
    resize,
    chdir,
    reconnect,
  } = useTerminalSession({
    projectId,
    enabled: shouldConnect,
    onMessage: handleMessage,
  })

  const scheduleFit = useCallback(() => {
    if (!isOpen) return

    if (animationFrameRef.current !== null) {
      cancelAnimationFrame(animationFrameRef.current)
    }

    animationFrameRef.current = requestAnimationFrame(() => {
      animationFrameRef.current = null

      const terminal = terminalRef.current
      const fitAddon = fitAddonRef.current
      const viewport = terminalViewportRef.current

      if (!terminal || !fitAddon || !viewport) return

      const { width, height } = viewport.getBoundingClientRect()
      if (width <= 0 || height <= 0) return

      fitAddon.fit()
      resize(terminal.cols, terminal.rows)
    })
  }, [isOpen, resize])

  useEffect(() => {
    terminalThemeRef.current = terminalTheme
    if (terminalRef.current) {
      terminalRef.current.options.theme = terminalTheme
      scheduleFit()
    }
  }, [scheduleFit, terminalTheme])

  useEffect(() => {
    if (!isOpen || !terminalViewportRef.current) return

    let disposed = false

    const waitForFonts = async () => {
      const fonts = (document as FontStatusDocument).fonts
      if (!fonts?.ready) return

      try {
        await fonts.ready
      } catch {
        // Ignore font loading failures and continue with the fallback stack.
      }
    }

    const boot = async () => {
      const [{ Terminal }, { FitAddon }] = await Promise.all([
        import("@xterm/xterm"),
        import("@xterm/addon-fit"),
      ])
      if (disposed || !terminalViewportRef.current) return

      const terminal = new Terminal({
        fontFamily: TERMINAL_FONT_FAMILY,
        fontSize: 14,
        lineHeight: 1.45,
        letterSpacing: 0,
        cursorBlink: true,
        cursorWidth: 1,
        scrollback: 2000,
        theme: terminalThemeRef.current,
      })
      const fitAddon = new FitAddon()
      terminal.loadAddon(fitAddon)
      terminal.open(terminalViewportRef.current)

      terminal.onData((data) => {
        sendInput(data)
      })

      terminalRef.current = terminal
      fitAddonRef.current = fitAddon

      await waitForFonts()
      if (disposed) return

      scheduleFit()
      terminal.focus()

      while (outputBufferRef.current.length) {
        terminal.write(outputBufferRef.current.shift() ?? "")
      }
    }

    void boot()

    return () => {
      disposed = true
      if (animationFrameRef.current !== null) {
        cancelAnimationFrame(animationFrameRef.current)
        animationFrameRef.current = null
      }
      fitAddonRef.current = null
      terminalRef.current?.dispose()
      terminalRef.current = null
    }
  }, [isOpen, scheduleFit, sendInput])

  useEffect(() => {
    if (!isOpen || !terminalBodyRef.current) return

    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => {
            scheduleFit()
          })
        : null

    observer?.observe(terminalBodyRef.current)

    const handleWindowResize = () => {
      scheduleFit()
    }

    window.addEventListener("resize", handleWindowResize)

    return () => {
      window.removeEventListener("resize", handleWindowResize)
      observer?.disconnect()
    }
  }, [isOpen, scheduleFit])

  useEffect(() => {
    if (!isOpen) return
    scheduleFit()
  }, [dockHeight, isOpen, scheduleFit])

  // Mobile Sheet animates open over ~500ms. scheduleFit fires immediately on
  // open but the viewport is still growing, so the initial fit can land on
  // a tiny size and the ResizeObserver's later ticks occasionally miss the
  // final dimensions. Schedule one final fit after the animation settles.
  useEffect(() => {
    if (!isOpen || !isMobile) return
    const timer = window.setTimeout(() => scheduleFit(), 550)
    return () => window.clearTimeout(timer)
  }, [isMobile, isOpen, scheduleFit])

  useEffect(() => {
    if (connectionState !== "connected" || !terminalRef.current) return
    scheduleFit()
  }, [connectionState, scheduleFit])

  useEffect(() => {
    if (!pendingCommand || connectionState !== "connected") return
    if (pendingCommand.type === "chdir") {
      chdir(pendingCommand.path)
      clearPendingCommand(pendingCommand.id)
    }
  }, [chdir, clearPendingCommand, connectionState, pendingCommand])

  if (!enabled || !projectId) return null

  const sessionMeta = `${getShellLabel(session?.shell)} • ${session?.cwd ?? tTerminal("startingSession")}`
  const connectionLabel = connectionState === "connected"
    ? ""
    : (CONNECTION_LABELS[connectionState] ?? connectionState)

  const header = (
    <div className="flex items-end justify-between gap-2 border-b border-border/60 bg-muted/30 dark:bg-muted/15 px-2 pt-2">
      <div className="flex min-w-0 flex-1 items-end">
        <div className="inline-flex min-w-0 max-w-full items-center gap-2 rounded-t-md border border-border/60 border-b-transparent bg-background px-3 py-1.5 -mb-px">
          <TerminalSquare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="shrink-0 text-xs font-medium text-foreground">{tTerminal("title")}</span>
          <span
            className={cn(
              "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
              connectionDotClassName(connectionState),
            )}
            aria-label={connectionLabel || "Connected"}
          />
          <span
            className="min-w-0 max-w-[280px] truncate text-[11px] text-muted-foreground"
            title={sessionMeta}
          >
            {sessionMeta}
          </span>
          {connectionLabel ? (
            <span
              className={cn(
                "inline-flex shrink-0 rounded-sm border px-1.5 py-0.5 text-[10px] font-medium",
                connectionBadgeClassName(connectionState),
              )}
            >
              {connectionLabel}
            </span>
          ) : null}
        </div>
      </div>
      <div className="flex items-center gap-0.5 pb-1.5">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 rounded-md text-muted-foreground hover:bg-muted/60 hover:text-foreground"
          onClick={() => terminalRef.current?.clear()}
          aria-label={tAccessibility("clearTerminal")}
        >
          <Eraser className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 rounded-md text-muted-foreground hover:bg-muted/60 hover:text-foreground"
          onClick={reconnect}
          aria-label={tAccessibility("reconnectTerminal")}
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 rounded-md text-muted-foreground hover:bg-muted/60 hover:text-foreground"
          onClick={closeTerminal}
          aria-label={tAccessibility("closeTerminal")}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )

  const body = (
    <div className="flex min-h-0 flex-1 flex-col bg-background">
      {error ? (
        <div className="border-b border-destructive/15 bg-destructive/4 px-4 py-2 text-xs text-destructive">
          {error}
        </div>
      ) : null}
      <div
        ref={terminalBodyRef}
        className="min-h-0 flex-1 bg-background"
        onClick={() => terminalRef.current?.focus()}
      >
        <div
          ref={terminalViewportRef}
          data-testid="terminal-dock-viewport"
          className="terminal-dock-scroll h-full min-h-0 w-full bg-background"
        />
      </div>
    </div>
  )

  if (isMobile) {
    return (
      <Sheet
        open={isOpen}
        onOpenChange={(open) => (!open ? closeTerminal() : undefined)}
      >
        <SheetContent
          side="bottom"
          className="h-[72vh] !gap-0 rounded-none p-0 [&>button.absolute]:hidden"
        >
          <div className="flex h-full min-h-0 flex-col">
            {header}
            {body}
          </div>
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <section
      className={cn(
        "relative border-t border-border/60 bg-background",
        isOpen && "animate-in slide-in-from-bottom-2 fade-in duration-200"
      )}
      style={{ height: isOpen ? dockHeight : 0 }}
      aria-hidden={!isOpen}
    >
      {isOpen ? (
        <>
          <ResizeHandle
            side="top"
            onResize={(delta) => setDockHeight(dockHeight + delta)}
          />
          <div className="flex h-full min-h-0 flex-col">
            {header}
            {body}
          </div>
        </>
      ) : null}
      <style>{`
        .terminal-dock-scroll .xterm,
        .terminal-dock-scroll .xterm-viewport {
          background: transparent !important;
        }

        .terminal-dock-scroll .xterm-viewport {
          scrollbar-width: thin;
          scrollbar-color: color-mix(in srgb, var(--muted-foreground) 30%, transparent)
            transparent;
        }

        .terminal-dock-scroll .xterm-viewport::-webkit-scrollbar {
          width: 10px;
        }

        .terminal-dock-scroll .xterm-viewport::-webkit-scrollbar-track {
          background: transparent;
        }

        .terminal-dock-scroll .xterm-viewport::-webkit-scrollbar-thumb {
          min-height: 24px;
          border: 3px solid transparent;
          border-radius: 999px;
          background: color-mix(
            in srgb,
            var(--muted-foreground) 28%,
            transparent
          );
          background-clip: padding-box;
        }

        .terminal-dock-scroll .xterm-viewport::-webkit-scrollbar-thumb:hover {
          background: color-mix(
            in srgb,
            var(--muted-foreground) 42%,
            transparent
          );
          background-clip: padding-box;
        }
      `}</style>
    </section>
  )
}

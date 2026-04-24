import * as React from "react"
import { screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { TerminalDock } from "@/components/bioinfoflow/terminal/terminal-dock"
import { TerminalDockProvider } from "@/components/bioinfoflow/terminal/terminal-dock-context"
import type { TerminalSession } from "@/lib/types"
import { renderAppPage } from "@/tests/app-test-utils"

const appearanceState = {
  resolvedMode: "light" as const,
  activePreset: "codex",
}

const resizeMock = vi.fn()
const sendInputMock = vi.fn()
const chdirMock = vi.fn()
const reconnectMock = vi.fn()

const terminalInstances: MockTerminal[] = []
const resizeObserverInstances: MockResizeObserver[] = []
let fitCallCount = 0
let disposeCallCount = 0
let focusCallCount = 0
let getBoundingClientRectMock: ReturnType<typeof vi.spyOn> | null = null

class MockResizeObserver {
  callback: ResizeObserverCallback
  observe = vi.fn()
  disconnect = vi.fn()
  unobserve = vi.fn()

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
    resizeObserverInstances.push(this)
  }

  trigger() {
    this.callback([], this as unknown as ResizeObserver)
  }
}

class MockFitAddon {
  fit() {
    fitCallCount += 1
  }
}

class MockTerminal {
  cols = 80
  rows = 24
  options: Record<string, unknown>

  constructor(options: Record<string, unknown>) {
    this.options = { ...options }
    terminalInstances.push(this)
  }

  loadAddon() {}

  open() {}

  focus() {
    focusCallCount += 1
  }

  write() {}

  writeln() {}

  clear() {}

  onData() {
    return { dispose() {} }
  }

  dispose() {
    disposeCallCount += 1
  }
}

const useTerminalSessionMock = vi.fn()

vi.mock("@/lib/appearance/use-appearance", () => ({
  useAppearance: () => ({
    mode: appearanceState.resolvedMode,
    resolvedMode: appearanceState.resolvedMode,
    lightPreset: "codex",
    darkPreset: "codex",
    activePreset: appearanceState.activePreset,
    setMode: vi.fn(),
    setLightPreset: vi.fn(),
    setDarkPreset: vi.fn(),
  }),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}))

vi.mock("@/hooks/use-terminal-session", () => ({
  useTerminalSession: (...args: unknown[]) => useTerminalSessionMock(...args),
}))

vi.mock("@xterm/xterm", () => ({
  Terminal: MockTerminal,
}))

vi.mock("@xterm/addon-fit", () => ({
  FitAddon: MockFitAddon,
}))

vi.mock("@/components/ui/resize-handle", () => ({
  ResizeHandle: () => null,
}))

function createSession(): TerminalSession {
  return {
    id: "session-1",
    project_id: "project-1",
    shell: "/bin/sh",
    cwd: "/workspace/project-1",
    status: "running",
  }
}

function renderDock() {
  return renderAppPage(
    <TerminalDockProvider projectId="project-1" enabled isMobile={false}>
      <TerminalDock />
    </TerminalDockProvider>
  )
}

describe("TerminalDock", () => {
  beforeEach(() => {
    appearanceState.resolvedMode = "light"
    appearanceState.activePreset = "codex"
    terminalInstances.length = 0
    resizeObserverInstances.length = 0
    fitCallCount = 0
    disposeCallCount = 0
    focusCallCount = 0
    resizeMock.mockReset()
    sendInputMock.mockReset()
    chdirMock.mockReset()
    reconnectMock.mockReset()
    localStorage.clear()
    localStorage.setItem("terminal-dock:project-1:open", "true")

    Object.defineProperty(document, "fonts", {
      configurable: true,
      value: { ready: Promise.resolve() },
    })
    document.documentElement.style.setProperty("--terminal-background", "#f6f7fb")
    document.documentElement.style.setProperty("--terminal-foreground", "#1e293b")
    document.documentElement.style.setProperty("--terminal-cursor", "#0f172a")
    document.documentElement.style.setProperty(
      "--terminal-selection",
      "rgba(15, 23, 42, 0.18)"
    )
    vi.stubGlobal("ResizeObserver", MockResizeObserver)
    vi.stubGlobal(
      "requestAnimationFrame",
      ((callback: FrameRequestCallback) => {
        callback(0)
        return 1
      }) as typeof requestAnimationFrame
    )
    vi.stubGlobal("cancelAnimationFrame", vi.fn())
    getBoundingClientRectMock = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockImplementation(
        () =>
          ({
            width: 960,
            height: 260,
            top: 0,
            right: 960,
            bottom: 260,
            left: 0,
            x: 0,
            y: 0,
            toJSON: () => ({}),
          }) as DOMRect
      )

    useTerminalSessionMock.mockReturnValue({
      session: createSession(),
      connectionState: "connected",
      error: null,
      sendInput: sendInputMock,
      resize: resizeMock,
      chdir: chdirMock,
      reconnect: reconnectMock,
    })
  })

  afterEach(() => {
    getBoundingClientRectMock?.mockRestore()
    getBoundingClientRectMock = null
  })

  it("updates the xterm theme without recreating the terminal instance", async () => {
    const view = renderDock()

    await waitFor(() => {
      expect(terminalInstances).toHaveLength(1)
      expect(fitCallCount).toBeGreaterThan(0)
      expect(resizeMock).toHaveBeenCalled()
    })

    const terminal = terminalInstances[0]
    expect(terminal.options.theme).toMatchObject({
      background: "#f6f7fb",
      foreground: "#1e293b",
    })
    expect(terminal.options.fontFamily).toContain("SFMono-Regular")
    expect(terminal.options.fontFamily).not.toContain("var(--font-terminal-mono)")
    expect(focusCallCount).toBeGreaterThan(0)

    appearanceState.resolvedMode = "dark"
    appearanceState.activePreset = "gruvbox"
    view.rerender(
      <TerminalDockProvider projectId="project-1" enabled isMobile={false}>
        <TerminalDock />
      </TerminalDockProvider>
    )

    await waitFor(() => {
      expect(terminal.options.theme).toMatchObject({
        background: "#f6f7fb",
        foreground: "#1e293b",
      })
    })

    expect(terminalInstances).toHaveLength(1)
    expect(disposeCallCount).toBe(0)
    expect(fitCallCount).toBeGreaterThan(0)
  })

  it("re-fits when the viewport is resized", async () => {
    renderDock()

    await waitFor(() => {
      expect(terminalInstances).toHaveLength(1)
      expect(resizeObserverInstances).toHaveLength(1)
    })

    const initialFitCount = fitCallCount
    const initialResizeCalls = resizeMock.mock.calls.length

    resizeObserverInstances[0].trigger()

    await waitFor(() => {
      expect(fitCallCount).toBeGreaterThan(initialFitCount)
      expect(resizeMock.mock.calls.length).toBeGreaterThan(initialResizeCalls)
    })
  })

  it("renders a compact single-line terminal header", async () => {
    renderDock()

    expect(await screen.findByText("title")).toBeInTheDocument()
    expect(screen.getByLabelText(/connected/i)).toBeInTheDocument()
    expect(screen.getByText("sh • /workspace/project-1")).toBeInTheDocument()
    expect(screen.queryByText("startingSession")).not.toBeInTheDocument()
  })

  it("shows inline error message without overlaying the terminal body", async () => {
    useTerminalSessionMock.mockReturnValue({
      session: createSession(),
      connectionState: "error",
      error: "Terminal connection failed",
      sendInput: sendInputMock,
      resize: resizeMock,
      chdir: chdirMock,
      reconnect: reconnectMock,
    })

    renderDock()

    const errorMessage = await screen.findByText("Terminal connection failed")
    expect(errorMessage).toBeInTheDocument()
    expect(errorMessage.className).not.toContain("absolute")
  })

  it("renders a flat terminal surface with the dock scrollbar hook", async () => {
    const view = renderDock()

    await screen.findByText("title")

    const viewport = view.container.querySelector("[data-testid='terminal-dock-viewport']")
    expect(viewport).toBeTruthy()
    expect(viewport?.className).toContain("terminal-dock-scroll")
    expect(view.container.innerHTML).not.toContain("rounded-[18px]")
  })

  it("uses a bottom slide animation for the dock container", async () => {
    const view = renderDock()

    await screen.findByText("title")

    const section = view.container.querySelector("section")
    expect(section).toBeTruthy()
    expect(section?.className).toContain("animate-in")
    expect(section?.className).toContain("slide-in-from-bottom-2")
  })
})

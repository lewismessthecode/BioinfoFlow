import * as React from "react"
import { screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { TerminalDock } from "@/components/bioinfoflow/terminal/terminal-dock"
import {
  TerminalDockProvider,
  useTerminalDock,
} from "@/components/bioinfoflow/terminal/terminal-dock-context"
import type { TerminalSession } from "@/lib/types"
import { renderAppPage } from "@/tests/app-test-utils"

const appearanceState = {
  resolvedMode: "light" as const,
  activePreset: "notion",
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
    lightPreset: "notion",
    darkPreset: "notion",
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
    target_type: "local",
    target_label: "local",
    remote_connection_id: null,
  }
}

function TerminalDockTestOpener() {
  const { openTerminal } = useTerminalDock()

  React.useEffect(() => {
    const timer = window.setTimeout(openTerminal, 0)
    return () => window.clearTimeout(timer)
  }, [openTerminal])

  return null
}

function renderDock({ open = true }: { open?: boolean } = {}) {
  return renderAppPage(
    <TerminalDockProvider projectId="project-1" enabled isMobile={false}>
      {open ? <TerminalDockTestOpener /> : null}
      <TerminalDock />
    </TerminalDockProvider>
  )
}

describe("TerminalDock", () => {
  beforeEach(() => {
    appearanceState.resolvedMode = "light"
    appearanceState.activePreset = "notion"
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

  it("does not auto-open from stored terminal state", async () => {
    localStorage.setItem("terminal-dock:project-1:open", "true")
    const view = renderDock({ open: false })

    await waitFor(() => {
      const section = view.container.querySelector("section")
      expect(section).toHaveAttribute("aria-hidden", "true")
    })
    expect(terminalInstances).toHaveLength(0)
    expect(localStorage.getItem("terminal-dock:project-1:open")).toBeNull()
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
    appearanceState.activePreset = "linear"
    document.documentElement.style.setProperty("--terminal-background", "#32302f")
    document.documentElement.style.setProperty("--terminal-foreground", "#ebdbb2")
    document.documentElement.style.setProperty("--terminal-cursor", "#ebdbb2")
    document.documentElement.style.setProperty(
      "--terminal-selection",
      "rgba(250, 189, 47, 0.35)"
    )
    view.rerender(
      <TerminalDockProvider projectId="project-1" enabled isMobile={false}>
        <TerminalDockTestOpener />
        <TerminalDock />
      </TerminalDockProvider>
    )

    await waitFor(() => {
      expect(terminal.options.theme).toMatchObject({
        background: "#32302f",
        foreground: "#ebdbb2",
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
    expect(screen.getByText("local")).toBeInTheDocument()
    expect(screen.queryByText("sh • /workspace/project-1")).not.toBeInTheDocument()
    expect(screen.getByTitle("local • sh • /workspace/project-1")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "newTerminal" })).toHaveAttribute(
      "aria-disabled",
      "true"
    )
    expect(screen.queryByRole("button", { name: "clearTerminal" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "reconnectTerminal" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "closeTerminal" })).toBeInTheDocument()
    expect(screen.queryByText("startingSession")).not.toBeInTheDocument()
    const terminalTab = screen.getByTitle("local • sh • /workspace/project-1")
    const tabStrip = screen.getByTestId("terminal-dock-tab-strip")
    expect(tabStrip.className).toContain("items-end")
    expect(terminalTab).toHaveAttribute("data-testid", "terminal-dock-tab")
    expect(terminalTab.className).toContain("rounded-t-md")
    expect(terminalTab.className).toContain("border")
    expect(terminalTab.className).toContain("bg-background")
  })

  it("labels remote terminal targets with the node name", async () => {
    useTerminalSessionMock.mockReturnValue({
      session: {
        ...createSession(),
        target_type: "remote",
        target_label: "remote · Phoenix login",
        remote_connection_id: "connection-1",
        cwd: "/data/phoenix",
        status: "running",
      },
      connectionState: "connected",
      error: null,
      sendInput: sendInputMock,
      resize: resizeMock,
      chdir: chdirMock,
      reconnect: reconnectMock,
    })

    renderDock()

    expect(await screen.findByText("remote · Phoenix login")).toBeInTheDocument()
    expect(screen.getByTitle("remote · Phoenix login • sh • /data/phoenix")).toBeInTheDocument()
    expect(
      screen.queryByText("Remote interactive terminals are not supported yet.")
    ).not.toBeInTheDocument()
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
    const body = viewport?.parentElement
    expect(viewport).toBeTruthy()
    expect(viewport?.className).toContain("terminal-dock-scroll")
    expect(viewport?.className).toContain("bg-transparent")
    expect(body?.className).toContain("px-5")
    expect(body?.className).toContain("pt-4")
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

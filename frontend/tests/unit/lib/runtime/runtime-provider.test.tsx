import { screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { renderWithProviders } from "@/tests/test-utils"
import {
  RuntimeProvider,
  resolveRuntimeMode,
  setActiveRuntimeForTests,
  useRuntime,
} from "@/lib/runtime"

function RuntimeProbe() {
  const runtime = useRuntime()

  return (
    <div>
      <div data-testid="mode">{runtime.mode}</div>
      <div data-testid="auth">{String(runtime.capabilities.auth)}</div>
      <div data-testid="terminal">{String(runtime.capabilities.terminal)}</div>
      <div data-testid="destructive">
        {String(runtime.capabilities.destructiveActions)}
      </div>
    </div>
  )
}

describe("runtime mode resolution", () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    setActiveRuntimeForTests(null)
  })

  it("defaults to live mode when no runtime env is set", () => {
    expect(resolveRuntimeMode()).toBe("live")
  })

  it("prefers APP_RUNTIME when it is set", () => {
    vi.stubEnv("APP_RUNTIME", "demo")

    expect(resolveRuntimeMode()).toBe("demo")
  })

  it("falls back to demo when DEPLOY_MODE is demo", () => {
    vi.stubEnv("DEPLOY_MODE", "demo")

    expect(resolveRuntimeMode()).toBe("demo")
  })

  it("falls back to demo when NEXT_PUBLIC_DEPLOY_MODE is demo", () => {
    vi.stubEnv("NEXT_PUBLIC_DEPLOY_MODE", "demo")

    expect(resolveRuntimeMode()).toBe("demo")
  })
})

describe("RuntimeProvider", () => {
  afterEach(() => {
    setActiveRuntimeForTests(null)
  })

  it("exposes demo capabilities to the app tree", () => {
    renderWithProviders(
      <RuntimeProvider mode="demo">
        <RuntimeProbe />
      </RuntimeProvider>,
    )

    expect(screen.getByTestId("mode")).toHaveTextContent("demo")
    expect(screen.getByTestId("auth")).toHaveTextContent("false")
    expect(screen.getByTestId("terminal")).toHaveTextContent("false")
    expect(screen.getByTestId("destructive")).toHaveTextContent("false")
  })
})

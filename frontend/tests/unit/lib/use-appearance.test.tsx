import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const themeState = {
  theme: "system",
  resolvedTheme: "light",
}

const setThemeMock = vi.fn()
const matchMediaListeners = new Set<(event: MediaQueryListEvent) => void>()
let prefersDarkScheme = false

vi.mock("next-themes", () => ({
  useTheme: () => ({
    theme: themeState.theme,
    resolvedTheme: themeState.resolvedTheme,
    setTheme: setThemeMock,
  }),
}))

import {
  AppearanceProvider,
  APPEARANCE_STORAGE_KEY,
  useAppearance,
} from "@/lib/appearance/provider"

function Wrapper({ children }: { children: React.ReactNode }) {
  return <AppearanceProvider>{children}</AppearanceProvider>
}

function dispatchSystemColorScheme(mode: "light" | "dark") {
  prefersDarkScheme = mode === "dark"

  const event = {
    matches: prefersDarkScheme,
    media: "(prefers-color-scheme: dark)",
  } as MediaQueryListEvent

  for (const listener of matchMediaListeners) {
    listener(event)
  }
}

describe("useAppearance", () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute("data-appearance-mode")
    document.documentElement.removeAttribute("data-appearance-preset")
    document.documentElement.style.cssText = ""
    document.head.innerHTML = '<meta name="theme-color" content="#ffffff">'
    themeState.theme = "system"
    themeState.resolvedTheme = "light"
    prefersDarkScheme = false
    matchMediaListeners.clear()
    setThemeMock.mockReset()
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: prefersDarkScheme,
      media: "(prefers-color-scheme: dark)",
      onchange: null,
      addEventListener: (_event: string, listener: (event: MediaQueryListEvent) => void) => {
        matchMediaListeners.add(listener)
      },
      removeEventListener: (_event: string, listener: (event: MediaQueryListEvent) => void) => {
        matchMediaListeners.delete(listener)
      },
      addListener: (listener: (event: MediaQueryListEvent) => void) => {
        matchMediaListeners.add(listener)
      },
      removeListener: (listener: (event: MediaQueryListEvent) => void) => {
        matchMediaListeners.delete(listener)
      },
      dispatchEvent: vi.fn(),
    })))
  })

  it("falls back to codex presets when no saved config exists", async () => {
    const { result } = renderHook(() => useAppearance(), { wrapper: Wrapper })

    await waitFor(() => {
      expect(result.current.lightPreset).toBe("codex")
    })

    expect(result.current.darkPreset).toBe("codex")
    expect(result.current.activePreset).toBe("codex")
    expect(result.current.mode).toBe("system")
    expect(result.current.resolvedMode).toBe("light")
    expect(document.documentElement.dataset.appearanceMode).toBe("light")
    expect(document.documentElement.dataset.appearancePreset).toBe("codex")
  })

  it("ignores corrupt or unknown local storage and restores codex defaults", async () => {
    localStorage.setItem(
      APPEARANCE_STORAGE_KEY,
      JSON.stringify({
        lightPreset: "unknown",
        darkPreset: "broken",
      }),
    )

    const { result, unmount } = renderHook(() => useAppearance(), {
      wrapper: Wrapper,
    })

    await waitFor(() => {
      expect(result.current.lightPreset).toBe("codex")
    })

    unmount()
    localStorage.setItem(APPEARANCE_STORAGE_KEY, "{bad-json")

    const { result: nextResult } = renderHook(() => useAppearance(), {
      wrapper: Wrapper,
    })

    await waitFor(() => {
      expect(nextResult.current.darkPreset).toBe("codex")
    })
  })

  it("persists preset changes and delegates mode updates to next-themes", async () => {
    const { result } = renderHook(() => useAppearance(), { wrapper: Wrapper })

    await waitFor(() => {
      expect(result.current.lightPreset).toBe("codex")
    })

    act(() => {
      result.current.setLightPreset("github")
      result.current.setDarkPreset("gruvbox")
      result.current.setMode("dark")
    })

    expect(localStorage.getItem(APPEARANCE_STORAGE_KEY)).toBe(
      JSON.stringify({
        lightPreset: "github",
        darkPreset: "gruvbox",
      }),
    )
    expect(setThemeMock).toHaveBeenCalledWith("dark")
  })

  it("follows live system color-scheme changes while mode is system", async () => {
    const { result } = renderHook(() => useAppearance(), { wrapper: Wrapper })

    await waitFor(() => {
      expect(result.current.resolvedMode).toBe("light")
    })

    act(() => {
      dispatchSystemColorScheme("dark")
    })

    await waitFor(() => {
      expect(result.current.resolvedMode).toBe("dark")
    })

    expect(result.current.mode).toBe("system")
    expect(document.documentElement.dataset.appearanceMode).toBe("dark")
    expect(document.documentElement.dataset.appearancePreset).toBe("codex")
    expect(
      document.querySelector('meta[name="theme-color"]')?.getAttribute("content"),
    ).toBe("#09090b")
  })
})

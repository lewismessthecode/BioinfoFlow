"use client"

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { useTheme } from "next-themes"

import {
  APPEARANCE_TOKEN_KEYS,
  appearancePresetIds,
  appearancePresets,
  type ThemePresetId,
} from "@/lib/appearance/presets"

export type AppearanceMode = "light" | "dark" | "system"
export type ResolvedAppearanceMode = "light" | "dark"
export type AppearanceConfig = {
  lightPreset: ThemePresetId
  darkPreset: ThemePresetId
}

type AppearanceContextValue = {
  mode: AppearanceMode
  resolvedMode: ResolvedAppearanceMode
  lightPreset: ThemePresetId
  darkPreset: ThemePresetId
  activePreset: ThemePresetId
  setMode: (mode: AppearanceMode) => void
  setLightPreset: (preset: ThemePresetId) => void
  setDarkPreset: (preset: ThemePresetId) => void
}

const DEFAULT_APPEARANCE_CONFIG: AppearanceConfig = {
  lightPreset: "notion",
  darkPreset: "notion",
}
const LEGACY_PRESET_ALIASES: Partial<Record<string, ThemePresetId>> = {
  codex: "notion",
  workbench: "notion",
}
const SYSTEM_COLOR_SCHEME_QUERY = "(prefers-color-scheme: dark)"

const AppearanceContext = createContext<AppearanceContextValue | null>(null)

export const APPEARANCE_STORAGE_KEY = "bioinfoflow:appearance"

function isThemePresetId(value: string): value is ThemePresetId {
  return appearancePresetIds.includes(value as ThemePresetId)
}

function normalizePresetId(value: string | undefined, fallback: ThemePresetId): ThemePresetId {
  if (!value) return fallback
  if (isThemePresetId(value)) return value
  return LEGACY_PRESET_ALIASES[value] ?? fallback
}

function sanitizeConfig(value: unknown): AppearanceConfig {
  if (!value || typeof value !== "object") {
    return DEFAULT_APPEARANCE_CONFIG
  }

  const config = value as Partial<Record<keyof AppearanceConfig, string>>

  return {
    lightPreset: normalizePresetId(
      config.lightPreset,
      DEFAULT_APPEARANCE_CONFIG.lightPreset,
    ),
    darkPreset: normalizePresetId(
      config.darkPreset,
      DEFAULT_APPEARANCE_CONFIG.darkPreset,
    ),
  }
}

function readStoredConfig(): AppearanceConfig {
  if (typeof window === "undefined") {
    return DEFAULT_APPEARANCE_CONFIG
  }

  const raw = window.localStorage.getItem(APPEARANCE_STORAGE_KEY)
  if (!raw) {
    return DEFAULT_APPEARANCE_CONFIG
  }

  try {
    return sanitizeConfig(JSON.parse(raw))
  } catch {
    return DEFAULT_APPEARANCE_CONFIG
  }
}

function getSystemResolvedMode(): ResolvedAppearanceMode {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "light"
  }

  return window.matchMedia(SYSTEM_COLOR_SCHEME_QUERY).matches ? "dark" : "light"
}

export function getNextAppearanceMode(
  mode: AppearanceMode,
  resolvedMode: ResolvedAppearanceMode,
): Exclude<AppearanceMode, "system"> {
  const current = mode === "system" ? resolvedMode : mode
  return current === "dark" ? "light" : "dark"
}

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const { theme, resolvedTheme, setTheme } = useTheme()
  const [config, setConfig] = useState<AppearanceConfig>(() => readStoredConfig())
  const [systemResolvedMode, setSystemResolvedMode] = useState<ResolvedAppearanceMode>(() =>
    getSystemResolvedMode(),
  )

  const mode: AppearanceMode =
    theme === "light" || theme === "dark" || theme === "system"
      ? theme
      : "system"
  const explicitResolvedMode: ResolvedAppearanceMode =
    theme === "dark" || (theme !== "light" && resolvedTheme === "dark")
      ? "dark"
      : "light"
  const resolvedMode: ResolvedAppearanceMode =
    mode === "system" ? systemResolvedMode : explicitResolvedMode
  const activePreset =
    resolvedMode === "dark" ? config.darkPreset : config.lightPreset

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return
    }

    const mediaQuery = window.matchMedia(SYSTEM_COLOR_SCHEME_QUERY)
    const syncResolvedMode = (matches: boolean) => {
      setSystemResolvedMode(matches ? "dark" : "light")
    }
    const handleChange = (event: MediaQueryListEvent) => {
      syncResolvedMode(event.matches)
    }

    syncResolvedMode(mediaQuery.matches)

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", handleChange)
      return () => mediaQuery.removeEventListener("change", handleChange)
    }

    mediaQuery.addListener(handleChange)
    return () => mediaQuery.removeListener(handleChange)
  }, [])

  useEffect(() => {
    window.localStorage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(config))
  }, [config])

  useEffect(() => {
    const root = document.documentElement
    const tokens = appearancePresets[activePreset][resolvedMode]

    for (const key of APPEARANCE_TOKEN_KEYS) {
      root.style.setProperty(`--${key}`, tokens[key])
    }

    root.dataset.appearanceMode = resolvedMode
    root.dataset.appearancePreset = activePreset
    root.style.colorScheme = resolvedMode

    const themeColor =
      document.querySelector<HTMLMetaElement>('meta[name="theme-color"]') ??
      (() => {
        const meta = document.createElement("meta")
        meta.name = "theme-color"
        document.head.appendChild(meta)
        return meta
      })()

    themeColor.content = tokens.background
  }, [activePreset, resolvedMode])

  const value = useMemo<AppearanceContextValue>(
    () => ({
      mode,
      resolvedMode,
      lightPreset: config.lightPreset,
      darkPreset: config.darkPreset,
      activePreset,
      setMode: (nextMode) => setTheme(nextMode),
      setLightPreset: (preset) =>
        setConfig((current) => ({ ...current, lightPreset: preset })),
      setDarkPreset: (preset) =>
        setConfig((current) => ({ ...current, darkPreset: preset })),
    }),
    [activePreset, config.darkPreset, config.lightPreset, mode, resolvedMode, setTheme],
  )

  return (
    <AppearanceContext.Provider value={value}>
      {children}
    </AppearanceContext.Provider>
  )
}

export function useAppearance() {
  const context = useContext(AppearanceContext)
  if (!context) {
    throw new Error("useAppearance must be used within an AppearanceProvider")
  }
  return context
}

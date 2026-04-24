"use client"

import type { ResolvedAppearanceMode } from "@/lib/appearance/provider"

export type TerminalTheme = {
  background: string
  foreground: string
  cursor: string
  selectionBackground: string
}

const FALLBACK_TERMINAL_THEME: Record<ResolvedAppearanceMode, TerminalTheme> = {
  light: {
    background: "#ffffff",
    foreground: "#111827",
    cursor: "#111827",
    selectionBackground: "rgba(17, 24, 39, 0.12)",
  },
  dark: {
    background: "#0f1115",
    foreground: "#e5e7eb",
    cursor: "#f8fafc",
    selectionBackground: "rgba(148, 163, 184, 0.35)",
  },
}

function readCssVar(name: string): string {
  if (typeof window === "undefined") {
    return ""
  }

  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim()
}

export function readTerminalTheme(
  resolvedMode: ResolvedAppearanceMode,
  preset?: string,
): TerminalTheme {
  void preset
  const fallback = FALLBACK_TERMINAL_THEME[resolvedMode]

  return {
    background: readCssVar("--terminal-background") || fallback.background,
    foreground: readCssVar("--terminal-foreground") || fallback.foreground,
    cursor: readCssVar("--terminal-cursor") || fallback.cursor,
    selectionBackground:
      readCssVar("--terminal-selection") || fallback.selectionBackground,
  }
}

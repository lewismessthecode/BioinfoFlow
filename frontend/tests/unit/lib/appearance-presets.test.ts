import { describe, expect, it } from "vitest"

import {
  APPEARANCE_TOKEN_KEYS,
  appearancePresetIds,
  appearancePresets,
} from "@/lib/appearance/presets"

describe("appearance preset registry", () => {
  it("registers all supported preset ids", () => {
    expect(appearancePresetIds).toEqual([
      "codex",
      "linear",
      "github",
      "notion",
      "catppuccin",
      "everforest",
      "gruvbox",
      "one",
      "proof",
      "raycast",
      "dracula",
      "ayu",
      "material",
      "matrix",
      "monokai",
      "rose-pine",
      "solarized",
      "tokyo-night",
      "vercel",
      "vscode-plus",
    ])
  })

  it("provides both light and dark token sets for every preset", () => {
    for (const presetId of appearancePresetIds) {
      const preset = appearancePresets[presetId]

      expect(preset).toBeDefined()
      expect(preset.label).toBeTruthy()

      for (const mode of ["light", "dark"] as const) {
        for (const key of APPEARANCE_TOKEN_KEYS) {
          expect(preset[mode][key], `${presetId}.${mode}.${key}`).toBeTruthy()
        }
      }
    }
  })

  it("keeps the classic palette anchors for the curated presets", () => {
    expect(appearancePresets.codex.light).toMatchObject({
      background: "#fdfdff",
      sidebar: "#f8f8fa",
      "sidebar-accent": "#eeeeef",
    })

    expect(appearancePresets.ayu.light).toMatchObject({
      background: "#fcfcfc",
      primary: "#ff9940",
    })
    expect(appearancePresets.ayu.dark).toMatchObject({
      background: "#1f2430",
      primary: "#ffcc66",
    })

    expect(appearancePresets.material.light).toMatchObject({
      background: "#fafafa",
    })
    expect(appearancePresets.material.dark).toMatchObject({
      background: "#0f111a",
      primary: "#82aaff",
    })

    expect(appearancePresets["rose-pine"].light).toMatchObject({
      background: "#faf4ed",
      "bg-surface": "#f2e9e1",
    })
    expect(appearancePresets["rose-pine"].dark).toMatchObject({
      background: "#191724",
      "bg-surface": "#26233a",
    })

    expect(appearancePresets.solarized.light).toMatchObject({
      background: "#fdf6e3",
      "bg-surface": "#eee8d5",
    })
    expect(appearancePresets.solarized.dark).toMatchObject({
      background: "#002b36",
      "bg-surface": "#073642",
    })

    expect(appearancePresets["tokyo-night"].light).toMatchObject({
      background: "#e6e7ed",
      sidebar: "#d6d8df",
    })
    expect(appearancePresets["tokyo-night"].dark).toMatchObject({
      background: "#1a1b26",
      sidebar: "#16161e",
    })

    expect(appearancePresets["vscode-plus"].light).toMatchObject({
      background: "#ffffff",
      sidebar: "#f3f3f3",
    })
    expect(appearancePresets["vscode-plus"].dark).toMatchObject({
      background: "#1e1e1e",
      "bg-surface": "#252526",
    })
  })
})

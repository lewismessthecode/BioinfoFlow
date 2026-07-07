import { describe, expect, it } from "vitest"

import {
  APPEARANCE_TOKEN_KEYS,
  appearancePresetIds,
  appearancePresets,
} from "@/lib/appearance/presets"

describe("appearance preset registry", () => {
  it("registers all supported preset ids", () => {
    expect(appearancePresetIds).toEqual([
      "workbench",
      "notion",
      "github",
      "linear",
      "one",
      "vercel",
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

  it("keeps the curated palette anchors", () => {
    expect(appearancePresets.workbench.label).toBe("Workbench")
    expect(appearancePresets.workbench.light).toMatchObject({
      background: "#fbfaf7",
      foreground: "#201f1b",
      primary: "#201f1b",
      sidebar: "#f2f0eb",
      "sidebar-accent": "#e7e2da",
      "bg-surface": "#f4f1eb",
    })
    expect(appearancePresets.workbench.dark).toMatchObject({
      background: "#0d0c0a",
      foreground: "#f2eee8",
      primary: "#f2eee8",
      sidebar: "#0b0a08",
      "bg-surface": "#181613",
    })
  })
})

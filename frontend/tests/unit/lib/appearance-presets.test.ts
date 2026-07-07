import { describe, expect, it } from "vitest"

import {
  APPEARANCE_TOKEN_KEYS,
  appearancePresetIds,
  appearancePresets,
} from "@/lib/appearance/presets"

describe("appearance preset registry", () => {
  it("registers all supported preset ids", () => {
    expect(appearancePresetIds).toEqual([
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

  it("keeps the Notion palette anchors", () => {
    expect(appearancePresets.notion.label).toBe("Notion")
    expect(appearancePresets.notion.light).toMatchObject({
      background: "#ffffff",
      foreground: "#191919",
      primary: "#191919",
      sidebar: "#fbfbfa",
      "sidebar-accent": "#f1f1ef",
      "bg-surface": "#f7f7f5",
    })
    expect(appearancePresets.notion.dark).toMatchObject({
      background: "#191919",
      foreground: "#f1f1ef",
      primary: "#f1f1ef",
      sidebar: "#181818",
      "bg-surface": "#242424",
    })
    expect(appearancePresets).not.toHaveProperty("workbench")
  })
})

import { describe, expect, it } from "vitest"
import {
  PIXEL_PERSONAS,
  findPixelPersona,
  getPixelPersonaCandidates,
  parsePixelPersonaReference,
  resolveDefaultPixelPersona,
  toPixelPersonaReference,
} from "@/lib/avatar/pixel-personas"

describe("pixel personas", () => {
  it("ships a reviewed catalog of twenty valid pixel portraits", () => {
    expect(PIXEL_PERSONAS).toHaveLength(20)
    expect(new Set(PIXEL_PERSONAS.map((persona) => persona.key)).size).toBe(20)

    for (const persona of PIXEL_PERSONAS) {
      expect(persona.key).toMatch(/^pixel-persona-\d{2}$/)
      expect(persona.pixels).toHaveLength(12)
      expect(persona.pixels.every((row) => row.length === 12)).toBe(true)
      expect(persona.palette["."]).toBe(persona.background)
      expect(findPixelPersona(persona.key)).toBe(persona)
    }
  })

  it("maps the same viewer id to the same default portrait", () => {
    const first = resolveDefaultPixelPersona("viewer-1")
    const second = resolveDefaultPixelPersona("viewer-1")

    expect(first).toBe(second)
    expect(first.key).toMatch(/^pixel-persona-/)
  })

  it("uses different viewer ids across the catalog", () => {
    const keys = new Set(
      Array.from({ length: 40 }, (_, index) =>
        resolveDefaultPixelPersona(`viewer-${index}`).key,
      ),
    )

    expect(keys.size).toBeGreaterThan(10)
  })

  it("round-trips reserved built-in avatar references", () => {
    const reference = toPixelPersonaReference("pixel-persona-03")

    expect(reference).toBe("bioinfoflow-avatar:pixel-persona-03")
    expect(parsePixelPersonaReference(reference)).toBe("pixel-persona-03")
    expect(parsePixelPersonaReference("https://example.com/avatar.webp")).toBeNull()
    expect(parsePixelPersonaReference("bioinfoflow-avatar:pixel-persona-99")).toBeNull()
  })

  it("returns stable non-overlapping candidate pages before wrapping", () => {
    const first = getPixelPersonaCandidates("viewer-1", 0, 6)
    const second = getPixelPersonaCandidates("viewer-1", 1, 6)

    expect(first).toHaveLength(6)
    expect(second).toHaveLength(6)
    expect(first.map((persona) => persona.key)).not.toEqual(
      second.map((persona) => persona.key),
    )
    expect(
      first.filter((persona) => second.some((candidate) => candidate.key === persona.key)),
    ).toHaveLength(0)
  })
})

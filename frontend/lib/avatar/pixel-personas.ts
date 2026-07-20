export type PixelPersonaKey = `pixel-persona-${string}`

export type PixelPersona = {
  key: PixelPersonaKey
  background: string
  palette: Readonly<Record<string, string>>
  pixels: readonly string[]
}

const PIXEL_PERSONA_REFERENCE_PREFIX = "bioinfoflow-avatar:"

type HairStyle = "crop" | "wave" | "bob" | "curls" | "sweep" | "silver"
type Expression = "neutral" | "smile" | "soft"
type Accessory = "square-glasses" | "round-glasses" | "lab-cap" | "headset"

type PersonaSpec = {
  background: string
  skin: string
  hair: string
  outfit: string
  eye: string
  mouth: string
  hairStyle: HairStyle
  expression: Expression
  accessory?: Accessory
  accessoryColor?: string
}

function fill(
  grid: string[][],
  x: number,
  y: number,
  width: number,
  height: number,
  value: string,
) {
  for (let row = y; row < y + height; row += 1) {
    for (let column = x; column < x + width; column += 1) {
      if (grid[row]?.[column] != null) {
        grid[row][column] = value
      }
    }
  }
}

function drawHair(grid: string[][], style: HairStyle) {
  if (style === "crop") {
    fill(grid, 2, 1, 8, 3, "h")
    fill(grid, 1, 3, 2, 4, "h")
    fill(grid, 9, 3, 2, 4, "h")
    return
  }

  if (style === "wave") {
    fill(grid, 1, 1, 10, 3, "h")
    fill(grid, 1, 3, 2, 6, "h")
    fill(grid, 9, 2, 2, 7, "h")
    grid[0][4] = "h"
    grid[0][5] = "h"
    grid[0][8] = "h"
    return
  }

  if (style === "bob") {
    fill(grid, 1, 1, 10, 3, "h")
    fill(grid, 1, 3, 2, 7, "h")
    fill(grid, 9, 3, 2, 7, "h")
    return
  }

  if (style === "curls") {
    fill(grid, 2, 1, 8, 3, "h")
    for (const [x, y] of [[1, 2], [1, 4], [1, 6], [9, 0], [10, 2], [10, 4], [10, 6]]) {
      fill(grid, x, y, 2, 2, "h")
    }
    return
  }

  if (style === "sweep") {
    fill(grid, 2, 1, 8, 2, "h")
    fill(grid, 1, 2, 5, 3, "h")
    fill(grid, 1, 4, 2, 4, "h")
    fill(grid, 9, 2, 2, 5, "h")
    grid[0][7] = "h"
    grid[0][8] = "h"
    return
  }

  fill(grid, 2, 1, 8, 2, "h")
  fill(grid, 1, 2, 2, 5, "h")
  fill(grid, 9, 2, 2, 5, "h")
  grid[0][3] = "h"
  grid[0][5] = "h"
  grid[0][7] = "h"
  grid[0][9] = "h"
}

function drawAccessory(grid: string[][], accessory?: Accessory) {
  if (accessory === "square-glasses") {
    fill(grid, 3, 5, 3, 2, "g")
    fill(grid, 7, 5, 3, 2, "g")
    grid[5][6] = "g"
    grid[6][6] = "g"
    grid[6][4] = "e"
    grid[6][8] = "e"
    return
  }

  if (accessory === "round-glasses") {
    for (const [x, y] of [[3, 5], [4, 4], [5, 5], [4, 6], [7, 5], [8, 4], [9, 5], [8, 6], [6, 5]]) {
      grid[y][x] = "g"
    }
    grid[5][4] = "e"
    grid[5][8] = "e"
    return
  }

  if (accessory === "lab-cap") {
    fill(grid, 2, 0, 8, 2, "a")
    fill(grid, 1, 1, 10, 2, "a")
    return
  }

  if (accessory === "headset") {
    fill(grid, 0, 4, 2, 4, "a")
    fill(grid, 10, 4, 2, 4, "a")
    fill(grid, 1, 2, 1, 2, "a")
    fill(grid, 10, 2, 1, 2, "a")
    fill(grid, 9, 8, 2, 1, "a")
    grid[9][8] = "a"
  }
}

function buildPixels(spec: PersonaSpec): readonly string[] {
  const grid = Array.from({ length: 12 }, () => Array.from({ length: 12 }, () => "."))

  fill(grid, 1, 10, 10, 2, "c")
  fill(grid, 2, 2, 8, 8, "s")
  fill(grid, 1, 4, 1, 4, "s")
  fill(grid, 10, 4, 1, 4, "s")
  drawHair(grid, spec.hairStyle)

  grid[5][4] = "e"
  grid[5][7] = "e"

  if (spec.expression === "smile") {
    grid[7][4] = "m"
    grid[8][5] = "m"
    grid[8][6] = "m"
    grid[7][7] = "m"
  } else if (spec.expression === "soft") {
    grid[8][5] = "m"
    grid[8][6] = "m"
    grid[7][7] = "m"
  } else {
    grid[8][5] = "m"
    grid[8][6] = "m"
  }

  drawAccessory(grid, spec.accessory)
  return grid.map((row) => row.join(""))
}

function persona(index: number, spec: PersonaSpec): PixelPersona {
  const key = `pixel-persona-${String(index).padStart(2, "0")}` as PixelPersonaKey
  return {
    key,
    background: spec.background,
    palette: {
      ".": spec.background,
      s: spec.skin,
      h: spec.hair,
      c: spec.outfit,
      e: spec.eye,
      m: spec.mouth,
      g: spec.accessoryColor ?? spec.eye,
      a: spec.accessoryColor ?? spec.outfit,
    },
    pixels: buildPixels(spec),
  }
}

export const PIXEL_PERSONAS: readonly PixelPersona[] = [
  persona(1, { background: "#dceee7", skin: "#efb58f", hair: "#233a55", outfit: "#447b71", eye: "#25323a", mouth: "#b85f58", hairStyle: "crop", expression: "neutral" }),
  persona(2, { background: "#ebe3f5", skin: "#8f5b44", hair: "#1d2028", outfit: "#6c59a0", eye: "#23242b", mouth: "#e6a17e", hairStyle: "curls", expression: "soft" }),
  persona(3, { background: "#f3e8cc", skin: "#efc5a6", hair: "#a64d42", outfit: "#c49437", eye: "#273238", mouth: "#b9605b", hairStyle: "bob", expression: "smile" }),
  persona(4, { background: "#dcebf3", skin: "#c9825e", hair: "#e7e3da", outfit: "#3e7898", eye: "#29475c", mouth: "#71403b", hairStyle: "silver", expression: "neutral" }),
  persona(5, { background: "#e5efd8", skin: "#d99b72", hair: "#40352e", outfit: "#6d914b", eye: "#26312c", mouth: "#8e4e4a", hairStyle: "sweep", expression: "soft" }),
  persona(6, { background: "#f0dfd6", skin: "#6f4336", hair: "#181a20", outfit: "#a8584c", eye: "#1f2025", mouth: "#d98f72", hairStyle: "bob", expression: "smile" }),
  persona(7, { background: "#dde4f2", skin: "#e2aa82", hair: "#5b3b2f", outfit: "#546c9d", eye: "#243247", mouth: "#a95855", hairStyle: "wave", expression: "neutral" }),
  persona(8, { background: "#e6e1d7", skin: "#9e674f", hair: "#d6cec0", outfit: "#755e4f", eye: "#342d2a", mouth: "#e1a17f", hairStyle: "silver", expression: "soft" }),
  persona(9, { background: "#d9ece9", skin: "#efb992", hair: "#754937", outfit: "#2f7f82", eye: "#21363a", mouth: "#b15d57", hairStyle: "curls", expression: "smile" }),
  persona(10, { background: "#eee2ef", skin: "#70483b", hair: "#2c2531", outfit: "#8b5e8f", eye: "#241f27", mouth: "#d99378", hairStyle: "crop", expression: "neutral" }),
  persona(11, { background: "#f3e8d8", skin: "#d58f68", hair: "#2f343c", outfit: "#c47d45", eye: "#21262e", mouth: "#924a46", hairStyle: "sweep", expression: "soft" }),
  persona(12, { background: "#dfe9dc", skin: "#b56e50", hair: "#18282d", outfit: "#557663", eye: "#18262a", mouth: "#e09a79", hairStyle: "wave", expression: "smile" }),
  persona(13, { background: "#e1e8f3", skin: "#efc0a0", hair: "#c9a780", outfit: "#597aa5", eye: "#26394f", mouth: "#b45e5b", hairStyle: "bob", expression: "neutral" }),
  persona(14, { background: "#e9e0d3", skin: "#80503e", hair: "#17191e", outfit: "#997342", eye: "#202126", mouth: "#d88f74", hairStyle: "curls", expression: "soft" }),
  persona(15, { background: "#dcece2", skin: "#db956e", hair: "#4b3029", outfit: "#4c8470", eye: "#26352f", mouth: "#924b48", hairStyle: "crop", expression: "smile" }),
  persona(16, { background: "#eee2e6", skin: "#aa684d", hair: "#ede8dc", outfit: "#9b586f", eye: "#3b2c33", mouth: "#e2a080", hairStyle: "silver", expression: "neutral" }),
  persona(17, { background: "#d9ebe5", skin: "#efb58f", hair: "#25394c", outfit: "#4b8074", eye: "#26343d", mouth: "#b85f58", hairStyle: "crop", expression: "smile", accessory: "square-glasses", accessoryColor: "#315b70" }),
  persona(18, { background: "#e8e1f1", skin: "#8f5b44", hair: "#202129", outfit: "#705c9e", eye: "#25252b", mouth: "#e4a07d", hairStyle: "wave", expression: "soft", accessory: "round-glasses", accessoryColor: "#c59b4c" }),
  persona(19, { background: "#f1e7cf", skin: "#9b6248", hair: "#25242a", outfit: "#c49337", eye: "#26272b", mouth: "#e4a17d", hairStyle: "crop", expression: "neutral", accessory: "lab-cap", accessoryColor: "#e7e1d4" }),
  persona(20, { background: "#e7e1ef", skin: "#d3926d", hair: "#40342d", outfit: "#725d99", eye: "#27292e", mouth: "#a95551", hairStyle: "bob", expression: "soft", accessory: "headset", accessoryColor: "#d7a947" }),
] as const

const PERSONA_BY_KEY = new Map(PIXEL_PERSONAS.map((item) => [item.key, item]))

function stableHash(value: string): number {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

export function findPixelPersona(key: string): PixelPersona | null {
  return PERSONA_BY_KEY.get(key as PixelPersonaKey) ?? null
}

export function resolveDefaultPixelPersona(viewerId: string): PixelPersona {
  const normalized = viewerId.trim() || "bioinfoflow-user"
  return PIXEL_PERSONAS[stableHash(normalized) % PIXEL_PERSONAS.length]
}

export function getPixelPersonaCandidates(
  viewerId: string,
  page: number,
  count = 6,
): PixelPersona[] {
  const safeCount = Math.max(1, Math.min(count, PIXEL_PERSONAS.length))
  const safePage = Number.isFinite(page) ? Math.max(0, Math.floor(page)) : 0
  const start = (stableHash(viewerId.trim() || "bioinfoflow-user") + safePage * safeCount)
    % PIXEL_PERSONAS.length

  return Array.from(
    { length: safeCount },
    (_, offset) => PIXEL_PERSONAS[(start + offset) % PIXEL_PERSONAS.length],
  )
}

export function toPixelPersonaReference(key: PixelPersonaKey): string {
  if (!findPixelPersona(key)) {
    throw new Error(`Unknown pixel persona: ${key}`)
  }
  return `${PIXEL_PERSONA_REFERENCE_PREFIX}${key}`
}

export function parsePixelPersonaReference(value?: string | null): PixelPersonaKey | null {
  if (!value?.startsWith(PIXEL_PERSONA_REFERENCE_PREFIX)) {
    return null
  }

  const key = value.slice(PIXEL_PERSONA_REFERENCE_PREFIX.length)
  return findPixelPersona(key)?.key ?? null
}

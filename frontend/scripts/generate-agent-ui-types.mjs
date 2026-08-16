import { readFile, writeFile } from "node:fs/promises"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import { compile } from "json-schema-to-typescript"

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..")
const schemaPath = resolve(root, "../docs/contracts/agent-ui-v1.json")
const outputPath = resolve(root, "lib/agent/protocol.generated.ts")
const check = process.argv.includes("--check")

const schema = JSON.parse(await readFile(schemaPath, "utf8"))
const generated = await compile(schema, "AgentUiContractBundle", {
  bannerComment:
    "/* Generated from docs/contracts/agent-ui-v1.json. Do not edit by hand. */",
  declareExternallyReferenced: true,
  enableConstEnums: false,
  format: true,
  style: {
    semi: false,
    singleQuote: false,
    trailingComma: "all",
  },
})

if (check) {
  const committed = await readFile(outputPath, "utf8").catch(() => null)
  if (committed === generated) process.exit(0)
  console.error(
    "Agent UI protocol types are stale. Run `bun run generate:agent-protocol`.",
  )
  process.exit(1)
}

await writeFile(outputPath, generated)

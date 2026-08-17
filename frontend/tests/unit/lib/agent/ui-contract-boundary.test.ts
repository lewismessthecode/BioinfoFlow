import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"

import { describe, expect, it } from "vitest"

const agentComponentsDirectory = "components/bioinfoflow/agent"
const nonUiBoundaries = new Set([
  `${agentComponentsDirectory}/use-agent-workbench-controller.ts`,
])

function sourceFiles(directory: string): string[] {
  return readdirSync(join(process.cwd(), directory), { withFileTypes: true })
    .flatMap((entry) => {
      const relativePath = `${directory}/${entry.name}`
      return entry.isDirectory()
        ? sourceFiles(relativePath)
        : /\.(ts|tsx)$/.test(entry.name)
          ? [relativePath]
          : []
    })
}

function productionConversationUiFiles() {
  const componentFiles = sourceFiles(agentComponentsDirectory).filter(
    (path) => !nonUiBoundaries.has(path),
  )
  return ["app/(app)/agent/page.tsx", ...componentFiles]
}

describe("Agent conversation UI contract boundary", () => {
  it("keeps production UI behind stable Conversation and Trace view models", () => {
    const forbiddenImports = [
      "@/lib/agent/contracts",
      "@/lib/agent/transport/",
    ]
    const offenders = productionConversationUiFiles().filter((relativePath) => {
      const source = readFileSync(join(process.cwd(), relativePath), "utf8")
      return forbiddenImports.some((specifier) => source.includes(specifier))
    })

    expect(offenders).toEqual([])
  })
})

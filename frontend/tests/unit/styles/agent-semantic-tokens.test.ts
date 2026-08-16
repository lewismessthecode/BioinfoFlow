import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const readSource = (path: string) =>
  readFileSync(resolve(process.cwd(), path), "utf8")

describe("Agent semantic surfaces", () => {
  it("defines theme-derived Agent surfaces and maps them into Tailwind", () => {
    const css = readSource("app/globals.css")

    for (const token of [
      "--agent-composer-surface:",
      "--agent-transcript-subtle:",
      "--agent-activity-hover:",
      "--agent-approval-warning:",
      "--agent-halo:",
    ]) {
      expect(css.split(token)).toHaveLength(3)
    }
    expect(css).toContain(
      "--color-agent-approval-warning: var(--agent-approval-warning);",
    )
  })

  it("routes Agent surfaces through semantic tokens", () => {
    expect(readSource("components/bioinfoflow/agent/agent-composer.tsx")).toContain(
      "bg-agent-composer-surface",
    )
    expect(readSource("components/bioinfoflow/agent/agent-transcript.tsx")).toContain(
      "bg-agent-transcript-subtle",
    )
    expect(readSource("components/bioinfoflow/agent/agent-activity.tsx")).toContain(
      "hover:bg-agent-activity-hover",
    )
    expect(readSource("components/bioinfoflow/agent/interaction-card.tsx")).toContain(
      "bg-agent-approval-warning",
    )
    expect(readSource("components/bioinfoflow/agent/agent-workbench.tsx")).toContain(
      "bg-agent-halo",
    )
  })
})

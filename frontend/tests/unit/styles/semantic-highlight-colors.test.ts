import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const readFrontendSource = (path: string) =>
  readFileSync(resolve(process.cwd(), path), "utf8")

const auditedSemanticSources = [
  "app/(demo)/demo/page.tsx",
  "app/auth/page.tsx",
  "app/(app)/connections/components/connection-list.tsx",
  "app/(app)/connections/components/connection-ui.tsx",
  "app/(app)/workflows/[id]/components/workflow-source-tab.tsx",
  "app/(app)/workflows/components/register-sub-components.tsx",
  "components/bioinfoflow/agent-core/agent-core-turn-block.tsx",
  "components/bioinfoflow/agent-runtime/agent-composer.tsx",
  "components/bioinfoflow/agent-runtime/agent-environment-card.tsx",
  "components/bioinfoflow/agent-runtime/artifact-viewers.tsx",
  "components/bioinfoflow/agent-runtime/connect-model-dialog.tsx",
  "components/bioinfoflow/agent-runtime/connected-node-selector.tsx",
  "components/bioinfoflow/agent-runtime/todo-checklist.tsx",
  "components/bioinfoflow/card/card-base.tsx",
  "components/bioinfoflow/composer-selector-chip.ts",
  "components/bioinfoflow/remote-connection-status.tsx",
  "components/bioinfoflow/run-stage-panel.tsx",
  "components/bioinfoflow/settings/llm-catalog-panel.tsx",
  "components/auth/demo-auth-screen.tsx",
  "components/landing/bento-grid.tsx",
  "components/landing/hardware-section.tsx",
  "components/landing/hero-section.tsx",
] as const

const retiredSemanticColors =
  /(?:emerald|green|red|rose)-(?:50|100|200|300|400|500|600|700|800|900|950)|#(?:346538|edf3ec|9f2f2d|fdebec|3a9b5b|58c486|2f8f55|c7e4ce|e3f3e7|b5dac0|d8eedf|257745|23583a|173826|2b7047|1d4530|f4d6d7|dde8db)/i

describe("semantic highlight colors", () => {
  it("defines the approved balanced tonal roles for light and dark themes", () => {
    const css = readFrontendSource("app/globals.css")

    expect(css).toContain("--success: #3F8A5D;")
    expect(css).toContain("--success-foreground: #2F744A;")
    expect(css).toContain("--success-muted: #E9F3EC;")
    expect(css).toContain("--success-border: #C6DEC9;")
    expect(css).toContain("--error: #C0575C;")
    expect(css).toContain("--error-foreground: #984248;")
    expect(css).toContain("--error-muted: #F9EAEC;")
    expect(css).toContain("--error-border: #E9C5C8;")

    expect(css).toContain("--success: #5DBB7C;")
    expect(css).toContain("--success-foreground: #78C991;")
    expect(css).toContain("--success-muted: #17271D;")
    expect(css).toContain("--success-border: #31563D;")
    expect(css).toContain("--error: #D96C72;")
    expect(css).toContain("--error-foreground: #E58A8E;")
    expect(css).toContain("--error-muted: #2D1B1D;")
    expect(css).toContain("--error-border: #60383C;")
  })

  it("exposes every semantic role through Tailwind theme mappings", () => {
    const css = readFrontendSource("app/globals.css")

    for (const mapping of [
      "--color-success-foreground: var(--success-foreground);",
      "--color-success-muted: var(--success-muted);",
      "--color-success-border: var(--success-border);",
      "--color-error: var(--error);",
      "--color-error-foreground: var(--error-foreground);",
      "--color-error-muted: var(--error-muted);",
      "--color-error-border: var(--error-border);",
    ]) {
      expect(css).toContain(mapping)
    }
  })

  it("routes shared status surfaces through semantic roles without colored glows", () => {
    const composer = readFrontendSource(
      "components/bioinfoflow/composer-selector-chip.ts",
    )
    const dagNode = readFrontendSource("components/bioinfoflow/dag/dag-node.tsx")
    const statusBadge = readFrontendSource("components/ui/status-badge.tsx")
    const sonner = readFrontendSource("components/ui/sonner.tsx")

    expect(composer).toContain("bg-success-muted")
    expect(composer).toContain("text-success-foreground")
    expect(dagNode).not.toContain("shadow-[0_0_12px_var(--success-border)]")
    expect(dagNode).not.toContain("shadow-[0_0_12px_var(--error-border)]")
    expect(readFrontendSource("app/globals.css")).not.toContain(
      "box-shadow: 0 0 12px",
    )
    expect(statusBadge).toContain("text-success-foreground")
    expect(statusBadge).toContain("text-error-foreground")
    expect(sonner).toContain('"--error-bg": "var(--error-muted)"')
    expect(sonner).toContain('"--error-text": "var(--error-foreground)"')
    expect(sonner).toContain('"--error-border": "var(--error-border)"')
  })

  it("removes retired hard-coded semantic colors from audited components", () => {
    for (const path of auditedSemanticSources) {
      expect(readFrontendSource(path), path).not.toMatch(retiredSemanticColors)
    }
  })
})

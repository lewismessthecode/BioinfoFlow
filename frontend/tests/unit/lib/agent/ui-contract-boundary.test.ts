import { readFileSync } from "node:fs"
import { join } from "node:path"

import { describe, expect, it } from "vitest"

// Transport contracts remain legal in controller/projection/adapter modules; this
// list covers the production component graph that renders the Conversation View.
const productionConversationUi = [
  "app/(app)/agent/page.tsx",
  "components/bioinfoflow/agent/agent-workbench.tsx",
  "components/bioinfoflow/agent/agent-composer.tsx",
  "components/bioinfoflow/agent/permission-menu.tsx",
  "components/bioinfoflow/agent/conversation-transcript.tsx",
  "components/bioinfoflow/agent/interaction-card.tsx",
  "components/bioinfoflow/agent/agent-activity.tsx",
  "components/bioinfoflow/agent/agent-thinking.tsx",
  "components/bioinfoflow/agent/plan-entry.tsx",
]

describe("Agent conversation UI contract boundary", () => {
  it("keeps production UI independent from Harness transport contracts", () => {
    const offenders = productionConversationUi.filter((relativePath) => {
      const source = readFileSync(join(process.cwd(), relativePath), "utf8")
      return source.includes("@/lib/agent/contracts")
    })

    expect(offenders).toEqual([])
  })
})

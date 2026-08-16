import { describe, expect, it } from "vitest"

import enMessages from "@/messages/en.json"
import zhMessages from "@/messages/zh-CN.json"

describe("Agent welcome copy", () => {
  it("uses a warm, concise invitation in both locales", () => {
    expect(enMessages.agentWorkbench.emptyTitle).toBe("Ready when you are.")
    expect(zhMessages.agentWorkbench.emptyTitle).toBe("准备好了，随时开始")
  })
})

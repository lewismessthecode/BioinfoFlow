import { describe, expect, it } from "vitest"

import enMessages from "@/messages/en.json"
import zhMessages from "@/messages/zh-CN.json"

describe("notification trigger messages", () => {
  it("stores trigger labels as nested keys for English and Chinese locales", () => {
    for (const messages of [enMessages, zhMessages]) {
      const triggers = messages.notificationConfig.triggers

      expect(Object.keys(triggers).some((key) => key.includes("."))).toBe(false)
      expect(triggers.run.completed).toBeTypeOf("string")
      expect(triggers.run.failed).toBeTypeOf("string")
      expect(triggers.run.cancelled).toBeTypeOf("string")
      expect(triggers.batch.completed).toBeTypeOf("string")
      expect(triggers.batch.failed).toBeTypeOf("string")
    }
  })
})

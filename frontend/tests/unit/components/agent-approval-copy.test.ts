import { describe, expect, it } from "vitest"

import enMessages from "@/messages/en.json"
import zhMessages from "@/messages/zh-CN.json"

describe("Agent approval copy", () => {
  it("describes Harness approval policy without colliding with environment Auto", () => {
    expect(enMessages.agentComposer.permission).toMatchObject({
      label: "Approval",
      title: "Approval policy",
      ask_changes: {
        name: "Confirm changes",
        description:
          "Read-only actions run directly; confirm every workspace change.",
      },
      ask_dangerous: {
        name: "Confirm risks",
        description:
          "Routine changes run directly; confirm risky or gated actions.",
      },
      full_access: {
        name: "No approval",
        description:
          "Allowed actions run directly within workspace and hard safety limits.",
      },
    })

    expect(zhMessages.agentComposer.permission).toMatchObject({
      label: "审批",
      title: "审批方式",
      ask_changes: {
        name: "更改确认",
        description: "只读操作直接执行；每次工作区更改都需要确认。",
      },
      ask_dangerous: {
        name: "风险确认",
        description: "常规更改直接执行；风险或受控操作需要确认。",
      },
      full_access: {
        name: "免审批",
        description: "允许的操作直接执行，仍受工作区和硬性安全边界限制。",
      },
    })

    expect(enMessages.agentComposer.permission.ask_dangerous.name).not.toBe(
      enMessages.agentComposer.environment.auto.name,
    )
    expect(zhMessages.agentComposer.permission.ask_dangerous.name).not.toBe(
      zhMessages.agentComposer.environment.auto.name,
    )
  })
})

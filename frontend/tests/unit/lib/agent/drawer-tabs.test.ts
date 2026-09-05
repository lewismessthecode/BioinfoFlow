import { describe, expect, it } from "vitest"

import {
  addDrawerTab,
  closeDrawerTab,
  reorderDrawerTabs,
  type AgentDrawerTab,
} from "@/lib/agent/drawer-tabs"

describe("drawer tabs", () => {
  it("reuses an existing resource tab instead of creating a duplicate", () => {
    const initial: AgentDrawerTab[] = [
      { id: "file:reports/qc.html", kind: "file", filePath: "reports/qc.html", title: "qc.html" },
      { id: "artifacts", kind: "artifacts", title: "Artifacts" },
    ]

    expect(addDrawerTab(initial, initial[1].id, initial[0])).toEqual({
      tabs: initial,
      activeTabId: "file:reports/qc.html",
    })
  })

  it("selects a sensible neighbor after closing the active tab", () => {
    const tabs: AgentDrawerTab[] = [
      { id: "workspace", kind: "workspace", title: "Files" },
      { id: "artifacts", kind: "artifacts", title: "Artifacts" },
      { id: "browser", kind: "browser", title: "Browser" },
    ]

    expect(closeDrawerTab(tabs, "artifacts", "artifacts")).toEqual({
      tabs: [tabs[0], tabs[2]],
      activeTabId: "browser",
    })
  })

  it("reorders tabs without changing their identity", () => {
    const tabs: AgentDrawerTab[] = [
      { id: "files", kind: "workspace", title: "Files" },
      { id: "artifacts", kind: "artifacts", title: "Artifacts" },
      { id: "browser", kind: "browser", title: "Browser" },
    ]

    expect(reorderDrawerTabs(tabs, 0, 2).map((tab) => tab.id)).toEqual([
      "artifacts",
      "browser",
      "files",
    ])
    expect(reorderDrawerTabs(tabs, -1, 1)).toEqual(tabs)
  })
})

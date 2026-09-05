export type AgentDrawerTabKind = "artifacts" | "workspace" | "dag" | "browser" | "file" | "artifact"

export type AgentDrawerTab = {
  id: string
  kind: AgentDrawerTabKind
  title: string
  filePath?: string
  artifactId?: string
}

export function drawerToolTab(kind: Exclude<AgentDrawerTabKind, "file" | "artifact">): AgentDrawerTab {
  const titleByKind: Record<Exclude<AgentDrawerTabKind, "file" | "artifact">, string> = {
    artifacts: "Artifacts",
    workspace: "Files",
    dag: "DAG",
    browser: "Browser",
  }
  return { id: kind, kind, title: titleByKind[kind] }
}

export function drawerFileTab(file: { name: string; path: string }): AgentDrawerTab {
  return { id: `file:${file.path}`, kind: "file", title: file.name, filePath: file.path }
}

export function drawerArtifactTab(artifactId: string): AgentDrawerTab {
  return { id: `artifact:${artifactId}`, kind: "artifact", title: "Artifact", artifactId }
}

export function isDrawerTab(value: unknown): value is AgentDrawerTab {
  if (!value || typeof value !== "object") return false
  const tab = value as Partial<AgentDrawerTab>
  return typeof tab.id === "string" && typeof tab.title === "string" &&
    (tab.kind === "artifacts" || tab.kind === "workspace" || tab.kind === "dag" || tab.kind === "browser" || tab.kind === "file" || tab.kind === "artifact")
}

export function addDrawerTab(
  tabs: readonly AgentDrawerTab[],
  activeTabId: string | null,
  tab: AgentDrawerTab,
): { tabs: AgentDrawerTab[]; activeTabId: string } {
  const existing = tabs.find((item) => item.id === tab.id)
  if (existing) return { tabs: [...tabs], activeTabId: existing.id }
  return { tabs: [...tabs, tab], activeTabId: tab.id }
}

export function closeDrawerTab(
  tabs: readonly AgentDrawerTab[],
  activeTabId: string | null,
  tabId: string,
): { tabs: AgentDrawerTab[]; activeTabId: string | null } {
  const index = tabs.findIndex((tab) => tab.id === tabId)
  if (index < 0) return { tabs: [...tabs], activeTabId }
  const nextTabs = tabs.filter((tab) => tab.id !== tabId)
  if (activeTabId !== tabId) return { tabs: nextTabs, activeTabId }
  return {
    tabs: nextTabs,
    activeTabId: nextTabs[index]?.id ?? nextTabs[index - 1]?.id ?? null,
  }
}

export function reorderDrawerTabs(
  tabs: readonly AgentDrawerTab[],
  fromIndex: number,
  toIndex: number,
): AgentDrawerTab[] {
  if (
    fromIndex < 0 ||
    fromIndex >= tabs.length ||
    toIndex < 0 ||
    toIndex >= tabs.length ||
    fromIndex === toIndex
  ) {
    return [...tabs]
  }
  const next = [...tabs]
  const [moved] = next.splice(fromIndex, 1)
  next.splice(toIndex, 0, moved)
  return next
}

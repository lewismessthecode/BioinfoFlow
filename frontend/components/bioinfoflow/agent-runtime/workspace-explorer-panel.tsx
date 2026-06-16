"use client"

import { FilesTab } from "./files-tab"

export function WorkspaceExplorerPanel({ projectId }: { projectId?: string | null }) {
  return <FilesTab projectId={projectId} />
}

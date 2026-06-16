"use client"

import { FilesTab } from "./files-tab"

export function WorkspaceExplorerPanel({
  projectId,
  onAddContext,
}: {
  projectId?: string | null
  onAddContext?: (path: string) => void
}) {
  return <FilesTab projectId={projectId} onAddContext={onAddContext} />
}

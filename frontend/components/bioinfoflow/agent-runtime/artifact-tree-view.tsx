"use client"

import { useState } from "react"
import { ChevronDown, ChevronRight, Folder } from "@/lib/icons"

import { cn } from "@/lib/utils"
import type {
  ArtifactTree,
  ArtifactTreeDirectory,
  ArtifactTreeNode,
} from "./artifact-tree"
import { ArtifactIcon } from "./artifact-viewers"

export function ArtifactTreeView({
  tree,
  selectedArtifactId,
  label,
  typeLabel,
  onSelectArtifact,
}: {
  tree: ArtifactTree
  selectedArtifactId: string | null
  label: string
  typeLabel: (type: string) => string
  onSelectArtifact: (artifactId: string) => void
}) {
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(() => new Set())

  return (
    <div role="tree" aria-label={label} className="grid min-w-0 gap-0.5">
      <ArtifactTreeRow
        node={tree.root}
        depth={0}
        root
        collapsedIds={collapsedIds}
        selectedArtifactId={selectedArtifactId}
        typeLabel={typeLabel}
        onToggle={(id) => setCollapsedIds((current) => toggleSet(current, id))}
        onSelectArtifact={onSelectArtifact}
      />
    </div>
  )
}

function ArtifactTreeRow({
  node,
  depth,
  root = false,
  collapsedIds,
  selectedArtifactId,
  typeLabel,
  onToggle,
  onSelectArtifact,
}: {
  node: ArtifactTreeNode
  depth: number
  root?: boolean
  collapsedIds: Set<string>
  selectedArtifactId: string | null
  typeLabel: (type: string) => string
  onToggle: (id: string) => void
  onSelectArtifact: (artifactId: string) => void
}) {
  if (node.kind === "directory") {
    const collapsed = collapsedIds.has(node.id)
    return (
      <div
        role="treeitem"
        aria-expanded={!collapsed}
        aria-selected={false}
        className="grid min-w-0 gap-0.5"
      >
        <button
          type="button"
          aria-label={node.name}
          aria-expanded={!collapsed}
          title={node.path}
          onClick={() => onToggle(node.id)}
          className={cn(
            "flex min-w-0 items-center gap-2 rounded-[7px] pr-2 text-left text-sm transition-colors duration-200 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/25",
            root ? "min-h-12" : "min-h-10",
          )}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          {collapsed ? (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )}
          <Folder className="h-[18px] w-[18px] shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium text-foreground">{node.name}</span>
            {root ? (
              <span className="mt-0.5 block text-[11px] tabular-nums text-muted-foreground">
                {countFiles(node)}
              </span>
            ) : null}
          </span>
        </button>
        {!collapsed ? (
          <div role="group" className="grid min-w-0 gap-0.5">
            {node.children.map((child) => (
              <ArtifactTreeRow
                key={child.id}
                node={child}
                depth={depth + 1}
                collapsedIds={collapsedIds}
                selectedArtifactId={selectedArtifactId}
                typeLabel={typeLabel}
                onToggle={onToggle}
                onSelectArtifact={onSelectArtifact}
              />
            ))}
          </div>
        ) : null}
      </div>
    )
  }

  const summary = node.artifact.summary || typeLabel(node.artifact.type)
  const selected = selectedArtifactId === node.artifactId
  return (
    <div role="treeitem" aria-selected={selected} className="min-w-0">
      <button
        type="button"
        title={node.sourcePath}
        onClick={() => onSelectArtifact(node.artifactId)}
        className={cn(
          "group flex min-h-11 w-full min-w-0 items-center gap-2 rounded-[7px] pr-2 text-left transition-colors duration-200 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/25",
          selected && "bg-muted/55",
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        <span className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <ArtifactIcon type={node.artifact.type} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-foreground">
            {node.name}
          </span>
          <span className="mt-0.5 block truncate text-xs text-muted-foreground">
            {summary}
          </span>
        </span>
      </button>
    </div>
  )
}

function countFiles(directory: ArtifactTreeDirectory): number {
  return directory.children.reduce(
    (count, node) =>
      count + (node.kind === "file" ? 1 : countFiles(node)),
    0,
  )
}

function toggleSet(current: Set<string>, value: string) {
  const next = new Set(current)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  return next
}

import type { AgentRuntimeArtifact } from "@/lib/agent-runtime"

export type ArtifactTreeFile = {
  kind: "file"
  id: string
  name: string
  path: string
  sourcePath: string
  artifactId: string
  artifact: AgentRuntimeArtifact
}

export type ArtifactTreeDirectory = {
  kind: "directory"
  id: string
  name: string
  path: string
  children: ArtifactTreeNode[]
}

export type ArtifactTreeNode = ArtifactTreeDirectory | ArtifactTreeFile

export type ArtifactTree = {
  root: ArtifactTreeDirectory
  fileCount: number
}

type NormalizedArtifact = {
  artifact: AgentRuntimeArtifact
  absolute: boolean
  pathBacked: boolean
  normalizedPath: string
  segments: string[]
  sourcePath: string
  index: number
}

export function buildArtifactTree(
  artifacts: AgentRuntimeArtifact[],
  fallbackRootName = "Artifacts",
): ArtifactTree {
  const records = deduplicateArtifacts(artifacts)
  const sharedSegments = commonParentSegments(
    records.filter((record) => record.absolute),
  )
  const rootName = sharedSegments.at(-1) ?? fallbackRootName
  const root: ArtifactTreeDirectory = {
    kind: "directory",
    id: "artifact-root",
    name: rootName,
    path: rootName,
    children: [],
  }

  for (const record of records) {
    const relativeSegments = record.absolute
      ? sharedSegments.length
        ? record.segments.slice(sharedSegments.length)
        : [record.segments.at(-1) ?? record.artifact.title]
      : record.segments
    insertArtifact(
      root,
      relativeSegments.length ? relativeSegments : [record.artifact.title],
      record,
    )
  }

  sortTree(root)
  return { root, fileCount: records.length }
}

function artifactPath(artifact: AgentRuntimeArtifact) {
  if (artifact.file_path?.trim()) {
    return { value: artifact.file_path, pathBacked: true }
  }
  const payloadPath = artifact.payload?.path
  if (typeof payloadPath === "string" && payloadPath.trim()) {
    return { value: payloadPath, pathBacked: true }
  }
  const title = artifact.title.trim() || artifact.id
  return {
    value: title,
    pathBacked: title.includes("/") || title.includes("\\"),
  }
}

function normalizePath(value: string) {
  const trimmed = value.trim().replaceAll("\\", "/")
  const absolute = trimmed.startsWith("/") || /^[A-Za-z]:\//.test(trimmed)
  const segments: string[] = []

  for (const segment of trimmed.split("/")) {
    if (!segment || segment === ".") continue
    if (segment === "..") {
      segments.pop()
      continue
    }
    segments.push(segment)
  }

  return {
    absolute,
    normalizedPath: `${absolute ? "/" : ""}${segments.join("/")}`,
    segments,
  }
}

function deduplicateArtifacts(artifacts: AgentRuntimeArtifact[]) {
  const records = new Map<string, NormalizedArtifact>()

  artifacts.forEach((artifact, index) => {
    const candidate = artifactPath(artifact)
    const normalized = normalizePath(candidate.value)
    const record: NormalizedArtifact = {
      artifact,
      absolute: normalized.absolute,
      pathBacked: candidate.pathBacked,
      normalizedPath: normalized.normalizedPath,
      segments: normalized.segments.length
        ? normalized.segments
        : [artifact.title || artifact.id],
      sourcePath: candidate.value,
      index,
    }
    const key = candidate.pathBacked
      ? `path:${normalized.normalizedPath}`
      : `artifact:${artifact.id}`
    const current = records.get(key)
    if (!current || isNewer(record, current)) records.set(key, record)
  })

  return [...records.values()]
}

function isNewer(next: NormalizedArtifact, current: NormalizedArtifact) {
  const nextUpdatedAt = Date.parse(next.artifact.updated_at)
  const currentUpdatedAt = Date.parse(current.artifact.updated_at)
  if (Number.isFinite(nextUpdatedAt) && Number.isFinite(currentUpdatedAt)) {
    if (nextUpdatedAt !== currentUpdatedAt) return nextUpdatedAt > currentUpdatedAt
  } else if (next.artifact.updated_at !== current.artifact.updated_at) {
    return next.artifact.updated_at > current.artifact.updated_at
  }
  return next.index > current.index
}

function commonParentSegments(records: NormalizedArtifact[]) {
  if (!records.length) return []
  const directories = records.map((record) => record.segments.slice(0, -1))
  const [first = []] = directories
  let length = first.length

  for (const directory of directories.slice(1)) {
    length = Math.min(length, directory.length)
    let index = 0
    while (index < length && directory[index] === first[index]) index += 1
    length = index
  }

  return first.slice(0, length)
}

function insertArtifact(
  root: ArtifactTreeDirectory,
  segments: string[],
  record: NormalizedArtifact,
) {
  const filename = segments.at(-1) || record.artifact.title || record.artifact.id
  let directory = root

  for (const segment of segments.slice(0, -1)) {
    const directoryPath = joinDisplayPath(directory.path, segment)
    const existing = directory.children.find(
      (node): node is ArtifactTreeDirectory =>
        node.kind === "directory" && node.name === segment,
    )
    if (existing) {
      directory = existing
      continue
    }
    const child: ArtifactTreeDirectory = {
      kind: "directory",
      id: `directory:${directoryPath}`,
      name: segment,
      path: directoryPath,
      children: [],
    }
    directory.children.push(child)
    directory = child
  }

  const displayPath = joinDisplayPath(directory.path, filename)
  directory.children.push({
    kind: "file",
    id: `file:${record.normalizedPath || record.artifact.id}`,
    name: filename,
    path: displayPath,
    sourcePath: record.sourcePath,
    artifactId: record.artifact.id,
    artifact: record.artifact,
  })
}

function joinDisplayPath(parent: string, child: string) {
  return parent ? `${parent}/${child}` : child
}

function sortTree(directory: ArtifactTreeDirectory) {
  directory.children.sort((left, right) => {
    if (left.kind !== right.kind) return left.kind === "directory" ? -1 : 1
    return left.name.localeCompare(right.name, undefined, {
      numeric: true,
      sensitivity: "base",
    })
  })
  for (const child of directory.children) {
    if (child.kind === "directory") sortTree(child)
  }
}

import type { AllowRoot } from "@/lib/form-spec"

export type StorageSourceKind = "project" | "deliveries" | "reference" | "database" | "results"

const ROOT_TO_SOURCE_KINDS: Record<AllowRoot, StorageSourceKind[]> = {
  project_data: ["project"],
  shared_data: ["deliveries"],
  reference: ["reference"],
  any_allowed_root: ["project", "deliveries", "reference"],
}

export function allowedSourceKindsFromRoots(
  roots: AllowRoot[] | null | undefined,
): StorageSourceKind[] | undefined {
  if (!roots || roots.length === 0) return undefined

  const ordered: StorageSourceKind[] = []
  const seen = new Set<StorageSourceKind>()
  for (const root of roots) {
    for (const kind of ROOT_TO_SOURCE_KINDS[root] ?? []) {
      if (seen.has(kind)) continue
      seen.add(kind)
      ordered.push(kind)
    }
  }
  return ordered.length > 0 ? ordered : undefined
}

export function preferredSourceKindFromRoots(
  roots: AllowRoot[] | null | undefined,
): StorageSourceKind | undefined {
  return allowedSourceKindsFromRoots(roots)?.[0]
}

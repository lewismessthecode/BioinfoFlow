import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Convert a project name to a filesystem-safe slug for workspace paths.
 * - Lowercase Latin characters
 * - Replace non-alphanumeric, non-CJK characters with dashes
 * - Collapse consecutive dashes
 * - Trim leading/trailing dashes
 *
 * Examples:
 *   "COVID Analysis"  → "covid-analysis"
 *   "RNA-seq 分析"    → "rna-seq-分析"
 */
export function slugifyProjectPath(name: string): string {
  const trimmed = name.trim()
  if (!trimmed) return ""

  return trimmed
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-|-$/g, "")
    || "untitled"
}

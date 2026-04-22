"use client"

import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

// ── Table Skeleton ────────────────────────────────────────────────

export interface SkeletonColumn {
  /** Column header text (i18n-resolved) */
  header: string | React.ReactNode
  /** Tailwind width class for <th>/<td>, e.g. "w-10" */
  width?: string
  /** Header/cell alignment */
  align?: "left" | "right" | "center"
  /** Skeleton layout rendered inside each <td> */
  cell: React.ReactNode
}

interface TableSkeletonProps {
  columns: SkeletonColumn[]
  /** Number of skeleton rows (default 6) */
  rows?: number
  className?: string
}

export function TableSkeleton({ columns, rows = 6, className }: TableSkeletonProps) {
  return (
    <div className={cn("border border-border rounded-lg overflow-hidden", className)}>
      <table className="w-full">
        <thead>
          <tr className="border-b border-border bg-secondary/50">
            {columns.map((col, i) => (
              <th
                key={i}
                scope="col"
                className={cn(
                  "text-xs font-medium text-muted-foreground px-4 py-3",
                  col.width,
                  col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : "text-left",
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, rowIdx) => (
            <tr key={rowIdx} className="border-b border-border last:border-0">
              {columns.map((col, colIdx) => (
                <td
                  key={colIdx}
                  className={cn(
                    "px-4 py-3",
                    col.width,
                    col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : undefined,
                  )}
                >
                  {col.cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Grid Skeleton ─────────────────────────────────────────────────

interface GridSkeletonProps {
  /** Number of skeleton cards (default 6) */
  count?: number
  /** Grid column classes (default: responsive 1→2→3) */
  gridClassName?: string
  /** Render function for a single skeleton card */
  children: React.ReactNode
  className?: string
}

export function GridSkeleton({
  count = 6,
  gridClassName = "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
  children,
  className,
}: GridSkeletonProps) {
  return (
    <div className={cn(gridClassName, className)}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i}>{children}</div>
      ))}
    </div>
  )
}

// ── Prebuilt cell helpers ─────────────────────────────────────────

/** Two-line cell: name + description */
export function SkeletonCellNameDesc({ nameWidth = "w-32", descWidth = "w-52" }: { nameWidth?: string; descWidth?: string }) {
  return (
    <>
      <Skeleton className={cn("h-4", nameWidth)} />
      <Skeleton className={cn("mt-2 h-3", descWidth)} />
    </>
  )
}

/** Single-line cell */
export function SkeletonCellLine({ width = "w-16" }: { width?: string }) {
  return <Skeleton className={cn("h-4", width)} />
}

/** Status pill cell */
export function SkeletonCellBadge({ width = "w-20" }: { width?: string }) {
  return <Skeleton className={cn("h-5 rounded-full", width)} />
}

/** Right-aligned action buttons */
export function SkeletonCellActions({ buttons }: { buttons: Array<{ width: string; rounded?: boolean }> }) {
  return (
    <div className="flex justify-end gap-2">
      {buttons.map((btn, i) => (
        <Skeleton key={i} className={cn("h-8", btn.width, btn.rounded && "rounded-full")} />
      ))}
    </div>
  )
}

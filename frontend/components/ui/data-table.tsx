"use client"

import React from "react"
import { cn } from "@/lib/utils"

// ── Column definition ─────────────────────────────────────────────

export interface DataTableColumn<T> {
  /** Unique key for React keying */
  key: string
  /** Header content (string or ReactNode) */
  header: React.ReactNode
  /** Text alignment */
  align?: "left" | "right" | "center"
  /** Optional width class (e.g. "w-10") */
  width?: string
  /** Optional extra classes on <th> */
  headerClassName?: string
  /** Render the cell content for a row */
  cell: (row: T) => React.ReactNode
  /** Optional extra classes on <td> */
  cellClassName?: string
}

// ── DataTable ─────────────────────────────────────────────────────

interface DataTableProps<T> {
  columns: DataTableColumn<T>[]
  data: T[]
  /** Accessible table caption (rendered as sr-only) */
  caption?: string
  /** Extract a stable key for each row */
  rowKey: (row: T) => string
  /** Optional click handler for rows */
  onRowClick?: (row: T) => void
  /** Optional per-row className */
  rowClassName?: (row: T) => string | undefined
  /** Optional per-row aria attributes */
  rowProps?: (row: T) => React.HTMLAttributes<HTMLTableRowElement>
  /** Render additional content after a row (e.g. expanded detail row) */
  renderAfterRow?: (row: T) => React.ReactNode
  /** Additional className for the outer wrapper */
  className?: string
}

export function DataTable<T>({
  columns,
  data,
  caption,
  rowKey,
  onRowClick,
  rowClassName,
  rowProps,
  renderAfterRow,
  className,
}: DataTableProps<T>) {
  return (
    <div className={cn("border border-border rounded-lg overflow-hidden", className)}>
      <table className="w-full">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-border bg-secondary/50">
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={cn(
                  "text-xs font-medium text-muted-foreground px-4 py-2.5",
                  col.width,
                  col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : "text-left",
                  col.headerClassName,
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => {
            const key = rowKey(row)
            const extraProps = rowProps?.(row) ?? {}
            return (
              <React.Fragment key={key}>
                <tr
                  className={cn(
                    "border-b border-border last:border-0 hover:bg-secondary/30 transition-colors",
                    onRowClick && "cursor-pointer",
                    rowClassName?.(row),
                  )}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  {...extraProps}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        "px-4 py-2.5",
                        col.width,
                        col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : undefined,
                        col.cellClassName,
                      )}
                    >
                      {col.cell(row)}
                    </td>
                  ))}
                </tr>
                {renderAfterRow?.(row)}
              </React.Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

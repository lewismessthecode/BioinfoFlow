"use client"

import { useMemo, useState } from "react"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { FileBrowserDialog } from "@/components/bioinfoflow/file-browser-dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { ColumnSpec, FormField } from "@/lib/form-spec"
import {
  allowedSourceKindsFromRoots,
  preferredSourceKindFromRoots,
} from "@/lib/storage-source-policy"
import { FolderOpen, Plus, X } from "@/lib/icons"

type TableValue = {
  filename: string
  rows: Array<Record<string, string>>
}

interface TableFieldProps {
  field: FormField
  projectId: string
  value: unknown
  onChange: (value: TableValue) => void
  invalid?: boolean
}

const FALLBACK_COLUMNS: ColumnSpec[] = [
  { name: "sample", required: true, kind: "string" },
  { name: "value", required: false, kind: "string" },
]

export function TableField({ field, projectId, value, onChange, invalid }: TableFieldProps) {
  const t = useTranslations("workflows.runForm")
  const columns = field.columns && field.columns.length > 0 ? field.columns : FALLBACK_COLUMNS
  const preferredSourceKind = preferredSourceKindFromRoots(field.allow_roots)
  const allowedSourceKinds = allowedSourceKindsFromRoots(field.allow_roots)
  const filename = (typeof value === "object" && value !== null && "filename" in value
    ? (value as TableValue).filename
    : null) ?? `${field.id}.csv`
  const rows = useMemo<Array<Record<string, string>>>(() => {
    if (typeof value === "object" && value !== null && Array.isArray((value as TableValue).rows)) {
      return (value as TableValue).rows
    }
    return [emptyRow(columns)]
  }, [value, columns])

  const [pickerCell, setPickerCell] = useState<{ row: number; column: ColumnSpec } | null>(null)

  function update(rowIdx: number, columnName: string, cellValue: string) {
    const next = rows.map((row, idx) =>
      idx === rowIdx ? { ...row, [columnName]: cellValue } : row,
    )
    onChange({ filename, rows: next })
  }

  function addRow() {
    onChange({ filename, rows: [...rows, emptyRow(columns)] })
  }

  function removeRow(rowIdx: number) {
    onChange({ filename, rows: rows.filter((_, idx) => idx !== rowIdx) })
  }

  return (
    <div className="space-y-2" aria-invalid={invalid}>
      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((column) => (
                <TableHead key={column.name} className="text-xs">
                  {column.name}
                  {column.required ? <span className="text-destructive"> *</span> : null}
                </TableHead>
              ))}
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, rowIdx) => (
              <TableRow key={rowIdx}>
                {columns.map((column) => (
                  <TableCell key={column.name}>
                    <div className="flex items-center gap-1">
                      <Input
                        value={row[column.name] ?? ""}
                        onChange={(event) => update(rowIdx, column.name, event.target.value)}
                        className="h-8 font-mono text-xs"
                      />
                      {column.kind === "path" ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => setPickerCell({ row: rowIdx, column })}
                          aria-label={t("browse")}
                        >
                          <FolderOpen className="size-4" />
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                ))}
                <TableCell>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeRow(rowIdx)}
                    aria-label={t("removeRow")}
                  >
                    <X className="size-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <Button type="button" variant="outline" size="sm" onClick={addRow}>
        <Plus className="size-4" />
        {t("addRow")}
      </Button>

      {pickerCell ? (
        <FileBrowserDialog
          open={true}
          onOpenChange={(open) => {
            if (!open) setPickerCell(null)
          }}
          projectId={projectId}
          basePath="."
          allowSuffixes={pickerCell.column.suffixes ?? undefined}
          allowedSourceKinds={allowedSourceKinds}
          preferredSourceKind={preferredSourceKind}
          title={pickerCell.column.name}
          onSelect={(assetUri) => {
            update(pickerCell.row, pickerCell.column.name, assetUri)
            setPickerCell(null)
          }}
        />
      ) : null}
    </div>
  )
}

function emptyRow(columns: ColumnSpec[]): Record<string, string> {
  return Object.fromEntries(columns.map((column) => [column.name, ""]))
}

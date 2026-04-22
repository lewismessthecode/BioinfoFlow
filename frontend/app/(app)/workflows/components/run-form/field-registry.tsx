"use client"

import type { FormField, FormValues } from "@/lib/form-spec"
import { BoolField } from "./fields/bool-field"
import { FileField } from "./fields/file-field"
import { FileListField } from "./fields/file-list-field"
import { ScalarField } from "./fields/scalar-field"
import { SelectField } from "./fields/select-field"
import { TableField } from "./fields/table-field"

export interface FieldRendererProps {
  field: FormField
  projectId: string
  values: FormValues
  onChange: (id: string, value: unknown) => void
  invalid?: boolean
}

export function renderField({
  field,
  projectId,
  values,
  onChange,
  invalid,
}: FieldRendererProps) {
  const value = values[field.id]
  const setValue = (next: unknown) => onChange(field.id, next)

  switch (field.kind) {
    case "file":
    case "directory":
      return (
        <FileField
          field={field}
          projectId={projectId}
          value={typeof value === "string" ? value : null}
          onChange={(next) => setValue(next)}
          invalid={invalid}
        />
      )
    case "file_list":
      return (
        <FileListField
          field={field}
          projectId={projectId}
          value={Array.isArray(value) ? (value as string[]) : []}
          onChange={(next) => setValue(next)}
          invalid={invalid}
        />
      )
    case "table":
      return (
        <TableField
          field={field}
          projectId={projectId}
          value={value}
          onChange={(next) => setValue(next)}
          invalid={invalid}
        />
      )
    case "bool":
      return <BoolField field={field} value={value} onChange={(next) => setValue(next)} />
    case "select":
      return (
        <SelectField
          field={field}
          value={value}
          onChange={(next) => setValue(next)}
          invalid={invalid}
        />
      )
    case "int":
    case "float":
    case "string":
    default:
      return (
        <ScalarField
          field={field}
          value={value}
          onChange={(next) => setValue(next)}
          invalid={invalid}
        />
      )
  }
}

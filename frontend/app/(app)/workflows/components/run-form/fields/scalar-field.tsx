"use client"

import { Input } from "@/components/ui/input"
import type { FormField } from "@/lib/form-spec"

interface ScalarFieldProps {
  field: FormField
  value: unknown
  onChange: (value: unknown) => void
  invalid?: boolean
}

export function ScalarField({ field, value, onChange, invalid }: ScalarFieldProps) {
  if (field.kind === "int" || field.kind === "float") {
    const numeric = typeof value === "number" ? value : ""
    return (
      <Input
        type="number"
        step={field.kind === "int" ? "1" : "any"}
        value={numeric}
        onChange={(event) => {
          const raw = event.target.value
          if (raw === "") {
            onChange(null)
            return
          }
          const parsed = field.kind === "int" ? Number.parseInt(raw, 10) : Number.parseFloat(raw)
          onChange(Number.isNaN(parsed) ? null : parsed)
        }}
        aria-invalid={invalid}
        placeholder={field.default == null ? undefined : String(field.default)}
      />
    )
  }

  return (
    <Input
      value={typeof value === "string" ? value : value == null ? "" : String(value)}
      onChange={(event) => onChange(event.target.value)}
      aria-invalid={invalid}
      placeholder={field.default == null ? undefined : String(field.default)}
    />
  )
}

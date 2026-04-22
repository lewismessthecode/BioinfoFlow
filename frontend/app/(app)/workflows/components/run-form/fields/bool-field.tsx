"use client"

import { Switch } from "@/components/ui/switch"
import type { FormField } from "@/lib/form-spec"

interface BoolFieldProps {
  field: FormField
  value: unknown
  onChange: (value: boolean) => void
}

export function BoolField({ field, value, onChange }: BoolFieldProps) {
  return (
    <Switch
      checked={Boolean(value)}
      onCheckedChange={onChange}
      aria-label={field.label}
    />
  )
}

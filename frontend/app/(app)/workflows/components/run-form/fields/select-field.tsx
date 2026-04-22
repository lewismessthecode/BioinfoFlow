"use client"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { FormField } from "@/lib/form-spec"

interface SelectFieldProps {
  field: FormField
  value: unknown
  onChange: (value: string) => void
  invalid?: boolean
}

export function SelectField({ field, value, onChange, invalid }: SelectFieldProps) {
  const options = field.options ?? []
  const current = typeof value === "string" ? value : ""
  return (
    <Select value={current} onValueChange={onChange}>
      <SelectTrigger aria-invalid={invalid}>
        <SelectValue placeholder={field.help ?? "Select…"} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label ?? option.value}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export type FormFieldKind =
  | "file"
  | "file_list"
  | "directory"
  | "table"
  | "string"
  | "int"
  | "float"
  | "bool"
  | "select"

export type FormFieldSection = "data" | "params" | "advanced"

export type AllowRoot =
  | "project_data"
  | "shared_data"
  | "reference"
  | "database"
  | "any_allowed_root"

export type ColumnSpec = {
  name: string
  required: boolean
  kind: "string" | "int" | "float" | "bool" | "path"
  suffixes?: string[]
}

export type OptionSpec = {
  value: string
  label?: string
}

export type FormField = {
  id: string
  label: string
  section: FormFieldSection
  kind: FormFieldKind
  required: boolean
  default: unknown | null
  help?: string | null
  platform_managed: boolean
  accept?: string[] | null
  allow_roots?: AllowRoot[] | null
  materialize_to_run?: boolean
  columns?: ColumnSpec[] | null
  options?: OptionSpec[] | null
}

export type FormSpec = {
  fields: FormField[]
}

export type FormValues = Record<string, unknown>

export type FieldIssue = {
  fieldId: string
  message: string
}

export type ValidationResult = {
  ok: boolean
  issues: FieldIssue[]
}

const FILE_LIKE: ReadonlySet<FormFieldKind> = new Set(["file", "file_list", "directory"])

function defaultValue(field: FormField): unknown {
  if (field.default !== null && field.default !== undefined) return field.default
  if (field.kind === "file_list") return []
  if (field.kind === "table") return { filename: "samplesheet.csv", rows: [] }
  if (field.kind === "bool") return false
  return ""
}

export function buildInitialValues(spec: FormSpec): FormValues {
  const values: FormValues = {}
  for (const field of spec.fields) {
    if (field.platform_managed) continue
    values[field.id] = defaultValue(field)
  }
  return values
}

function isFieldFilled(field: FormField, value: unknown): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === "string") return value.trim().length > 0
  if (Array.isArray(value)) return value.length > 0

  if (field.kind === "table") {
    const rows = Array.isArray((value as { rows?: unknown }).rows)
      ? (value as { rows: unknown[] }).rows
      : []
    return rows.some((row) => {
      if (!row || typeof row !== "object") return false
      return Object.values(row).some((cell) => {
        if (cell === null || cell === undefined) return false
        return String(cell).trim().length > 0
      })
    })
  }

  return true
}

export function countFilledFields(spec: FormSpec, values: FormValues): number {
  return spec.fields.filter((field) => {
    if (field.platform_managed) return false
    return isFieldFilled(field, values[field.id])
  }).length
}

export function validateValues(spec: FormSpec, values: FormValues): ValidationResult {
  const issues: FieldIssue[] = []
  for (const field of spec.fields) {
    if (field.platform_managed) continue
    const raw = values[field.id]

    if (field.required && !isFieldFilled(field, raw)) {
      issues.push({ fieldId: field.id, message: `${field.label} is required` })
      continue
    }
    if (!isFieldFilled(field, raw)) continue

    if (FILE_LIKE.has(field.kind)) {
      const paths = field.kind === "file_list" ? (raw as string[]) : [raw as string]
      for (const path of paths) {
        if (typeof path !== "string" || path.trim().length === 0) {
          issues.push({ fieldId: field.id, message: `${field.label} must be a path` })
          break
        }
      }
    } else if (field.kind === "int") {
      if (typeof raw !== "number" || !Number.isInteger(raw)) {
        issues.push({ fieldId: field.id, message: `${field.label} must be an integer` })
      }
    } else if (field.kind === "float") {
      if (typeof raw !== "number" || Number.isNaN(raw)) {
        issues.push({ fieldId: field.id, message: `${field.label} must be a number` })
      }
    } else if (field.kind === "bool") {
      if (typeof raw !== "boolean") {
        issues.push({ fieldId: field.id, message: `${field.label} must be true or false` })
      }
    } else if (field.kind === "select") {
      const options = (field.options ?? []).map((opt) => opt.value)
      if (typeof raw !== "string" || !options.includes(raw)) {
        issues.push({ fieldId: field.id, message: `${field.label} must be one of ${options.join(", ")}` })
      }
    }
  }
  return { ok: issues.length === 0, issues }
}

export type RunOptions = {
  profile?: string | null
  max_retries?: number | null
  timeout_seconds?: number | null
  resume_from_run_id?: string | null
}

export type RunCreateV2 = {
  project_id: string
  workflow_id: string
  values: FormValues
  options?: RunOptions
}

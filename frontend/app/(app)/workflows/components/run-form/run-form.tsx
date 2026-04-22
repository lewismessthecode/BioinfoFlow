"use client"

import { useMemo } from "react"
import { useTranslations } from "next-intl"
import { Label } from "@/components/ui/label"
import type {
  FieldIssue,
  FormField,
  FormFieldSection,
  FormSpec,
  FormValues,
} from "@/lib/form-spec"
import { renderField } from "./field-registry"

interface RunFormProps {
  spec: FormSpec
  projectId: string
  values: FormValues
  onChange: (id: string, value: unknown) => void
  issues?: FieldIssue[]
}

const SECTION_ORDER: FormFieldSection[] = ["data", "params", "advanced"]

export function RunForm({ spec, projectId, values, onChange, issues = [] }: RunFormProps) {
  const t = useTranslations("workflows.runForm")
  const grouped = useMemo(() => groupBySection(spec.fields), [spec.fields])
  const issueByField = useMemo(() => {
    const map = new Map<string, string>()
    for (const issue of issues) map.set(issue.fieldId, issue.message)
    return map
  }, [issues])

  return (
    <div className="space-y-8">
      {SECTION_ORDER.map((section) => {
        const fields = grouped[section] ?? []
        if (fields.length === 0) return null
        return (
          <section key={section} className="space-y-4">
            <header className="flex items-baseline justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                {t(`section.${section}`)}
              </h3>
            </header>
            <div className="space-y-4">
              {fields.map((field) => {
                const issue = issueByField.get(field.id)
                return (
                  <div key={field.id} className="space-y-1.5">
                    <Label htmlFor={field.id} className="flex items-center gap-1.5">
                      <span>{field.label}</span>
                      {field.required ? (
                        <span className="text-xs text-destructive" aria-hidden>
                          *
                        </span>
                      ) : null}
                      {field.platform_managed ? (
                        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                          {t("platformManaged")}
                        </span>
                      ) : null}
                    </Label>
                    {renderField({
                      field,
                      projectId,
                      values,
                      onChange,
                      invalid: Boolean(issue),
                    })}
                    {field.help ? (
                      <p className="text-xs text-muted-foreground">{field.help}</p>
                    ) : null}
                    {issue ? (
                      <p className="text-xs text-destructive" role="alert">
                        {issue}
                      </p>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function groupBySection(fields: FormField[]): Record<FormFieldSection, FormField[]> {
  const groups: Record<FormFieldSection, FormField[]> = {
    data: [],
    params: [],
    advanced: [],
  }
  for (const field of fields) {
    if (field.platform_managed) continue
    groups[field.section].push(field)
  }
  return groups
}

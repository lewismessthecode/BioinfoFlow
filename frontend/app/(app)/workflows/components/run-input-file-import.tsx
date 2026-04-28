"use client"

import { useRef, useState, type ChangeEvent } from "react"
import { FileJson, Loader2, Upload } from "lucide-react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import type { FormField, FormSpec, FormValues } from "@/lib/form-spec"

interface RunInputFileImportProps {
  spec: FormSpec
  projectId: string
  onApplyValues: (values: FormValues) => void
}

export function RunInputFileImport({
  spec,
  projectId,
  onApplyValues,
}: RunInputFileImportProps) {
  const t = useTranslations("workflows.submission")
  const inputRef = useRef<HTMLInputElement>(null)
  const [isImporting, setIsImporting] = useState(false)

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    setIsImporting(true)
    try {
      const lowerName = file.name.toLowerCase()
      if (lowerName.endsWith(".json")) {
        const parsed = JSON.parse(await file.text()) as unknown
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error(t("workbench.inputFileUnsupported"))
        }
        const values = valuesFromJson(spec, parsed as Record<string, unknown>)
        onApplyValues(values)
        toast.success(t("workbench.inputFileImported"))
        return
      }

      if (
        lowerName.endsWith(".csv")
        || lowerName.endsWith(".tsv")
        || lowerName.endsWith(".txt")
      ) {
        const target = findUploadTarget(spec, lowerName)
        if (!target) {
          throw new Error(t("workbench.inputFileNoTarget"))
        }
        const formData = new FormData()
        formData.set("project_id", projectId)
        formData.set("file", file)
        const { data } = await apiRequest<{ uri: string }>("/runs/uploads", {
          method: "POST",
          body: formData,
        })
        onApplyValues({ [target.id]: data.uri })
        toast.success(t("workbench.inputFileImported"))
        return
      }

      throw new Error(t("workbench.inputFileUnsupported"))
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("workbench.inputFileImportFailed")))
    } finally {
      setIsImporting(false)
      event.target.value = ""
    }
  }

  return (
    <div className="rounded-lg border border-border/60 bg-muted/10 p-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm font-medium text-foreground">
            <FileJson className="size-4 text-muted-foreground" />
            {t("workbench.inputFileTitle")}
          </div>
          <p className="max-w-2xl text-xs leading-5 text-muted-foreground">
            {t("workbench.inputFileDescription")}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          className="shrink-0 rounded-xl"
          onClick={() => inputRef.current?.click()}
          disabled={isImporting}
        >
          {isImporting ? (
            <Loader2 className="mr-2 size-4 animate-spin" />
          ) : (
            <Upload className="mr-2 size-4" />
          )}
          {t("workbench.selectInputFile")}
        </Button>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".json,.csv,.tsv,.txt,application/json,text/csv,text/tab-separated-values,text/plain"
        className="hidden"
        onChange={handleFileChange}
      />
    </div>
  )
}

function valuesFromJson(spec: FormSpec, payload: Record<string, unknown>): FormValues {
  const byId = new Map(spec.fields.map((field) => [field.id, field]))
  const values: FormValues = {}

  for (const [rawKey, value] of Object.entries(payload)) {
    const fieldId = byId.has(rawKey) ? rawKey : rawKey.split(".").at(-1) ?? rawKey
    const field = byId.get(fieldId)
    if (!field || field.platform_managed) continue
    values[field.id] = normalizeImportedValue(field, value)
  }

  return values
}

function normalizeImportedValue(field: FormField, value: unknown): unknown {
  if (value === null || value === undefined) return value
  if (field.kind === "int" && typeof value === "string") {
    const parsed = Number.parseInt(value, 10)
    return Number.isNaN(parsed) ? value : parsed
  }
  if (field.kind === "float" && typeof value === "string") {
    const parsed = Number.parseFloat(value)
    return Number.isNaN(parsed) ? value : parsed
  }
  if (field.kind === "bool" && typeof value === "string") {
    if (value.toLowerCase() === "true") return true
    if (value.toLowerCase() === "false") return false
  }
  return value
}

function findUploadTarget(spec: FormSpec, lowerName: string): FormField | null {
  const fields = spec.fields.filter((field) => !field.platform_managed)
  const materialized = fields.filter(
    (field) => field.kind === "file" && field.materialize_to_run,
  )
  const candidates = materialized.length > 0
    ? materialized
    : fields.filter((field) => field.kind === "file")

  if (candidates.length === 0) return null
  const nameStem = lowerName.replace(/\.(csv|tsv|txt)$/i, "")
  return (
    candidates.find((field) => field.id.toLowerCase() === nameStem)
    ?? candidates.find((field) => /sample|sheet|manifest|input/.test(field.id.toLowerCase()))
    ?? candidates[0]
  )
}

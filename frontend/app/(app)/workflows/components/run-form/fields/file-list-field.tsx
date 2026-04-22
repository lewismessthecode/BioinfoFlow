"use client"

import { useState } from "react"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { FileBrowserDialog } from "@/components/bioinfoflow/file-browser-dialog"
import type { FormField } from "@/lib/form-spec"
import {
  allowedSourceKindsFromRoots,
  preferredSourceKindFromRoots,
} from "@/lib/storage-source-policy"
import { FolderOpen, Plus, X } from "lucide-react"

interface FileListFieldProps {
  field: FormField
  projectId: string
  value: string[] | null | undefined
  onChange: (value: string[]) => void
  invalid?: boolean
}

export function FileListField({ field, projectId, value, onChange, invalid }: FileListFieldProps) {
  const t = useTranslations("workflows.runForm")
  const [pickerOpen, setPickerOpen] = useState(false)
  const items = value ?? []
  const preferredKind = preferredSourceKindFromRoots(field.allow_roots)
  const allowedSourceKinds = allowedSourceKindsFromRoots(field.allow_roots)

  return (
    <div className="space-y-2">
      <ul className={invalid ? "space-y-1 ring-1 ring-destructive rounded-md p-1" : "space-y-1"}>
        {items.length === 0 ? (
          <li className="text-xs text-muted-foreground italic">{t("emptyList")}</li>
        ) : null}
        {items.map((item, index) => (
          <li key={`${item}-${index}`} className="flex items-center gap-2">
            <Input
              value={item}
              onChange={(event) => {
                const next = [...items]
                next[index] = event.target.value
                onChange(next)
              }}
              className="font-mono text-xs"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => onChange(items.filter((_, idx) => idx !== index))}
              aria-label={t("removeItem")}
            >
              <X className="size-4" />
            </Button>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setPickerOpen(true)}
        >
          <FolderOpen className="size-4" />
          {t("browse")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onChange([...items, ""])}
        >
          <Plus className="size-4" />
          {t("addManual")}
        </Button>
      </div>

      <FileBrowserDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        projectId={projectId}
        basePath="."
        allowSuffixes={field.accept ?? undefined}
        allowedSourceKinds={allowedSourceKinds}
        preferredSourceKind={preferredKind}
        title={field.label}
        onSelect={(assetUri) => {
          onChange([...items, assetUri])
          setPickerOpen(false)
        }}
      />
    </div>
  )
}

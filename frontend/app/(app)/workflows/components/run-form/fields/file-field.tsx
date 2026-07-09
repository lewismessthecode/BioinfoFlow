"use client"

import { useRef, useState, type ChangeEvent } from "react"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { FileBrowserDialog } from "@/components/bioinfoflow/file-browser-dialog"
import type { FormField } from "@/lib/form-spec"
import {
  allowedSourceKindsFromRoots,
  preferredSourceKindFromRoots,
} from "@/lib/storage-source-policy"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import { toast } from "sonner"
import { FolderOpen, Loader2, Upload, X } from "@/lib/icons"

interface FileFieldProps {
  field: FormField
  projectId: string
  value: string | null | undefined
  onChange: (value: string | null) => void
  invalid?: boolean
}

export function FileField({ field, projectId, value, onChange, invalid }: FileFieldProps) {
  const t = useTranslations("workflows.runForm")
  const tCommon = useTranslations("common")
  const tFb = useTranslations("fileBrowser")
  const [pickerOpen, setPickerOpen] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const preferredKind = preferredSourceKindFromRoots(field.allow_roots)
  const allowedSourceKinds = allowedSourceKindsFromRoots(field.allow_roots)

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setIsUploading(true)
    try {
      const formData = new FormData()
      formData.set("project_id", projectId)
      formData.set("file", file)
      const { data } = await apiRequest<{ uri: string }>("/runs/uploads", {
        method: "POST",
        body: formData,
      })
      onChange(data.uri)
    } catch (error) {
      toast.error(getApiErrorMessage(error, tFb("errors.upload")))
    } finally {
      setIsUploading(false)
      event.target.value = ""
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Input
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value || null)}
        placeholder={t("filePlaceholder")}
        aria-invalid={invalid}
        className="font-mono text-xs"
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setPickerOpen(true)}
        disabled={isUploading}
      >
        <FolderOpen className="size-4" />
        {t("browse")}
      </Button>
      {field.materialize_to_run ? (
        <>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => uploadInputRef.current?.click()}
            disabled={isUploading}
          >
            {isUploading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Upload className="size-4" />
            )}
            {tCommon("upload")}
          </Button>
          <input
            ref={uploadInputRef}
            type="file"
            accept={field.accept?.join(",")}
            className="hidden"
            onChange={handleUpload}
          />
        </>
      ) : null}
      {value ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => onChange(null)}
          aria-label={t("clear")}
        >
          <X className="size-4" />
        </Button>
      ) : null}

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
          onChange(assetUri)
          setPickerOpen(false)
        }}
      />
    </div>
  )
}

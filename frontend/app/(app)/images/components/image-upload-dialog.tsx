"use client"

import type { ChangeEvent } from "react"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  AUTOMATIC_REGISTRY_VALUE,
  getContainerRegistryLabel,
  getContainerRegistrySelectValue,
} from "@/lib/registry-utils"
import type { ContainerRegistryConfig } from "@/lib/types"
import { cn } from "@/lib/utils"

type ImportMethod = "registry" | "tarball"

interface ImageUploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  importMethod: ImportMethod
  onImportMethodChange: (method: ImportMethod) => void
  imageName: string
  onImageNameChange: (name: string) => void
  tarballFile: File | null
  onTarballFileChange: (event: ChangeEvent<HTMLInputElement>) => void
  registries: ContainerRegistryConfig[]
  selectedRegistry: string
  onSelectedRegistryChange: (registry: string) => void
  isSubmitting: boolean
  onPull: () => void
}

export function ImageUploadDialog({
  open,
  onOpenChange,
  importMethod,
  onImportMethodChange,
  imageName,
  onImageNameChange,
  tarballFile,
  onTarballFileChange,
  registries,
  selectedRegistry,
  onSelectedRegistryChange,
  isSubmitting,
  onPull,
}: ImageUploadDialogProps) {
  const tImages = useTranslations("images")
  const tCommon = useTranslations("common")
  const hasRegistryOptions = importMethod === "registry" && registries.length > 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{tImages("uploadDialog.title")}</DialogTitle>
          <DialogDescription>{tImages("uploadDialog.description")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>{tImages("uploadDialog.importMethod")}</Label>
            <div className="grid grid-cols-2 gap-2">
              {(["registry", "tarball"] as const).map((method) => (
                <button
                  key={method}
                  type="button"
                  onClick={() => onImportMethodChange(method)}
                  className={cn(
                    "flex flex-col items-center gap-1 p-3 rounded-lg border text-sm transition-colors",
                    importMethod === method
                      ? "border-foreground bg-secondary"
                      : "border-border hover:border-foreground/50",
                  )}
                >
                  <span className="font-medium capitalize">
                    {method === "registry" ? tImages("uploadDialog.methods.registry") : tImages("uploadDialog.methods.tarball")}
                  </span>
                </button>
              ))}
            </div>
          </div>
          {importMethod === "registry" ? (
            <div className="space-y-2">
              <Label htmlFor="image-name">{tImages("uploadDialog.imageName")}</Label>
              <Input
                id="image-name"
                placeholder="e.g., biocontainers/bwa:0.7.17"
                value={imageName}
                onChange={(e) => onImageNameChange(e.target.value)}
              />
              {hasRegistryOptions ? (
                <div className="space-y-2 pt-1">
                  <Label htmlFor="image-registry">{tImages("uploadDialog.registry")}</Label>
                  <select
                    id="image-registry"
                    value={selectedRegistry}
                    onChange={(event) => onSelectedRegistryChange(event.target.value)}
                    className={cn(
                      "border-input h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow]",
                      "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
                    )}
                  >
                    <option value={AUTOMATIC_REGISTRY_VALUE}>
                      {tImages("uploadDialog.registryAutomatic")}
                    </option>
                    {registries.map((registry) => {
                      const value = getContainerRegistrySelectValue(registry)
                      return (
                        <option key={registry.id ?? value} value={value}>
                          {getContainerRegistryLabel(registry)}
                        </option>
                      )
                    })}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    {tImages("uploadDialog.registryHint")}
                  </p>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="space-y-2">
              <Label htmlFor="image-tarball">{tImages("uploadDialog.tarball")}</Label>
              <Input
                id="image-tarball"
                type="file"
                accept=".tar"
                onChange={onTarballFileChange}
              />
              {tarballFile && (
                <p className="text-xs text-muted-foreground">
                  {tImages("uploadDialog.selectedFile", { name: tarballFile.name })}
                </p>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("cancel")}
          </Button>
          <Button onClick={onPull} disabled={isSubmitting}>
            {isSubmitting ? tImages("uploadDialog.submitting") : tImages("uploadDialog.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

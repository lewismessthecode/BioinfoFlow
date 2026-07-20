"use client"

import { useEffect, useRef, useState } from "react"
import AvatarEditor, { type AvatarEditorRef } from "react-avatar-editor"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"

type AvatarUploadDialogProps = {
  file: File | null
  open: boolean
  saving?: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (blob: Blob) => Promise<void> | void
}

export function AvatarUploadDialog({
  file,
  open,
  saving = false,
  onOpenChange,
  onConfirm,
}: AvatarUploadDialogProps) {
  const t = useTranslations("settings")
  const editorRef = useRef<AvatarEditorRef>(null)
  const [zoom, setZoom] = useState(1.15)
  const [processing, setProcessing] = useState(false)

  useEffect(() => {
    if (open) setZoom(1.15)
  }, [open, file])

  const handleConfirm = async () => {
    const canvas = editorRef.current?.getImageScaledToCanvas()
    if (!canvas) return

    setProcessing(true)
    try {
      const blob = await new Promise<Blob>((resolve, reject) => {
        canvas.toBlob(
          (result) => {
            if (result) resolve(result)
            else reject(new Error("Avatar crop could not be encoded."))
          },
          "image/webp",
          0.88,
        )
      })
      await onConfirm(blob)
    } finally {
      setProcessing(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden rounded-2xl border-border/70 p-0 sm:max-w-[430px]">
        <DialogHeader className="border-b border-border/60 px-6 pb-4 pt-6">
          <DialogTitle>{t("account.avatar.cropTitle")}</DialogTitle>
          <DialogDescription>
            {t("account.avatar.cropDescription")}
          </DialogDescription>
        </DialogHeader>

        <div className="grid justify-items-center gap-5 bg-secondary/25 px-6 py-6">
          {file ? (
            <div className="overflow-hidden rounded-[24px] border border-border/70 bg-card shadow-[0_14px_34px_rgba(36,35,33,0.12)]">
              <AvatarEditor
                ref={editorRef}
                image={file}
                width={256}
                height={256}
                border={14}
                borderRadius={30}
                color={[22, 22, 20, 0.72]}
                scale={zoom}
              />
            </div>
          ) : null}

          <div className="w-full space-y-2">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="avatar-zoom">{t("account.avatar.zoom")}</Label>
              <span className="text-xs tabular-nums text-muted-foreground">
                {Math.round(zoom * 100)}%
              </span>
            </div>
            <input
              id="avatar-zoom"
              type="range"
              min="1"
              max="2.5"
              step="0.05"
              value={zoom}
              onChange={(event) => setZoom(Number(event.target.value))}
              className="h-2 w-full cursor-pointer accent-foreground"
            />
          </div>
        </div>

        <DialogFooter className="border-t border-border/60 px-6 py-4">
          <Button
            type="button"
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={saving || processing}
          >
            {t("account.avatar.cancel")}
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={!file || saving || processing}
          >
            {saving || processing
              ? t("account.avatar.saving")
              : t("account.avatar.useImage")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

"use client"

import { useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { Loader2, RefreshCw, RotateCcw, Upload } from "@/lib/icons"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { UserAvatar, PixelPersonaGraphic } from "@/components/bioinfoflow/user-avatar"
import { AvatarUploadDialog } from "@/components/bioinfoflow/settings/avatar-upload-dialog"
import {
  clearDevAvatarPreference,
  useDevAvatarPreference,
  writeDevAvatarPreference,
} from "@/lib/avatar/avatar-preference"
import {
  getPixelPersonaCandidates,
  parsePixelPersonaReference,
  toPixelPersonaReference,
  type PixelPersonaKey,
} from "@/lib/avatar/pixel-personas"
import { cn } from "@/lib/utils"

const ALLOWED_AVATAR_TYPES = new Set(["image/png", "image/jpeg", "image/webp"])
const MAX_AVATAR_SOURCE_BYTES = 5 * 1024 * 1024

type AvatarSettingsPanelProps = {
  viewer: {
    id: string
    name?: string
    image?: string | null
    authEnabled: boolean
  }
}

export function AvatarSettingsPanel({ viewer }: AvatarSettingsPanelProps) {
  const t = useTranslations("settings")
  const router = useRouter()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const devPreference = useDevAvatarPreference(!viewer.authEnabled)
  const [page, setPage] = useState(0)
  const [activeImage, setActiveImage] = useState<string | null>(viewer.image ?? null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [cropOpen, setCropOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const effectiveImage = viewer.authEnabled ? activeImage : devPreference
  const activeBuiltInKey = parsePixelPersonaReference(effectiveImage)
  const candidates = getPixelPersonaCandidates(viewer.id, page, 6)
  const hasCustomChoice = Boolean(effectiveImage)

  const saveAuthenticated = async (
    request: RequestInit,
    successMessage: string,
  ) => {
    setSaving(true)
    try {
      const response = await fetch("/api/profile/avatar", request)
      if (!response.ok) throw new Error("Avatar update failed")
      const payload = (await response.json()) as {
        data?: { image?: string | null }
      }
      setActiveImage(payload.data?.image ?? null)
      toast.success(successMessage)
      router.refresh()
      return true
    } catch {
      toast.error(t("account.avatar.saveFailed"))
      return false
    } finally {
      setSaving(false)
    }
  }

  const handleBuiltInSelect = async (key: PixelPersonaKey) => {
    const reference = toPixelPersonaReference(key)
    if (!viewer.authEnabled) {
      writeDevAvatarPreference(reference)
      toast.success(t("account.avatar.saved"))
      return
    }

    await saveAuthenticated(
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ avatarKey: key }),
      },
      t("account.avatar.saved"),
    )
  }

  const handleReset = async () => {
    if (!viewer.authEnabled) {
      clearDevAvatarPreference()
      toast.success(t("account.avatar.reset"))
      return
    }

    await saveAuthenticated(
      { method: "DELETE" },
      t("account.avatar.reset"),
    )
  }

  const handleFileChange = (file?: File) => {
    if (!file) return
    if (!ALLOWED_AVATAR_TYPES.has(file.type)) {
      toast.error(t("account.avatar.unsupportedType"))
      return
    }
    if (file.size > MAX_AVATAR_SOURCE_BYTES) {
      toast.error(t("account.avatar.tooLarge"))
      return
    }
    setUploadFile(file)
    setCropOpen(true)
  }

  const handleCroppedUpload = async (blob: Blob) => {
    if (!viewer.authEnabled) {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result))
        reader.onerror = () => reject(reader.error)
        reader.readAsDataURL(blob)
      })
      writeDevAvatarPreference(dataUrl)
      toast.success(t("account.avatar.saved"))
      setCropOpen(false)
      setUploadFile(null)
      return
    }

    const formData = new FormData()
    formData.set("file", new File([blob], "avatar.webp", { type: "image/webp" }))
    const saved = await saveAuthenticated(
      { method: "POST", body: formData },
      t("account.avatar.saved"),
    )
    if (saved) {
      setCropOpen(false)
      setUploadFile(null)
    }
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-[0_1px_0_rgba(36,35,33,0.02)]">
      <div className="grid gap-5 border-b border-border/60 px-5 py-5 sm:px-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
        <div className="flex min-w-0 items-center gap-4">
          <UserAvatar
            viewerId={viewer.id}
            name={viewer.name || "Bioinfoflow User"}
            image={activeImage}
            authEnabled={viewer.authEnabled}
            alt={t("account.avatar.previewAlt")}
            className="h-[72px] w-[72px] rounded-[18px] ring-1 ring-border/70 shadow-[0_10px_24px_rgba(36,35,33,0.09)]"
            imageClassName="rounded-[18px]"
            fallbackClassName="rounded-[18px]"
          />
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-foreground">
              {t("account.avatar.title")}
            </h3>
            <p className="mt-1 max-w-[52ch] text-[13px] leading-5 text-muted-foreground">
              {t("account.avatar.description")}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            aria-label={t("account.avatar.upload")}
            className="sr-only"
            onChange={(event) => {
              handleFileChange(event.target.files?.[0])
              event.currentTarget.value = ""
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={saving}
          >
            <Upload className="mr-2 h-3.5 w-3.5" />
            {t("account.avatar.upload")}
          </Button>
          {hasCustomChoice ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleReset}
              disabled={saving}
            >
              <RotateCcw className="mr-2 h-3.5 w-3.5" />
              {t("account.avatar.restoreDefault")}
            </Button>
          ) : null}
        </div>
      </div>

      <div className="px-5 py-5 sm:px-6">
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
            {t("account.avatar.builtInLabel")}
          </p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 px-2.5 text-xs"
            onClick={() => setPage((current) => current + 1)}
            disabled={saving}
          >
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            {t("account.avatar.showAnotherSet")}
          </Button>
        </div>

        <div className="grid grid-cols-3 gap-3 sm:grid-cols-6" role="radiogroup">
          {candidates.map((persona, index) => {
            const selected = persona.key === activeBuiltInKey
            return (
              <button
                key={persona.key}
                type="button"
                role="radio"
                aria-checked={selected}
                aria-label={t("account.avatar.optionLabel", { number: index + 1 })}
                data-avatar-key={persona.key}
                disabled={saving}
                onClick={() => handleBuiltInSelect(persona.key)}
                className={cn(
                  "group relative aspect-square overflow-hidden rounded-[14px] border bg-secondary/40 p-0.5 outline-none transition-[border-color,box-shadow,transform] duration-150 motion-safe:active:scale-[0.97] focus-visible:ring-2 focus-visible:ring-ring/55 focus-visible:ring-offset-2",
                  selected
                    ? "border-foreground/55 shadow-[0_0_0_2px_hsl(var(--background)),0_0_0_4px_hsl(var(--foreground)/0.38)]"
                    : "border-border/70 hover:-translate-y-0.5 hover:border-foreground/30 hover:shadow-[0_8px_18px_rgba(36,35,33,0.1)]",
                )}
              >
                <PixelPersonaGraphic
                  persona={persona}
                  className="rounded-[11px]"
                />
                {selected ? (
                  <span className="absolute inset-x-2 bottom-1.5 rounded-full bg-foreground/88 px-1 py-0.5 text-[8px] font-semibold uppercase tracking-[0.08em] text-background">
                    {t("account.avatar.selected")}
                  </span>
                ) : null}
              </button>
            )
          })}
        </div>

        <div className="mt-4 min-h-5 text-xs text-muted-foreground" aria-live="polite">
          {saving ? (
            <span className="inline-flex items-center gap-1.5">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {t("account.avatar.saving")}
            </span>
          ) : null}
        </div>
      </div>

      <AvatarUploadDialog
        file={uploadFile}
        open={cropOpen}
        saving={saving}
        onOpenChange={(open) => {
          setCropOpen(open)
          if (!open) setUploadFile(null)
        }}
        onConfirm={handleCroppedUpload}
      />
    </section>
  )
}

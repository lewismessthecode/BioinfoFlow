"use client"

import { useState } from "react"
import { useTranslations } from "next-intl"
import { Check, ExternalLink, Loader2, X } from "lucide-react"
import { toast } from "sonner"
import { ProviderIcon } from "@/components/bioinfoflow/chat/provider-icons"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { StatusBadge } from "@/components/ui/status-badge"

// ── API key portal URLs ────────────────────────────────────────────
const PROVIDER_KEY_URLS: Record<string, string> = {
  anthropic:   "https://console.anthropic.com/settings/keys",
  openai:      "https://platform.openai.com/api-keys",
  gemini:      "https://aistudio.google.com/apikey",
  deepseek:    "https://platform.deepseek.com/api_keys",
  qwen:        "https://dashscope.console.aliyun.com/apiKey",
  xai:         "https://console.x.ai/team/default/api-keys",
  kimi:        "https://platform.moonshot.cn/console/api-keys",
  minimax:     "https://platform.minimaxi.com/user-center/basic-information/interface-key",
  openrouter:  "https://openrouter.ai/keys",
}

export type ProviderField = {
  name: "api_key" | "base_url" | "model"
  label: string
  value: string
  placeholder: string
  secret?: boolean
}

interface ProviderCardProps {
  provider: string
  label: string
  fields: ProviderField[]
  isConfigured: boolean
  onUpdateField: (field: ProviderField["name"], value: string) => Promise<void>
  onTest: () => Promise<{ success: boolean; error: string | null }>
}

export function ProviderCard({
  provider,
  label,
  fields,
  isConfigured,
  onUpdateField,
  onTest,
}: ProviderCardProps) {
  const t = useTranslations("settings")

  const [isTesting, setIsTesting] = useState(false)
  const [testResult, setTestResult] = useState<"success" | "error" | null>(null)
  const [savingField, setSavingField] = useState<ProviderField["name"] | null>(null)
  const [editingField, setEditingField] = useState<ProviderField["name"] | null>(null)
  const [draftValues, setDraftValues] = useState<
    Partial<Record<ProviderField["name"], string>>
  >({})

  const updateDraft = (field: ProviderField["name"], value: string) => {
    setDraftValues((prev) => ({ ...prev, [field]: value }))
  }

  const finishEditing = (field: ProviderField["name"]) => {
    setEditingField((prev) => (prev === field ? null : prev))
    setDraftValues((prev) => {
      const next = { ...prev }
      delete next[field]
      return next
    })
  }

  const saveField = async (field: ProviderField, value: string) => {
    setSavingField(field.name)
    try {
      await onUpdateField(field.name, value)
      setTestResult(null)
      toast.success(
        value
          ? field.name === "api_key"
            ? t("keySaved")
            : t("settingSaved", { field: field.label })
          : field.name === "api_key"
            ? t("keyCleared")
            : t("settingCleared", { field: field.label })
      )
    } catch {
      // Error already toasted by the hook.
    } finally {
      setSavingField(null)
      finishEditing(field.name)
    }
  }

  const handleFocus = (field: ProviderField) => {
    setEditingField(field.name)
    updateDraft(field.name, field.secret ? "" : field.value)
    setTestResult(null)
  }

  const handleBlur = async (field: ProviderField) => {
    if (editingField !== field.name) {
      return
    }

    const nextValue = (draftValues[field.name] ?? "").trim()
    const currentValue = field.value.trim()

    if (field.secret && !nextValue) {
      finishEditing(field.name)
      return
    }

    if (nextValue === currentValue) {
      finishEditing(field.name)
      return
    }

    await saveField(field, nextValue)
  }

  const handleKeyDown = (
    event: React.KeyboardEvent<HTMLInputElement>,
    field: ProviderField
  ) => {
    if (event.key === "Enter") {
      event.preventDefault()
      event.currentTarget.blur()
    }

    if (event.key === "Escape") {
      event.preventDefault()
      finishEditing(field.name)
    }
  }

  const handleClearField = async (field: ProviderField) => {
    await saveField(field, "")
  }

  const handleTest = async () => {
    setIsTesting(true)
    setTestResult(null)
    const result = await onTest()
    setTestResult(result.success ? "success" : "error")
    if (result.success) {
      toast.success(t("testSuccess"))
    } else {
      toast.error(result.error || t("testFailed"))
    }
    setIsTesting(false)
  }

  const keyUrl = PROVIDER_KEY_URLS[provider]

  return (
    <Card className="transition-colors">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <ProviderIcon provider={provider} size={16} />
            <span className="font-semibold text-sm">{label}</span>
            {keyUrl && (
              <a
                href={keyUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
                title={t("getApiKey", { provider: label })}
              >
                <ExternalLink className="size-3" />
                <span className="hidden sm:inline">Get key</span>
              </a>
            )}
          </div>
          <StatusBadge
            variant={isConfigured ? "success" : "neutral"}
            className="px-2 py-0.5"
          >
            {isConfigured ? t("status.connected") : t("status.notConfigured")}
          </StatusBadge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 px-4 pb-4 pt-0">
        {fields.map((field) => {
          const isEditing = editingField === field.name
          const displayValue = isEditing
            ? draftValues[field.name] ?? ""
            : field.value

          return (
            <div key={field.name} className="space-y-1.5">
              <Label
                htmlFor={`provider-${provider}-${field.name}`}
                className="text-xs text-muted-foreground"
              >
                {field.label}
              </Label>
              <div className="flex gap-2">
                <Input
                  id={`provider-${provider}-${field.name}`}
                  aria-label={`${label} ${field.label}`}
                  type={field.secret && !isEditing ? "password" : "text"}
                  value={displayValue}
                  placeholder={field.placeholder}
                  onFocus={() => handleFocus(field)}
                  onChange={(event) => updateDraft(field.name, event.target.value)}
                  onBlur={() => void handleBlur(field)}
                  onKeyDown={(event) => handleKeyDown(event, field)}
                  disabled={savingField === field.name}
                  className="flex-1 font-mono text-xs h-8"
                />
                {field.value && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                    onClick={() => void handleClearField(field)}
                    disabled={savingField === field.name}
                    title={
                      field.name === "api_key"
                        ? t("clearKey")
                        : t("clearValue", { field: field.label })
                    }
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </div>
          )
        })}

        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            className="h-8 shrink-0 text-xs"
            onClick={handleTest}
            disabled={!isConfigured || isTesting}
          >
            {isTesting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : testResult === "success" ? (
              <Check className="h-3.5 w-3.5 text-green-500" />
            ) : testResult === "error" ? (
              <X className="h-3.5 w-3.5 text-destructive" />
            ) : (
              t("testConnection")
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

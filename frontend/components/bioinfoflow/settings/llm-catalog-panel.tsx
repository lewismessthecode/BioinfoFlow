"use client"

import { useEffect, useMemo, useState } from "react"
import { CheckCircle2, ExternalLink, Loader2, RefreshCw } from "@/lib/icons"
import { useTranslations } from "next-intl"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useLlmCatalog } from "@/hooks/use-llm-catalog"
import { celebrateMilestone } from "@/lib/celebrations"
import type {
  LlmConfiguredProvider,
  LlmProviderTemplate,
  LlmProviderTemplateField,
} from "@/lib/llm"
import { cn } from "@/lib/utils"

type FieldValues = Record<string, Record<string, string>>

export function LlmCatalogPanel() {
  const t = useTranslations("settings")
  const {
    providerTemplates = [],
    configuredProviders,
    isLoading,
    isMutating,
    discoverModels,
    setupProvider,
  } = useLlmCatalog()
  const [fieldValues, setFieldValues] = useState<FieldValues>({})
  const [savingTemplateId, setSavingTemplateId] = useState<string | null>(null)
  const [refreshingModels, setRefreshingModels] = useState(false)

  const providersByTemplate = useMemo(() => {
    const byTemplate = new Map<string, LlmConfiguredProvider>()
    for (const template of providerTemplates) {
      const provider = configuredProviders.find((item) =>
        providerMatchesTemplate(item, template),
      )
      if (provider) byTemplate.set(template.id, provider)
    }
    return byTemplate
  }, [configuredProviders, providerTemplates])

  useEffect(() => {
    setFieldValues((current) => {
      let changed = false
      const next: FieldValues = { ...current }

      for (const template of providerTemplates) {
        const provider = providersByTemplate.get(template.id)
        const currentValues = next[template.id] ?? {}
        const templateValues = { ...currentValues }

        for (const field of template.fields) {
          if (templateValues[field.name] !== undefined) continue
          templateValues[field.name] = initialFieldValue(template, field, provider)
          changed = true
        }

        if (!next[template.id]) {
          next[template.id] = templateValues
          changed = true
        } else if (templateValues !== currentValues) {
          next[template.id] = templateValues
        }
      }

      return changed ? next : current
    })
  }, [providerTemplates, providersByTemplate])

  const setFieldValue = (
    templateId: string,
    fieldName: string,
    value: string,
  ) => {
    setFieldValues((current) => ({
      ...current,
      [templateId]: {
        ...(current[templateId] ?? {}),
        [fieldName]: value,
      },
    }))
  }

  const buildSetupInput = (
    template: LlmProviderTemplate,
    discover: boolean,
  ) => {
    const provider = providersByTemplate.get(template.id)
    const values = fieldValues[template.id] ?? {}
    return {
      templateId: template.id,
      providerId: provider?.id,
      name: provider?.name || template.name,
      baseUrl: readBaseUrl(template, provider, values),
      apiKey: (values.api_key ?? "").trim(),
      modelIds: cleanModelIds(values.model_id),
      discover,
      scope: "user" as const,
      enabled: true,
    }
  }

  const saveProvider = async (template: LlmProviderTemplate) => {
    setSavingTemplateId(template.id)
    try {
      const hadConfiguredProvider = configuredProviders.some(providerIsUsable)
      const setupInput = buildSetupInput(template, true)
      const result = await setupProvider(setupInput)
      if (!result) {
        toast.error(t("providerCards.saveFailed"))
        return
      }
      setFieldValue(template.id, "api_key", "")
      if (result.discovered && result.models.length > 0) {
        toast.success(
          t("providerCards.modelsDiscovered", { count: result.models.length }),
        )
      } else {
        toast.success(t("providerCards.saved"))
      }
      if (
        !hadConfiguredProvider &&
        setupInput.apiKey &&
        providerIsUsable(result.provider)
      ) {
        celebrateMilestone("first-provider-key")
      }
    } finally {
      setSavingTemplateId(null)
    }
  }

  const refreshModels = async () => {
    const providersToRefresh = providerTemplates
      .filter((template) => template.discovery !== "static")
      .map((template) => ({
        template,
        provider: providersByTemplate.get(template.id),
      }))
      .filter(
        (item): item is { template: LlmProviderTemplate; provider: LlmConfiguredProvider } =>
          providerConfigured(item.template, item.provider),
      )

    if (providersToRefresh.length === 0) return

    setRefreshingModels(true)
    try {
      let refreshed = 0
      let discovered = 0
      for (const { provider } of providersToRefresh) {
        const result = await discoverModels(provider.id)
        if (result) {
          refreshed += 1
          discovered += result.length
        }
      }
      if (refreshed === 0) {
        toast.error(t("providerCards.modelRefreshFailed"))
      } else {
        toast.success(t("providerCards.modelsDiscovered", { count: discovered }))
      }
    } finally {
      setRefreshingModels(false)
    }
  }

  const refreshableProviderCount = providerTemplates.filter((template) => {
    const provider = providersByTemplate.get(template.id)
    return template.discovery !== "static" && providerConfigured(template, provider)
  }).length

  return (
    <section className="space-y-4">
      <div className="flex min-h-9 items-center justify-between gap-3">
        {isLoading ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            {t("providerCards.loading")}
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">
            {t("providerCards.summary", {
              count: configuredProviders.filter(
                (provider) =>
                  provider.enabled &&
                  (provider.credential?.configured || provider.credential?.available),
              ).length,
            })}
          </div>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-9 gap-2 rounded-md"
          disabled={refreshableProviderCount === 0 || refreshingModels || isMutating}
          onClick={() => void refreshModels()}
        >
          {refreshingModels ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <RefreshCw className="size-3.5" />
          )}
          {refreshingModels
            ? t("providerCards.refreshingModels")
            : t("providerCards.refreshModels")}
        </Button>
      </div>

      <div className="overflow-hidden rounded-xl border border-border/70 bg-card">
        {providerTemplates.map((template) => {
          const provider = providersByTemplate.get(template.id)
          const values = fieldValues[template.id] ?? {}
          const configured = providerConfigured(template, provider)
          const note = credentialNote(t, provider)
          const saving = savingTemplateId === template.id
          const canSave =
            !saving && !isMutating && requiredFieldsReady(template, values, configured)

          return (
            <div
              key={template.id}
              role="group"
              aria-label={template.name}
              className="grid gap-4 border-b border-border/60 px-4 py-4 last:border-b-0 sm:px-5 lg:grid-cols-[minmax(180px,1fr)_minmax(420px,1.35fr)] lg:items-start"
            >
              <div className="min-w-0 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="truncate text-sm font-semibold leading-6 text-foreground">
                    {template.name}
                  </h4>
                  <span
                    className={cn(
                      "inline-flex h-6 shrink-0 items-center rounded-md border px-2 text-xs font-medium",
                      configured
                        ? "border-border bg-secondary/45 text-foreground"
                        : "border-border bg-muted text-muted-foreground",
                    )}
                  >
                    {configured ? <CheckCircle2 className="mr-1 size-3.5" /> : null}
                    {configured ? t("providerCards.ready") : t("providerCards.needsSetup")}
                  </span>
                </div>
                {note ? (
                  <p className="text-[13px] leading-5 text-muted-foreground">
                    {note}
                  </p>
                ) : null}
              </div>

              <div className="min-w-0 space-y-3 lg:justify-self-end">
                <div className="grid gap-2 sm:grid-cols-2">
                  {template.fields.map((field) => (
                    <Input
                      key={field.name}
                      aria-label={`${template.name} ${fieldAriaLabel(field)}`}
                      type={field.secret ? "password" : "text"}
                      value={values[field.name] ?? ""}
                      onChange={(event) =>
                        setFieldValue(template.id, field.name, event.target.value)
                      }
                      placeholder={placeholderForField(t, field, configured)}
                      className="h-10 rounded-md"
                    />
                  ))}
                </div>

                <div className="flex flex-wrap items-center gap-3 sm:justify-end">
                  <a
                    href={template.docs_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {t("providerCards.getApiKey", { provider: template.name })}
                    <ExternalLink className="size-3 shrink-0" />
                  </a>
                  <Button
                    type="button"
                    size="sm"
                    className="h-9 rounded-md px-4"
                    disabled={!canSave}
                    onClick={() => void saveProvider(template)}
                  >
                    {saving ? t("providerCards.saving") : t("providerCards.save")}
                  </Button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function providerMatchesTemplate(
  provider: LlmConfiguredProvider,
  template: LlmProviderTemplate,
) {
  const providerTemplate = String(provider.metadata?.providerTemplate ?? "")
  if (providerTemplate) return providerTemplate === template.id
  return provider.kind === template.kind
}

function initialFieldValue(
  template: LlmProviderTemplate,
  field: LlmProviderTemplateField,
  provider?: LlmConfiguredProvider,
) {
  if (field.name === "base_url") {
    return provider?.base_url ?? field.default ?? template.default_base_url ?? ""
  }
  return field.default ?? ""
}

function apiKeyRequired(template: LlmProviderTemplate) {
  return Boolean(
    template.fields.find((field) => field.name === "api_key")?.required,
  )
}

function providerConfigured(
  template: LlmProviderTemplate,
  provider?: LlmConfiguredProvider,
) {
  if (!provider?.enabled) return false
  if (provider.credential?.configured || provider.credential?.available) return true
  return !apiKeyRequired(template) && provider.credential?.source === "none"
}

function providerIsUsable(provider: LlmConfiguredProvider) {
  return Boolean(
    provider.enabled &&
      (provider.credential?.configured || provider.credential?.available),
  )
}

function credentialNote(
  t: ReturnType<typeof useTranslations>,
  provider?: LlmConfiguredProvider,
) {
  const credential = provider?.credential
  if (!credential) return ""
  // Only annotate a card once the credential is actually usable. An env var
  // that is recorded but empty/unset must not read as "From .env".
  if (!(credential.configured || credential.available)) return ""
  if (credential.source === "env") return t("providerCards.fromEnv")
  if (credential.source === "stored") return t("providerCards.keySavedShort")
  return credential.masked_hint ?? credential.fingerprint ?? ""
}

function readBaseUrl(
  template: LlmProviderTemplate,
  provider: LlmConfiguredProvider | undefined,
  values: Record<string, string>,
) {
  return (
    (values.base_url ?? "").trim() ||
    provider?.base_url ||
    template.default_base_url ||
    null
  )
}

function requiredFieldsReady(
  template: LlmProviderTemplate,
  values: Record<string, string>,
  configured: boolean,
) {
  return template.fields.every((field) => {
    if (!field.required) return true
    if (field.name === "api_key" && configured) return true
    return (values[field.name] ?? field.default ?? "").trim().length > 0
  })
}

function cleanModelIds(value: string | undefined) {
  return (value ?? "")
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function placeholderForField(
  t: ReturnType<typeof useTranslations>,
  field: LlmProviderTemplateField,
  configured: boolean,
) {
  if (field.name === "api_key") {
    return configured
      ? t("providerCards.savedKeyPlaceholder")
      : t("providerCards.apiKeyPlaceholder")
  }
  if (field.name === "base_url") return t("providerCards.endpointPlaceholder")
  if (field.name === "model_id") return t("providerCards.modelIdPlaceholder")
  return field.placeholder
}

function fieldAriaLabel(field: LlmProviderTemplateField) {
  if (field.name === "api_key") return "API key"
  if (field.name === "base_url") return "endpoint"
  if (field.name === "model_id") return "model id"
  return field.label
}

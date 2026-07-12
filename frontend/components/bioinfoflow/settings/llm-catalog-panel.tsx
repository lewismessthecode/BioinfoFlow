"use client"

import { useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Loader2,
  RefreshCw,
  ShieldAlert,
} from "@/lib/icons"
import { useTranslations } from "next-intl"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  useLlmCatalog,
  type SetupProviderOutcome,
} from "@/hooks/use-llm-catalog"
import { celebrateMilestone } from "@/lib/celebrations"
import type {
  LlmConfiguredProvider,
  LlmProviderTemplate,
  LlmProviderTemplateField,
} from "@/lib/llm"
import { cn } from "@/lib/utils"

type FieldValues = Record<string, Record<string, string>>
type ToggleValues = Record<string, boolean>
type RowErrors = Record<string, string>
type SettingsTranslations = ReturnType<typeof useTranslations>

const SKELETON_ROWS = [0, 1, 2, 3]
const INTERNAL_HOST_SUFFIXES = [
  ".local",
  ".internal",
  ".intranet",
  ".lan",
  ".home",
  ".home.arpa",
  ".corp",
  ".svc",
  ".test",
]

export function LlmCatalogPanel() {
  const t = useTranslations("settings")
  const {
    providerTemplates = [],
    configuredProviders,
    isLoading,
    isMutating,
    error,
    refresh,
    discoverModels,
    setupProvider,
  } = useLlmCatalog()
  const [fieldValues, setFieldValues] = useState<FieldValues>({})
  const [insecureHttpValues, setInsecureHttpValues] = useState<ToggleValues>({})
  const [rowErrors, setRowErrors] = useState<RowErrors>({})
  const [savingTemplateIds, setSavingTemplateIds] = useState<Set<string>>(
    () => new Set(),
  )
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
        } else if (changed) {
          next[template.id] = templateValues
        }
      }

      return changed ? next : current
    })

    setInsecureHttpValues((current) => {
      let changed = false
      const next = { ...current }
      for (const template of providerTemplates) {
        if (next[template.id] !== undefined) continue
        next[template.id] = Boolean(
          providersByTemplate.get(template.id)?.allow_insecure_http,
        )
        changed = true
      }
      return changed ? next : current
    })
  }, [providerTemplates, providersByTemplate])

  const clearRowError = (templateId: string) => {
    setRowErrors((current) => {
      if (!current[templateId]) return current
      const next = { ...current }
      delete next[templateId]
      return next
    })
  }

  const setFieldValue = (
    templateId: string,
    fieldName: string,
    value: string,
  ) => {
    clearRowError(templateId)
    setFieldValues((current) => ({
      ...current,
      [templateId]: {
        ...(current[templateId] ?? {}),
        [fieldName]: value,
      },
    }))
  }

  const setAllowInsecureHttp = (templateId: string, allowed: boolean) => {
    clearRowError(templateId)
    setInsecureHttpValues((current) => ({
      ...current,
      [templateId]: allowed,
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
      allowInsecureHttp: Boolean(insecureHttpValues[template.id]),
    }
  }

  const saveProvider = async (template: LlmProviderTemplate) => {
    setSavingTemplateIds((current) => {
      const next = new Set(current)
      next.add(template.id)
      return next
    })
    clearRowError(template.id)
    try {
      const hadConfiguredProvider = configuredProviders.some(providerIsUsable)
      const setupInput = buildSetupInput(template, true)
      const outcome: SetupProviderOutcome = await setupProvider(setupInput)
      if (!outcome.ok) {
        setRowErrors((current) => ({
          ...current,
          [template.id]: outcome.error.message,
        }))
        toast.error(outcome.error.message || t("providerCards.saveFailed"))
        return
      }

      const result = outcome.result
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
      setSavingTemplateIds((current) => {
        const next = new Set(current)
        next.delete(template.id)
        return next
      })
    }
  }

  const refreshModels = async () => {
    const providersToRefresh = providerTemplates
      .map((template) => ({
        template,
        provider: providersByTemplate.get(template.id),
      }))
      .filter(
        (
          item,
        ): item is {
          template: LlmProviderTemplate
          provider: LlmConfiguredProvider
        } =>
          item.template.discovery !== "static" &&
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

  const refreshableProviderCount = providerTemplates.reduce((count, template) => {
    const provider = providersByTemplate.get(template.id)
    return template.discovery !== "static" && providerConfigured(template, provider)
      ? count + 1
      : count
  }, 0)
  const configuredCount = configuredProviders.reduce(
    (count, provider) =>
      provider.enabled &&
      (provider.credential?.configured || provider.credential?.available)
        ? count + 1
        : count,
    0,
  )

  return (
    <section className="space-y-3">
      <div className="flex min-h-9 items-center justify-between gap-3">
        <div className="text-xs font-medium text-muted-foreground tabular-nums">
          {isLoading
            ? t("providerCards.loading")
            : t("providerCards.summary", { count: configuredCount })}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 gap-1.5 rounded-md border-border/70 bg-background px-2.5 shadow-none"
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

      {isLoading ? <ProviderCatalogSkeleton /> : null}
      {!isLoading && error && providerTemplates.length === 0 ? (
        <ProviderCatalogError t={t} onRetry={() => void refresh()} />
      ) : null}
      {!isLoading && providerTemplates.length > 0 ? (
        <div className="space-y-2">
          {providerTemplates.map((template) => {
            const provider = providersByTemplate.get(template.id)
            const values = fieldValues[template.id] ?? {}
            return (
              <ProviderCard
                key={template.id}
                t={t}
                template={template}
                provider={provider}
                values={values}
                insecureHttpAllowed={Boolean(insecureHttpValues[template.id])}
                error={rowErrors[template.id]}
                saving={savingTemplateIds.has(template.id)}
                onFieldChange={(fieldName, value) =>
                  setFieldValue(template.id, fieldName, value)
                }
                onInsecureHttpChange={(allowed) =>
                  setAllowInsecureHttp(template.id, allowed)
                }
                onSave={() => void saveProvider(template)}
              />
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

type ProviderCardProps = {
  t: SettingsTranslations
  template: LlmProviderTemplate
  provider?: LlmConfiguredProvider
  values: Record<string, string>
  insecureHttpAllowed: boolean
  error?: string
  saving: boolean
  onFieldChange: (fieldName: string, value: string) => void
  onInsecureHttpChange: (allowed: boolean) => void
  onSave: () => void
}

function ProviderCard({
  t,
  template,
  provider,
  values,
  insecureHttpAllowed,
  error,
  saving,
  onFieldChange,
  onInsecureHttpChange,
  onSave,
}: ProviderCardProps) {
  const configured = providerConfigured(template, provider)
  const note = credentialNote(t, provider)
  const endpoint = readBaseUrl(template, provider, values) ?? ""
  const publicPlainHttp = isPublicPlainHttpEndpoint(endpoint)
  const savedInsecureTransport = Boolean(
    provider?.allow_insecure_http && isPublicPlainHttpEndpoint(provider.base_url ?? ""),
  )
  const canSave = !saving && requiredFieldsReady(template, values, configured)
  const fieldCount = template.fields.length

  return (
    <article
      role="group"
      aria-label={template.name}
      className="rounded-[10px] border border-border/70 bg-card px-4 py-3.5 transition-colors hover:border-border sm:px-5"
    >
      <header className="mb-3 flex min-w-0 items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="truncate text-[15px] font-semibold tracking-[-0.01em] text-foreground">
              {template.name}
            </h4>
            <ProviderStatus configured={configured} t={t} />
            {savedInsecureTransport ? (
              <div className="inline-flex items-center gap-1.5 rounded-md bg-[#FBF3DB] px-2 py-1 text-[11px] font-medium text-[#7A5A10]">
                <ShieldAlert className="size-3.5" />
                {t("providerCards.insecureHttpEnabled")}
              </div>
            ) : null}
          </div>
          {note ? (
            <p className="mt-1 text-xs leading-4 text-muted-foreground">{note}</p>
          ) : null}
        </div>
        <a
          href={template.docs_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
        >
          {t("providerCards.getApiKey", { provider: template.name })}
          <ExternalLink className="size-3 shrink-0" />
        </a>
      </header>

      <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-end">
        <div
          className={cn(
            "grid min-w-0 flex-1 gap-3",
            fieldCount === 2 && "sm:grid-cols-2",
            fieldCount >= 3 && "sm:grid-cols-2 xl:grid-cols-3",
          )}
        >
          {template.fields.map((field) => (
            <ProviderField
              key={field.name}
              t={t}
              template={template}
              field={field}
              configured={configured}
              value={values[field.name] ?? ""}
              onChange={(value) => onFieldChange(field.name, value)}
            />
          ))}
        </div>
        <Button
          type="button"
          size="sm"
          className="h-9 w-full shrink-0 rounded-md bg-[#111111] px-4 text-white shadow-none hover:bg-[#2F3437] md:w-28"
          disabled={!canSave}
          onClick={onSave}
        >
          {saving ? t("providerCards.saving") : t("providerCards.save")}
        </Button>
      </div>

      {publicPlainHttp ? (
        <div className="mt-3">
          <InsecureHttpNotice
            t={t}
            checked={insecureHttpAllowed}
            onCheckedChange={onInsecureHttpChange}
          />
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="mt-3 flex items-start gap-2 rounded-lg border border-[#F4D6D7] bg-[#FDEBEC] px-3 py-2.5 text-xs leading-5 text-[#9F2F2D]"
        >
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <span className="text-pretty">{error}</span>
        </div>
      ) : null}
    </article>
  )
}

function ProviderStatus({
  configured,
  t,
}: {
  configured: boolean
  t: SettingsTranslations
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center rounded-md border px-2 text-[11px] font-medium tracking-[0.02em]",
        configured
          ? "border-[#DDE8DB] bg-[#EDF3EC] text-[#346538]"
          : "border-border/70 bg-[#F7F6F3] text-muted-foreground",
      )}
    >
      {configured ? <CheckCircle2 className="mr-1 size-3.5" /> : null}
      {configured ? t("providerCards.ready") : t("providerCards.needsSetup")}
    </span>
  )
}

type ProviderFieldProps = {
  t: SettingsTranslations
  template: LlmProviderTemplate
  field: LlmProviderTemplateField
  configured: boolean
  value: string
  onChange: (value: string) => void
}

function ProviderField({
  t,
  template,
  field,
  configured,
  value,
  onChange,
}: ProviderFieldProps) {
  const inputId = `provider-${template.id}-${field.name}`
  return (
    <div className="min-w-0 space-y-1.5">
      <Label
        htmlFor={inputId}
        className="text-[11px] font-medium tracking-[0.02em] text-muted-foreground"
      >
        {fieldLabel(t, field)}
      </Label>
      <Input
        id={inputId}
        aria-label={`${template.name} ${fieldAriaLabel(field)}`}
        type={field.secret ? "password" : "text"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholderForField(t, field, configured)}
        className="h-9 rounded-md border-border/80 bg-background px-3 text-sm shadow-none"
      />
    </div>
  )
}

function InsecureHttpNotice({
  t,
  checked,
  onCheckedChange,
}: {
  t: SettingsTranslations
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  const label = t("providerCards.allowInsecureHttp")
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 rounded-lg border px-3 py-2.5 transition-colors",
        checked
          ? "border-[#D8C57E] bg-[#FBF3DB] text-[#694D0B]"
          : "border-border/70 bg-[#F7F6F3] text-foreground",
      )}
    >
      <div className="flex min-w-0 items-start gap-2.5">
        <ShieldAlert
          className={cn(
            "mt-0.5 size-4 shrink-0",
            checked ? "text-[#956400]" : "text-muted-foreground",
          )}
        />
        <div className="min-w-0">
          <p className="text-xs font-semibold">{label}</p>
          <p
            className={cn(
              "mt-0.5 text-pretty text-[11px] leading-4",
              checked ? "text-[#7A5A10]" : "text-muted-foreground",
            )}
          >
            {t("providerCards.insecureHttpDescription")}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2.5">
        <span
          className={cn(
            "min-w-8 text-right text-[11px] font-semibold",
            checked ? "text-[#7A5A10]" : "text-muted-foreground",
          )}
        >
          {checked
            ? t("providerCards.insecureHttpOn")
            : t("providerCards.insecureHttpOff")}
        </span>
        <Switch
          aria-label={label}
          checked={checked}
          onCheckedChange={onCheckedChange}
          className="h-6 w-11 border border-[#D7D3C8] bg-[#E7E3D8] data-[state=checked]:border-[#956400] data-[state=checked]:bg-[#956400] [&_[data-slot=switch-thumb]]:size-5 [&_[data-slot=switch-thumb]]:bg-white"
        />
      </div>
    </div>
  )
}

function ProviderCatalogSkeleton() {
  return (
    <div className="space-y-2" aria-hidden="true">
      {SKELETON_ROWS.map((row) => (
        <div
          key={row}
          data-testid="provider-card-skeleton"
          className="rounded-[10px] border border-border/60 bg-card px-5 py-3.5"
        >
          <div className="mb-3 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-5 w-12" />
            </div>
            <Skeleton className="h-5 w-16" />
          </div>
          <div className="flex flex-col gap-3 md:flex-row md:items-end">
            <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
            <Skeleton className="h-9 w-full md:w-28" />
          </div>
        </div>
      ))}
    </div>
  )
}

function ProviderCatalogError({
  t,
  onRetry,
}: {
  t: SettingsTranslations
  onRetry: () => void
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-[10px] border border-[#F4D6D7] bg-[#FDEBEC] px-4 py-3 text-[#9F2F2D]">
      <div className="flex items-center gap-2.5">
        <AlertTriangle className="size-4 shrink-0" />
        <p className="text-sm font-medium">{t("providerCards.loadFailed")}</p>
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-8 rounded-md border-[#E6BFC0] bg-transparent shadow-none hover:bg-white/45"
        onClick={onRetry}
      >
        <RefreshCw className="size-3.5" />
        {t("providerCards.retry")}
      </Button>
    </div>
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
  t: SettingsTranslations,
  provider?: LlmConfiguredProvider,
) {
  const credential = provider?.credential
  if (!credential) return ""
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
  t: SettingsTranslations,
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

function fieldLabel(t: SettingsTranslations, field: LlmProviderTemplateField) {
  if (field.name === "api_key") return t("providerCards.apiKeyLabel")
  if (field.name === "base_url") return t("providerCards.endpointLabel")
  if (field.name === "model_id") return t("providerCards.modelIdLabel")
  return field.label
}

function fieldAriaLabel(field: LlmProviderTemplateField) {
  if (field.name === "api_key") return "API key"
  if (field.name === "base_url") return "endpoint"
  if (field.name === "model_id") return "model id"
  return field.label
}

function isPublicPlainHttpEndpoint(value: string) {
  const trimmed = value.trim()
  if (!trimmed.toLowerCase().startsWith("http://")) return false
  try {
    const hostname = new URL(trimmed).hostname.replace(/^\[|\]$/g, "").toLowerCase()
    if (!hostname) return false
    if (hostname === "localhost" || hostname === "::1") return false
    if (hostname.endsWith(".localhost")) return false
    if (hostname.includes(":")) return !isPrivateIpv6(hostname)
    if (!hostname.includes(".") && !/^\d+$/.test(hostname)) return false
    if (INTERNAL_HOST_SUFFIXES.some((suffix) => hostname.endsWith(suffix))) {
      return false
    }
    if (isPrivateIpv4(hostname)) return false
    return true
  } catch {
    return false
  }
}

function isPrivateIpv6(hostname: string) {
  const normalized = hostname.split("%")[0]
  if (normalized === "::" || normalized === "::1") return true

  const mappedIpv4 = normalized.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/)
  if (mappedIpv4) return isPrivateIpv4(mappedIpv4[1])

  const firstHextet = Number.parseInt(normalized.split(":", 1)[0] || "0", 16)
  if (!Number.isInteger(firstHextet)) return false
  return (
    (firstHextet & 0xfe00) === 0xfc00 ||
    (firstHextet & 0xffc0) === 0xfe80 ||
    normalized.startsWith("2001:db8:")
  )
}

function isPrivateIpv4(hostname: string) {
  const octets = hostname.split(".").map(Number)
  if (octets.length !== 4 || octets.some((octet) => !Number.isInteger(octet))) {
    return false
  }
  const [first, second] = octets
  if (octets.some((octet) => octet < 0 || octet > 255)) return false
  return (
    first === 10 ||
    first === 127 ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168)
  )
}

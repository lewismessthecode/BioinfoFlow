"use client"

import { useEffect, useMemo, useRef, useState } from "react"
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
  LlmModel,
  LlmProviderTemplate,
  LlmProviderTemplateField,
  LlmProviderTestResult,
  LlmWireProtocol,
} from "@/lib/llm"
import { cn } from "@/lib/utils"

type FieldValues = Record<string, Record<string, string>>
type ToggleValues = Record<string, boolean>
type RowErrors = Record<string, string>
type ProtocolValues = Record<string, LlmWireProtocol>
type ProbeResults = Record<string, LlmProviderTestResult>
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
    models = [],
    isLoading,
    isMutating,
    error,
    refresh,
    discoverModels,
    setupProvider,
    testProvider,
  } = useLlmCatalog()
  const [fieldValues, setFieldValues] = useState<FieldValues>({})
  const [insecureHttpValues, setInsecureHttpValues] = useState<ToggleValues>({})
  const [protocolValues, setProtocolValues] = useState<ProtocolValues>({})
  const [selectedTestModelIds, setSelectedTestModelIds] = useState<FieldValues>({})
  const [probeResults, setProbeResults] = useState<ProbeResults>({})
  const [rowErrors, setRowErrors] = useState<RowErrors>({})
  const [savingTemplateIds, setSavingTemplateIds] = useState<Set<string>>(
    () => new Set(),
  )
  const [refreshingModels, setRefreshingModels] = useState(false)
  const [testingTemplateIds, setTestingTemplateIds] = useState<Set<string>>(
    () => new Set(),
  )
  const [dirtyTemplateIds, setDirtyTemplateIds] = useState<Set<string>>(
    () => new Set(),
  )
  const probeRevisionByTemplate = useRef<Record<string, number>>({})

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

    setProtocolValues((current) => {
      let changed = false
      const next = { ...current }
      for (const template of providerTemplates) {
        if (next[template.id] !== undefined) continue
        next[template.id] =
          providersByTemplate.get(template.id)?.wire_protocol ??
          template.default_wire_protocol ??
          "chat_completions"
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

  const invalidateProbeResult = (templateId: string) => {
    probeRevisionByTemplate.current[templateId] =
      (probeRevisionByTemplate.current[templateId] ?? 0) + 1
    setProbeResults((current) => {
      if (!current[templateId]) return current
      const next = { ...current }
      delete next[templateId]
      return next
    })
  }

  const markTemplateDirty = (templateId: string) => {
    invalidateProbeResult(templateId)
    setDirtyTemplateIds((current) => new Set(current).add(templateId))
  }

  const setFieldValue = (
    templateId: string,
    fieldName: string,
    value: string,
    markDirty = true,
  ) => {
    clearRowError(templateId)
    setFieldValues((current) => ({
      ...current,
      [templateId]: {
        ...(current[templateId] ?? {}),
        [fieldName]: value,
      },
    }))
    if (markDirty) markTemplateDirty(templateId)
  }

  const setAllowInsecureHttp = (templateId: string, allowed: boolean) => {
    clearRowError(templateId)
    setInsecureHttpValues((current) => ({
      ...current,
      [templateId]: allowed,
    }))
    markTemplateDirty(templateId)
  }

  const setWireProtocol = (
    templateId: string,
    wireProtocol: LlmWireProtocol,
  ) => {
    clearRowError(templateId)
    setProtocolValues((current) => ({
      ...current,
      [templateId]: wireProtocol,
    }))
    markTemplateDirty(templateId)
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
      wireProtocol:
        protocolValues[template.id] ??
        provider?.wire_protocol ??
        template.default_wire_protocol ??
        "chat_completions",
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
    invalidateProbeResult(template.id)
    try {
      const hadConfiguredProvider = configuredProviders.some(providerIsUsable)
      const setupInput = buildSetupInput(template, false)
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
      setDirtyTemplateIds((current) => {
        const next = new Set(current)
        next.delete(template.id)
        return next
      })
      setFieldValue(template.id, "api_key", "", false)
      const shouldDiscoverModels =
        setupInput.modelIds.length === 0 && template.discovery !== "static"
      const discoveredModels = shouldDiscoverModels
        ? await discoverModels(result.provider.id)
        : null
      if (shouldDiscoverModels && discoveredModels === null) {
        toast.warning(t("providerCards.savedDiscoveryFailed"))
      } else if (shouldDiscoverModels && discoveredModels?.length === 0) {
        toast.warning(t("providerCards.savedNoModels"))
      } else if (discoveredModels && discoveredModels.length > 0) {
        toast.success(
          t("providerCards.modelsDiscovered", { count: discoveredModels.length }),
        )
      } else if (result.discovered && result.models.length > 0) {
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

  const testConfiguredProvider = async (
    template: LlmProviderTemplate,
    provider: LlmConfiguredProvider,
    providerModels: LlmModel[],
  ) => {
    const selectedModelId =
      selectedTestModelIds[template.id]?.model_id ?? providerModels[0]?.id
    if (!selectedModelId) return
    setTestingTemplateIds((current) => new Set(current).add(template.id))
    clearRowError(template.id)
    const probeRevision = probeRevisionByTemplate.current[template.id] ?? 0
    try {
      const result = await testProvider(provider.id, selectedModelId)
      if ((probeRevisionByTemplate.current[template.id] ?? 0) !== probeRevision) {
        return
      }
      if (result) {
        setProbeResults((current) => ({
          ...current,
          [template.id]: result,
        }))
      } else {
        const message = t("providerCards.testRequestFailed")
        setRowErrors((current) => ({ ...current, [template.id]: message }))
        toast.error(message)
      }
    } finally {
      setTestingTemplateIds((current) => {
        const next = new Set(current)
        next.delete(template.id)
        return next
      })
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
            const providerModels = provider
              ? models.filter((model) => model.provider_id === provider.id)
              : []
            const selectedTestModelId =
              selectedTestModelIds[template.id]?.model_id ??
              providerModels[0]?.id ??
              ""
            const candidateProbeResult = dirtyTemplateIds.has(template.id)
              ? undefined
              : probeResults[template.id] ?? providerProbeResult(provider)
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
                testing={testingTemplateIds.has(template.id)}
                wireProtocol={
                  protocolValues[template.id] ??
                  provider?.wire_protocol ??
                  template.default_wire_protocol ??
                  "chat_completions"
                }
                providerModels={providerModels}
                selectedTestModelId={selectedTestModelId}
                probeResult={probeResultForSelectedModel(
                  candidateProbeResult,
                  providerModels,
                  selectedTestModelId,
                )}
                settingsDirty={dirtyTemplateIds.has(template.id)}
                onFieldChange={(fieldName, value) =>
                  setFieldValue(template.id, fieldName, value)
                }
                onInsecureHttpChange={(allowed) =>
                  setAllowInsecureHttp(template.id, allowed)
                }
                onWireProtocolChange={(wireProtocol) =>
                  setWireProtocol(template.id, wireProtocol)
                }
                onTestModelChange={(modelId) => {
                  invalidateProbeResult(template.id)
                  setSelectedTestModelIds((current) => ({
                    ...current,
                    [template.id]: { model_id: modelId },
                  }))
                }}
                onTest={() => {
                  if (provider) {
                    void testConfiguredProvider(template, provider, providerModels)
                  }
                }}
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
  testing: boolean
  wireProtocol: LlmWireProtocol
  providerModels: LlmModel[]
  selectedTestModelId: string
  probeResult?: LlmProviderTestResult
  settingsDirty: boolean
  onFieldChange: (fieldName: string, value: string) => void
  onInsecureHttpChange: (allowed: boolean) => void
  onWireProtocolChange: (wireProtocol: LlmWireProtocol) => void
  onTestModelChange: (modelId: string) => void
  onTest: () => void
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
  testing,
  wireProtocol,
  providerModels,
  selectedTestModelId,
  probeResult,
  settingsDirty,
  onFieldChange,
  onInsecureHttpChange,
  onWireProtocolChange,
  onTestModelChange,
  onTest,
  onSave,
}: ProviderCardProps) {
  const configured = providerConfigured(template, provider)
  const note = credentialNote(t, provider)
  const endpoint = readBaseUrl(template, provider, values) ?? ""
  const publicPlainHttp = isPublicPlainHttpEndpoint(endpoint)
  const savedInsecureTransport = Boolean(
    provider?.allow_insecure_http && isPublicPlainHttpEndpoint(provider.base_url ?? ""),
  )
  const canSave =
    !saving &&
    requiredFieldsReady(template, values, configured) &&
    (!publicPlainHttp || insecureHttpAllowed)
  const supportedProtocols = templateWireProtocols(template)
  const multipleProtocols = supportedProtocols.length > 1
  const fieldCount = template.fields.length + (multipleProtocols ? 1 : 0)

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
          {multipleProtocols ? (
            <ProtocolField
              t={t}
              template={template}
              protocols={supportedProtocols}
              value={wireProtocol}
              onChange={onWireProtocolChange}
            />
          ) : null}
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

      {provider && configured ? (
        <ProviderProbeControls
          t={t}
          template={template}
          models={providerModels}
          selectedModelId={selectedTestModelId}
          result={probeResult}
          settingsDirty={settingsDirty}
          testing={testing}
          onModelChange={onTestModelChange}
          onTest={onTest}
        />
      ) : null}

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

function ProtocolField({
  t,
  template,
  protocols,
  value,
  onChange,
}: {
  t: SettingsTranslations
  template: LlmProviderTemplate
  protocols: LlmWireProtocol[]
  value: LlmWireProtocol
  onChange: (value: LlmWireProtocol) => void
}) {
  const inputId = `provider-${template.id}-wire-protocol`
  return (
    <div className="min-w-0 space-y-1.5">
      <Label
        htmlFor={inputId}
        className="text-[11px] font-medium tracking-[0.02em] text-muted-foreground"
      >
        {t("providerCards.protocolLabel")}
      </Label>
      <select
        id={inputId}
        aria-label={t("providerCards.protocolAriaLabel", {
          provider: template.name,
        })}
        value={value}
        onChange={(event) => onChange(event.target.value as LlmWireProtocol)}
        className="h-9 w-full rounded-md border border-border/80 bg-background px-3 text-sm text-foreground shadow-none outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        {protocols.map((protocol) => (
          <option key={protocol} value={protocol}>
            {protocolLabel(t, protocol)}
          </option>
        ))}
      </select>
    </div>
  )
}

function ProviderProbeControls({
  t,
  template,
  models,
  selectedModelId,
  result,
  settingsDirty,
  testing,
  onModelChange,
  onTest,
}: {
  t: SettingsTranslations
  template: LlmProviderTemplate
  models: LlmModel[]
  selectedModelId: string
  result?: LlmProviderTestResult
  settingsDirty: boolean
  testing: boolean
  onModelChange: (modelId: string) => void
  onTest: () => void
}) {
  const selectId = `provider-${template.id}-test-model`
  return (
    <div className="mt-3 flex flex-col gap-2 border-t border-border/60 pt-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 flex-1 items-end gap-2">
        <div className="min-w-0 flex-1 sm:max-w-72">
          <Label
            htmlFor={selectId}
            className="mb-1.5 block text-[11px] font-medium tracking-[0.02em] text-muted-foreground"
          >
            {t("providerCards.testModelLabel")}
          </Label>
          <select
            id={selectId}
            aria-label={t("providerCards.testModelAriaLabel", {
              provider: template.name,
            })}
            value={selectedModelId}
            disabled={models.length === 0 || testing}
            onChange={(event) => onModelChange(event.target.value)}
            className="h-8 w-full rounded-md border border-border/80 bg-background px-2.5 text-xs text-foreground shadow-none outline-none disabled:opacity-50 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {models.length === 0 ? (
              <option value="">{t("providerCards.noTestModels")}</option>
            ) : null}
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.display_name || model.model_id}
              </option>
            ))}
          </select>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 shrink-0 rounded-md border-border/80 bg-background px-3 shadow-none"
          disabled={models.length === 0 || testing || settingsDirty}
          onClick={onTest}
        >
          {testing ? <Loader2 className="size-3.5 animate-spin" /> : null}
          {testing ? t("providerCards.testing") : t("providerCards.test")}
        </Button>
      </div>
      {settingsDirty ? (
        <div
          role="status"
          className="rounded-md border border-[#E8D9A7] bg-[#FBF3DB] px-2.5 py-1.5 text-[11px] font-medium leading-4 text-[#7A5A10]"
        >
          {t("providerCards.settingsChanged")}
        </div>
      ) : result ? (
        <ProviderProbeStatus t={t} result={result} />
      ) : null}
    </div>
  )
}

function ProviderProbeStatus({
  t,
  result,
}: {
  t: SettingsTranslations
  result: LlmProviderTestResult
}) {
  return (
    <div
      role={result.success ? "status" : "alert"}
      className={cn(
        "flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-2.5 py-1.5 text-[11px] leading-4",
        result.success
          ? "border-[#DDE8DB] bg-[#EDF3EC] text-[#346538]"
          : "border-[#F4D6D7] bg-[#FDEBEC] text-[#9F2F2D]",
      )}
    >
      <span className="font-semibold">
        {result.success
          ? t("providerCards.testSucceeded")
          : t("providerCards.testFailed")}
      </span>
      <span>{protocolLabel(t, result.wire_protocol)}</span>
      {result.model ? <span>{result.model}</span> : null}
      {result.latency_ms !== null && result.latency_ms !== undefined ? (
        <span className="tabular-nums">{result.latency_ms} ms</span>
      ) : null}
      {!result.success && result.error ? (
        <span className="text-pretty">{result.error}</span>
      ) : null}
      {!result.success && result.retryable ? (
        <span className="font-semibold">{t("providerCards.retryable")}</span>
      ) : null}
    </div>
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
  const helpText = null
  const helpId = helpText ? `${inputId}-help` : undefined
  return (
    <div className="min-w-0 space-y-1.5">
      <Label
        htmlFor={inputId}
        className="text-[11px] font-medium tracking-[0.02em] text-muted-foreground"
      >
        {fieldLabel(t, template, field)}
      </Label>
      <Input
        id={inputId}
        aria-label={`${template.name} ${fieldAriaLabel(field)}`}
        aria-describedby={helpId}
        type={field.secret ? "password" : "text"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholderForField(t, template, field, configured)}
        className="h-9 rounded-md border-border/80 bg-background px-3 text-sm shadow-none"
      />
      {helpText ? (
        <p id={helpId} className="text-pretty text-[11px] leading-4 text-muted-foreground">
          {helpText}
        </p>
      ) : null}
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

function providerProbeResult(
  provider?: LlmConfiguredProvider,
): LlmProviderTestResult | undefined {
  const status = provider?.test_status
  if (!provider || !status || typeof status.success !== "boolean") return undefined
  const wireProtocol = status.wire_protocol
  if (wireProtocol !== "chat_completions" && wireProtocol !== "responses") {
    return undefined
  }
  return {
    provider_id: provider.id,
    success: status.success,
    model: typeof status.model === "string" ? status.model : null,
    wire_protocol: wireProtocol,
    error_code:
      typeof status.error_code === "string" ? status.error_code : null,
    error:
      typeof status.error === "string"
        ? status.error
        : typeof status.error_message === "string"
          ? status.error_message
          : null,
    latency_ms:
      typeof status.latency_ms === "number" ? status.latency_ms : null,
    retryable: status.retryable === true,
    http_status:
      typeof status.http_status === "number" ? status.http_status : null,
    provider_code:
      typeof status.provider_code === "string" ? status.provider_code : null,
  }
}

function probeResultForSelectedModel(
  result: LlmProviderTestResult | undefined,
  models: LlmModel[],
  selectedModelId: string,
): LlmProviderTestResult | undefined {
  if (!result) return undefined
  const selectedModel = models.find((model) => model.id === selectedModelId)
  if (!selectedModel) return result.model ? undefined : result
  return result.model === selectedModel.model_id ? result : undefined
}

function protocolLabel(
  t: SettingsTranslations,
  protocol: LlmWireProtocol,
) {
  return protocol === "responses"
    ? t("providerCards.protocolResponses")
    : t("providerCards.protocolChat")
}

function templateWireProtocols(
  template: LlmProviderTemplate,
): LlmWireProtocol[] {
  return template.supported_wire_protocols?.length
    ? template.supported_wire_protocols
    : [template.default_wire_protocol ?? "chat_completions"]
}

function readBaseUrl(
  template: LlmProviderTemplate,
  provider: LlmConfiguredProvider | undefined,
  values: Record<string, string>,
) {
  const exposesEndpoint = template.fields.some((field) => field.name === "base_url")
  if (!exposesEndpoint) return template.default_base_url || null
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
  template: LlmProviderTemplate,
  field: LlmProviderTemplateField,
  configured: boolean,
) {
  if (field.name === "api_key") {
    return configured
      ? t("providerCards.savedKeyPlaceholder")
      : t("providerCards.apiKeyPlaceholder")
  }
  if (field.name === "base_url") {
    return t("providerCards.endpointPlaceholder")
  }
  if (field.name === "model_id") return t("providerCards.modelIdPlaceholder")
  return field.placeholder
}

function fieldLabel(
  t: SettingsTranslations,
  template: LlmProviderTemplate,
  field: LlmProviderTemplateField,
) {
  if (field.name === "api_key") return t("providerCards.apiKeyLabel")
  if (field.name === "base_url") {
    return t("providerCards.endpointLabel")
  }
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

"use client"

import { useMemo, useState, type FormEvent, type ReactNode } from "react"
import {
  CheckCircle2,
  Loader2,
  Plus,
  RefreshCw,
  SlidersHorizontal,
} from "lucide-react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useLlmCatalog } from "@/hooks/use-llm-catalog"
import type {
  LlmModel,
  LlmModelProfile,
  LlmProvider,
  LlmProviderKind,
} from "@/lib/llm"

const PROVIDER_KINDS: LlmProviderKind[] = [
  "openai",
  "anthropic",
  "gemini",
  "openrouter",
  "ollama",
  "vllm",
  "openai_compatible",
]

export function LlmCatalogPanel() {
  const t = useTranslations("settings")
  const {
    providers,
    models,
    profiles,
    isLoading,
    isMutating,
    error,
    createProvider,
    setProviderEnabled,
    testProvider,
  } = useLlmCatalog()
  const [name, setName] = useState("")
  const [kind, setKind] = useState<LlmProviderKind>("openai_compatible")
  const [baseUrl, setBaseUrl] = useState("")
  const [apiKeyRef, setApiKeyRef] = useState("")

  const modelsById = useMemo(
    () => new Map(models.map((model) => [model.id, model])),
    [models],
  )
  const providerById = useMemo(
    () => new Map(providers.map((provider) => [provider.id, provider])),
    [providers],
  )

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const provider = await createProvider({
      name: name.trim(),
      kind,
      baseUrl: baseUrl.trim() || null,
      apiKeyRef: apiKeyRef.trim() || null,
      scope: "workspace",
      enabled: true,
    })
    if (!provider) return
    setName("")
    setKind("openai_compatible")
    setBaseUrl("")
    setApiKeyRef("")
    toast.success(t("llmCatalog.created"))
  }

  const handleTestProvider = async (provider: LlmProvider) => {
    const result = await testProvider(provider.id)
    if (!result) return
    toast[result.success ? "success" : "error"](
      result.success ? t("llmCatalog.testPassed") : t("llmCatalog.testFailed"),
    )
  }

  const handleToggleProvider = async (provider: LlmProvider) => {
    const updated = await setProviderEnabled(provider, !provider.enabled)
    if (updated) toast.success(t("llmCatalog.updated"))
  }

  return (
    <section className="space-y-4 border border-border/60 bg-card p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h4 className="text-sm font-semibold text-foreground">
            {t("llmCatalog.title")}
          </h4>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
            {t("llmCatalog.description")}
          </p>
        </div>
        {isLoading ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            {t("loading")}
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {t("llmCatalog.loadFailed")}
        </div>
      ) : null}

      <form
        className="grid gap-3 border-t border-border/70 pt-4 md:grid-cols-2 xl:grid-cols-5"
        onSubmit={handleCreate}
      >
        <div className="space-y-2 xl:col-span-1">
          <Label htmlFor="llm-provider-name">{t("llmCatalog.providerName")}</Label>
          <Input
            id="llm-provider-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
        </div>
        <div className="space-y-2 xl:col-span-1">
          <Label htmlFor="llm-provider-kind">{t("llmCatalog.providerKind")}</Label>
          <select
            id="llm-provider-kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as LlmProviderKind)}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            {PROVIDER_KINDS.map((providerKind) => (
              <option key={providerKind} value={providerKind}>
                {providerKind}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2 xl:col-span-1">
          <Label htmlFor="llm-provider-base-url">{t("baseUrl")}</Label>
          <Input
            id="llm-provider-base-url"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
          />
        </div>
        <div className="space-y-2 xl:col-span-1">
          <Label htmlFor="llm-provider-api-key-ref">{t("llmCatalog.apiKeyRef")}</Label>
          <Input
            id="llm-provider-api-key-ref"
            value={apiKeyRef}
            onChange={(event) => setApiKeyRef(event.target.value)}
          />
        </div>
        <div className="flex items-end">
          <Button type="submit" size="sm" disabled={isMutating || !name.trim()}>
            <Plus className="size-4" />
            {t("llmCatalog.addProvider")}
          </Button>
        </div>
      </form>

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <ProviderList
          providers={providers}
          isMutating={isMutating}
          onTest={handleTestProvider}
          onToggle={handleToggleProvider}
        />
        <ModelProfileList profiles={profiles} modelsById={modelsById} />
      </div>

      <ModelList
        models={models}
        providerById={providerById}
      />
    </section>
  )
}

function ProviderList({
  providers,
  isMutating,
  onTest,
  onToggle,
}: {
  providers: LlmProvider[]
  isMutating: boolean
  onTest: (provider: LlmProvider) => void
  onToggle: (provider: LlmProvider) => void
}) {
  const t = useTranslations("settings")
  if (providers.length === 0) {
    return (
      <div className="border-t border-border/70 pt-3 text-sm text-muted-foreground">
        {t("llmCatalog.noProviders")}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {providers.map((provider) => (
        <div key={provider.id} className="border border-border/70 p-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium text-foreground">{provider.name}</p>
                <span className="font-mono text-xs text-muted-foreground">
                  {provider.kind}
                </span>
                <span className="text-xs text-muted-foreground">
                  {provider.enabled ? t("llmCatalog.enabled") : t("llmCatalog.disabled")}
                </span>
              </div>
              <p className="mt-1 truncate text-xs text-muted-foreground">
                {provider.base_url || provider.api_key_ref || provider.scope}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onTest(provider)}
                disabled={isMutating}
              >
                <RefreshCw className="size-3.5" />
                {t("llmCatalog.testProvider")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => onToggle(provider)}
                disabled={isMutating}
              >
                {provider.enabled
                  ? t("llmCatalog.disableProvider")
                  : t("llmCatalog.enableProvider")}
              </Button>
            </div>
          </div>
          {provider.test_status ? (
            <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <CheckCircle2 className="size-3.5 text-emerald-600 dark:text-emerald-400" />
              {String(provider.test_status.success ?? "")}
              {provider.test_status.latency_ms ? (
                <span>{String(provider.test_status.latency_ms)}ms</span>
              ) : null}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  )
}

function ModelList({
  models,
  providerById,
}: {
  models: LlmModel[]
  providerById: Map<string, LlmProvider>
}) {
  const t = useTranslations("settings")
  if (models.length === 0) {
    return (
      <div className="border-t border-border/70 pt-3 text-sm text-muted-foreground">
        {t("llmCatalog.noModels")}
      </div>
    )
  }

  return (
    <div className="space-y-2 border-t border-border/70 pt-3">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <SlidersHorizontal className="size-3.5" />
        {t("llmCatalog.models")}
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {models.map((model) => (
          <div key={model.id} className="border border-border/70 p-3">
            <p className="font-medium text-foreground">{model.display_name}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {providerById.get(model.provider_id)?.name ?? model.provider_id} /{" "}
              {model.model_id}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Capability enabled={Boolean(model.context_length)}>
                {t("llmCatalog.context")}: {model.context_length ?? "-"}
              </Capability>
              <Capability enabled={Boolean(model.max_output_tokens)}>
                {t("llmCatalog.maxOutput")}: {model.max_output_tokens ?? "-"}
              </Capability>
              <Capability enabled={model.supports_tools}>
                {t("llmCatalog.tools")}
              </Capability>
              <Capability enabled={model.supports_streaming}>
                {t("llmCatalog.streaming")}
              </Capability>
              <Capability enabled={model.supports_vision}>
                {t("llmCatalog.vision")}
              </Capability>
              <Capability enabled={model.supports_json_schema}>
                {t("llmCatalog.jsonSchema")}
              </Capability>
              <Capability enabled={model.supports_reasoning}>
                {t("llmCatalog.reasoning")}
              </Capability>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ModelProfileList({
  profiles,
  modelsById,
}: {
  profiles: LlmModelProfile[]
  modelsById: Map<string, LlmModel>
}) {
  const t = useTranslations("settings")
  if (profiles.length === 0) {
    return (
      <div className="border border-border/70 p-3 text-sm text-muted-foreground">
        {t("llmCatalog.noProfiles")}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="text-xs font-medium text-muted-foreground">
        {t("llmCatalog.modelProfiles")}
      </div>
      {profiles.map((profile) => {
        const model = modelsById.get(profile.primary_model_id)
        return (
          <div key={profile.id} className="border border-border/70 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-medium text-foreground">{profile.name}</p>
              <span className="font-mono text-xs text-muted-foreground">
                {profile.task_type}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {model?.display_name ?? profile.primary_model_id}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              {t("llmCatalog.maxOutput")}: {profile.max_tokens ?? "-"} /{" "}
              {t("llmCatalog.reasoning")}: {profile.reasoning_budget ?? "-"}
            </p>
          </div>
        )
      })}
    </div>
  )
}

function Capability({
  enabled,
  children,
}: {
  enabled: boolean
  children: ReactNode
}) {
  return (
    <span
      className={
        enabled
          ? "border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-700 dark:text-emerald-300"
          : "border border-border/70 bg-muted/30 px-2 py-0.5 text-[11px] text-muted-foreground"
      }
    >
      {children}
    </span>
  )
}

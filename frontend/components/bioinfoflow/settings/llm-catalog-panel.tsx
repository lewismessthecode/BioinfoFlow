"use client"

import { useEffect, useMemo, useState } from "react"
import { CheckCircle2, ExternalLink, KeyRound, Loader2, RefreshCw } from "lucide-react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useLlmCatalog } from "@/hooks/use-llm-catalog"
import type {
  LlmConfiguredProvider,
  LlmProviderCredentialSource,
  LlmProviderKind,
} from "@/lib/llm"
import { cn } from "@/lib/utils"

type ProviderCardSpec = {
  slug: string
  name: string
  kind: LlmProviderKind
  defaultBaseUrl?: string | null
  docsUrl: string
  envVarName?: string
  noKeyRequired?: boolean
  keyOptional?: boolean
  showEndpoint?: boolean
}

const PROVIDER_CARDS: ProviderCardSpec[] = [
  {
    slug: "openai",
    name: "OpenAI",
    kind: "openai",
    docsUrl: "https://platform.openai.com/api-keys",
    envVarName: "OPENAI_API_KEY",
  },
  {
    slug: "anthropic",
    name: "Claude",
    kind: "anthropic",
    docsUrl: "https://console.anthropic.com/settings/keys",
    envVarName: "ANTHROPIC_API_KEY",
  },
  {
    slug: "gemini",
    name: "Gemini",
    kind: "gemini",
    docsUrl: "https://aistudio.google.com/apikey",
    envVarName: "GEMINI_API_KEY",
  },
  {
    slug: "grok",
    name: "Grok",
    kind: "openai_compatible",
    defaultBaseUrl: "https://api.x.ai/v1",
    docsUrl: "https://console.x.ai/",
    envVarName: "XAI_API_KEY",
  },
  {
    slug: "deepseek",
    name: "DeepSeek",
    kind: "deepseek",
    docsUrl: "https://platform.deepseek.com/api_keys",
    envVarName: "DEEPSEEK_API_KEY",
  },
  {
    slug: "openrouter",
    name: "OpenRouter",
    kind: "openrouter",
    docsUrl: "https://openrouter.ai/settings/keys",
    envVarName: "OPENROUTER_API_KEY",
  },
  {
    slug: "ollama",
    name: "Ollama",
    kind: "ollama",
    defaultBaseUrl: "http://localhost:11434",
    docsUrl: "https://ollama.com/download",
    noKeyRequired: true,
    showEndpoint: true,
  },
  {
    slug: "glm",
    name: "GLM",
    kind: "openai_compatible",
    defaultBaseUrl: "https://open.bigmodel.cn/api/paas/v4",
    docsUrl: "https://bigmodel.cn/usercenter/proj-mgmt/apikeys",
    envVarName: "GLM_API_KEY",
  },
  {
    slug: "minimax",
    name: "Minimax",
    kind: "openai_compatible",
    defaultBaseUrl: "https://api.minimax.chat/v1",
    docsUrl: "https://platform.minimaxi.com/user-center/basic-information/interface-key",
    envVarName: "MINIMAX_API_KEY",
  },
  {
    slug: "vllm",
    name: "vLLM",
    kind: "vllm",
    defaultBaseUrl: "http://localhost:8000/v1",
    docsUrl: "https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
    keyOptional: true,
    showEndpoint: true,
  },
  {
    slug: "openai-compatible",
    name: "OpenAI Compatible",
    kind: "openai_compatible",
    defaultBaseUrl: "https://api.example.com/v1",
    docsUrl: "https://platform.openai.com/docs/api-reference",
    keyOptional: true,
    showEndpoint: true,
  },
]

export function LlmCatalogPanel() {
  const t = useTranslations("settings")
  const {
    configuredProviders,
    models = [],
    isLoading,
    isMutating,
    createProvider,
    updateProvider,
    updateCredential,
    discoverModels,
  } = useLlmCatalog()
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({})
  const [endpoints, setEndpoints] = useState<Record<string, string>>({})
  const [savingSlug, setSavingSlug] = useState<string | null>(null)
  const [refreshingSlug, setRefreshingSlug] = useState<string | null>(null)

  const providersBySlug = useMemo(() => {
    const bySlug = new Map<string, LlmConfiguredProvider>()
    for (const spec of PROVIDER_CARDS) {
      const provider = configuredProviders.find((item) => providerMatchesSpec(item, spec))
      if (provider) bySlug.set(spec.slug, provider)
    }
    return bySlug
  }, [configuredProviders])

  useEffect(() => {
    setEndpoints((current) => {
      const next = { ...current }
      let changed = false
      for (const spec of PROVIDER_CARDS) {
        if (next[spec.slug] !== undefined) continue
        const provider = providersBySlug.get(spec.slug)
        next[spec.slug] = provider?.base_url ?? spec.defaultBaseUrl ?? ""
        changed = true
      }
      return changed ? next : current
    })
  }, [providersBySlug])

  const saveProvider = async (spec: ProviderCardSpec) => {
    const secret = (apiKeys[spec.slug] ?? "").trim()
    const endpoint = (endpoints[spec.slug] ?? spec.defaultBaseUrl ?? "").trim()
    const existingProvider = providersBySlug.get(spec.slug)
    if (!existingProvider && !spec.noKeyRequired && !spec.keyOptional && !secret) return
    if (spec.showEndpoint && !endpoint) return

    setSavingSlug(spec.slug)
    try {
      const shouldSaveNoAuth =
        (spec.noKeyRequired || spec.keyOptional) &&
        !secret &&
        !existingProvider?.credential?.configured
      const authMode = secret
        ? "stored"
        : shouldSaveNoAuth
          ? "none"
          : existingProvider?.metadata?.authMode
      const metadata = {
        ...(existingProvider?.metadata ?? {}),
        providerSlug: spec.slug,
        ...(authMode ? { authMode } : {}),
      }
      const baseUrl = endpoint || spec.defaultBaseUrl || null
      const provider =
        existingProvider ??
        await createProvider({
          name: spec.name,
          kind: spec.kind,
          baseUrl,
          apiKeyRef: null,
          scope: "user",
          enabled: true,
          metadata,
        })

      if (!provider) {
        toast.error(t("providerCards.saveFailed"))
        return
      }

      if (existingProvider) {
        const updated = await updateProvider(existingProvider.id, {
          name: existingProvider.name || spec.name,
          baseUrl,
          metadata,
          enabled: true,
        })
        if (!updated) {
          toast.error(t("providerCards.saveFailed"))
          return
        }
      }

      if (secret || shouldSaveNoAuth || !existingProvider?.credential?.configured) {
        const source: LlmProviderCredentialSource =
          shouldSaveNoAuth ? "none" : "stored"
        const credential = await updateCredential(provider.id, {
          source,
          envVarName: null,
          secret: source === "stored" ? secret : null,
        })
        if (!credential) {
          toast.error(t("providerCards.saveFailed"))
          return
        }
      }

      setApiKeys((current) => ({ ...current, [spec.slug]: "" }))
      toast.success(t("providerCards.saved"))
    } finally {
      setSavingSlug(null)
    }
  }

  const ensureProvider = async (spec: ProviderCardSpec) => {
    const existingProvider = providersBySlug.get(spec.slug)
    const endpoint = (endpoints[spec.slug] ?? spec.defaultBaseUrl ?? "").trim()
    const metadata = {
      ...(existingProvider?.metadata ?? {}),
      providerSlug: spec.slug,
    }
    const baseUrl = endpoint || spec.defaultBaseUrl || null

    if (existingProvider) {
      const updated = await updateProvider(existingProvider.id, {
        name: existingProvider.name || spec.name,
        baseUrl,
        metadata,
        enabled: true,
      })
      return updated ?? existingProvider
    }

    return createProvider({
      name: spec.name,
      kind: spec.kind,
      baseUrl,
      apiKeyRef: null,
      scope: "user",
      enabled: true,
      metadata,
    })
  }

  const refreshLocalModels = async (spec: ProviderCardSpec) => {
    if (spec.kind !== "ollama") return
    const endpoint = (endpoints[spec.slug] ?? spec.defaultBaseUrl ?? "").trim()
    if (!endpoint) return

    setRefreshingSlug(spec.slug)
    try {
      const existingProvider = providersBySlug.get(spec.slug)
      const provider = await ensureProvider(spec)
      if (!provider) {
        toast.error(t("providerCards.modelRefreshFailed"))
        return
      }

      if (!existingProvider) {
        const credential = await updateCredential(provider.id, {
          source: "none",
          envVarName: null,
          secret: null,
        })
        if (!credential) {
          toast.error(t("providerCards.modelRefreshFailed"))
          return
        }
      }

      const discovered = await discoverModels(provider.id)
      if (!discovered) {
        toast.error(t("providerCards.modelRefreshFailed"))
        return
      }

      toast.success(t("providerCards.modelsRefreshed"))
    } finally {
      setRefreshingSlug(null)
    }
  }

  return (
    <section className="space-y-4">
      {isLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          {t("providerCards.loading")}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {PROVIDER_CARDS.map((spec) => {
          const provider = providersBySlug.get(spec.slug)
          const configured = Boolean(
            provider?.credential?.configured ||
              provider?.credential?.available ||
              ((spec.noKeyRequired || spec.keyOptional) &&
                provider?.enabled &&
                provider?.credential?.source === "none"),
          )
          const keyValue = apiKeys[spec.slug] ?? ""
          const endpointValue = endpoints[spec.slug] ?? spec.defaultBaseUrl ?? ""
          const providerModels = provider
            ? models.filter((model) => model.provider_id === provider.id)
            : []
          const saving = savingSlug === spec.slug || isMutating
          const refreshing = refreshingSlug === spec.slug
          const canSave =
            !saving &&
            (!spec.showEndpoint || endpointValue.trim().length > 0) &&
            (configured ||
              spec.noKeyRequired ||
              spec.keyOptional ||
              keyValue.trim().length > 0)

          return (
            <div
              key={spec.slug}
              role="group"
              aria-label={spec.name}
              className="flex min-h-[214px] flex-col rounded-[24px] border border-border/70 bg-card p-4 shadow-sm shadow-foreground/5 transition-colors hover:border-border"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h4 className="truncate text-sm font-semibold text-foreground">
                    {spec.name}
                  </h4>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {configured
                      ? t("providerCards.configured")
                      : spec.noKeyRequired || spec.keyOptional
                        ? t("providerCards.noKeyRequired")
                        : t("providerCards.notConfigured")}
                  </p>
                </div>
                <span
                  className={cn(
                    "flex size-8 shrink-0 items-center justify-center rounded-full border",
                    configured
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300"
                      : "border-border bg-muted text-muted-foreground",
                  )}
                >
                  {configured ? (
                    <CheckCircle2 className="size-4" />
                  ) : (
                    <KeyRound className="size-4" />
                  )}
                </span>
              </div>

              <div className="mt-4 grid gap-2">
                {provider?.credential?.masked_hint ||
                provider?.credential?.fingerprint ? (
                  <div className="truncate text-xs text-muted-foreground">
                    {provider.credential.masked_hint ?? provider.credential.fingerprint}
                  </div>
                ) : null}
                {spec.showEndpoint ? (
                  <Input
                    aria-label={`${spec.name} endpoint`}
                    value={endpointValue}
                    onChange={(event) =>
                      setEndpoints((current) => ({
                        ...current,
                        [spec.slug]: event.target.value,
                      }))
                    }
                    placeholder={t("providerCards.endpointPlaceholder")}
                    className="h-10 rounded-2xl"
                  />
                ) : null}
                {!spec.noKeyRequired ? (
                  <Input
                    aria-label={`${spec.name} API key`}
                    type="password"
                    value={keyValue}
                    onChange={(event) =>
                      setApiKeys((current) => ({
                        ...current,
                        [spec.slug]: event.target.value,
                      }))
                    }
                    placeholder={
                      configured
                        ? t("providerCards.savedKeyPlaceholder")
                        : t("providerCards.apiKeyPlaceholder")
                    }
                    className="h-10 rounded-2xl"
                  />
                ) : null}
                {spec.kind === "ollama" && providerModels.length > 0 ? (
                  <div className="rounded-2xl bg-muted/45 px-3 py-2 text-xs text-muted-foreground">
                    <div className="mb-1 font-medium text-foreground">
                      {t("providerCards.modelsDiscovered", {
                        count: providerModels.length,
                      })}
                    </div>
                    <div className="truncate">
                      {providerModels
                        .map((model) => model.model_id)
                        .slice(0, 3)
                        .join(", ")}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="mt-auto flex items-center justify-between gap-3 pt-4">
                <a
                  href={spec.docsUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-w-0 items-center gap-1 truncate text-xs text-muted-foreground transition-colors hover:text-foreground"
                >
                  <span className="truncate">
                    {t("providerCards.getApiKey", { provider: spec.name })}
                  </span>
                  <ExternalLink className="size-3 shrink-0" />
                </a>
                <Button
                  type="button"
                  size="sm"
                  className="h-9 rounded-full px-4"
                  disabled={!canSave}
                  onClick={() => void saveProvider(spec)}
                >
                  {saving ? t("providerCards.saving") : t("providerCards.save")}
                </Button>
              </div>
              {spec.kind === "ollama" ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="mt-2 h-8 justify-center rounded-full text-xs text-muted-foreground hover:text-foreground"
                  disabled={refreshing || isMutating || !endpointValue.trim()}
                  onClick={() => void refreshLocalModels(spec)}
                >
                  {refreshing ? (
                    <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="mr-1.5 size-3.5" />
                  )}
                  {refreshing
                    ? t("providerCards.refreshingModels")
                    : t("providerCards.refreshModels")}
                </Button>
              ) : null}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function providerMatchesSpec(
  provider: LlmConfiguredProvider,
  spec: ProviderCardSpec,
) {
  const providerSlug = String(provider.metadata?.providerSlug ?? "")
  if (providerSlug) return providerSlug === spec.slug
  if (spec.kind !== "openai_compatible") return provider.kind === spec.kind
  return provider.kind === spec.kind && provider.name === spec.name
}

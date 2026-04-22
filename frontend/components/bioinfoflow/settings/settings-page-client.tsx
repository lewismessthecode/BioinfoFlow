"use client"

import { useEffect, useState } from "react"
import { useTranslations } from "next-intl"
import { Loader2, ShieldCheck, User, Cpu, Users } from "lucide-react"
import {
  ProviderCard,
  type ProviderField,
} from "@/components/bioinfoflow/settings/provider-card"
import { MembersPanel } from "@/components/bioinfoflow/settings/members-panel"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { useLlmSettings } from "@/hooks/use-llm-settings"
import { apiRequest } from "@/lib/api"
import { authClient } from "@/lib/auth-client"
import type { AuthMode, TeamRole } from "@/lib/auth-config"
import { cn } from "@/lib/utils"
import { toast } from "sonner"

type ProviderFieldName = ProviderField["name"]

type ProviderMeta = {
  id: string
  label: string
  credential_type: string
  credential_fields?: ProviderFieldName[]
  base_url?: string | null
  default_model?: string | null
}

type SettingsPageClientProps = {
  viewer: {
    id: string
    name?: string
    email?: string
    role: TeamRole
    mode: AuthMode
    canManageMembers: boolean
    authEnabled: boolean
    authLocalEnabled: boolean
  }
}

type SettingsSection = "account" | "providers" | "members"

const NAV_ITEMS: { key: SettingsSection; icon: typeof User; requiresMembers?: boolean }[] = [
  { key: "account", icon: User },
  { key: "providers", icon: Cpu },
  { key: "members", icon: Users, requiresMembers: true },
]

export default function SettingsPageClient({
  viewer,
}: SettingsPageClientProps) {
  const t = useTranslations("settings")
  const { settings, isLoading, updateSettings, testProvider } = useLlmSettings()
  const [providers, setProviders] = useState<ProviderMeta[]>([])
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [savingPassword, setSavingPassword] = useState(false)
  const [activeSection, setActiveSection] = useState<SettingsSection>("account")

  useEffect(() => {
    if (activeSection !== "providers") return
    apiRequest<ProviderMeta[]>("/providers")
      .then(({ data }) => setProviders(data))
      .catch(() => toast.error(t("testFailed")))
  }, [activeSection, t])

  if (isLoading || !settings) {
    return (
      <div className="h-full space-y-4 overflow-y-auto p-6">
        <Skeleton className="h-6 w-40" />
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
    )
  }

  const fallbackCredentialFields = (
    provider: ProviderMeta,
  ): ProviderFieldName[] => {
    const fields: ProviderFieldName[] = []

    if (provider.credential_type !== "base_url_only") {
      fields.push("api_key")
    }
    if (
      provider.credential_type === "api_key_and_base_url" ||
      provider.credential_type === "base_url_only"
    ) {
      fields.push("base_url")
    }
    if (provider.id === "ollama") {
      fields.push("model")
    }

    return fields
  }

  const getFieldLabel = (field: ProviderFieldName) => {
    if (field === "api_key") return t("apiKey")
    if (field === "base_url") return t("baseUrl")
    return t("model")
  }

  const getFieldPlaceholder = (
    provider: ProviderMeta,
    field: ProviderFieldName,
  ) => {
    if (field === "api_key") {
      return t("apiKeyPlaceholder", { prefix: "" })
    }
    if (field === "base_url") {
      return provider.base_url || t("baseUrlPlaceholder")
    }
    return provider.default_model || t("modelPlaceholder")
  }

  const handleChangePassword = async (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault()
    setSavingPassword(true)

    try {
      await authClient.changePassword({
        currentPassword,
        newPassword,
        revokeOtherSessions: true,
      })
      setCurrentPassword("")
      setNewPassword("")
      toast.success(t("account.passwordChanged"))
    } catch {
      toast.error(t("account.passwordChangeFailed"))
    } finally {
      setSavingPassword(false)
    }
  }

  const modeLabel = t(`account.modes.${viewer.mode}`)

  const visibleNavItems = NAV_ITEMS.filter(
    (item) => !item.requiresMembers || viewer.canManageMembers,
  )

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Sub-sidebar ──────────────────────────────────── */}
      <nav className="w-[200px] shrink-0 border-r border-border/60 bg-secondary/30 p-4">
        <h2 className="mb-4 text-lg font-semibold tracking-tight text-foreground">
          {t("pageTitle")}
        </h2>
        <ul className="space-y-0.5">
          {visibleNavItems.map((item) => {
            const Icon = item.icon
            return (
              <li key={item.key}>
                <button
                  type="button"
                  onClick={() => setActiveSection(item.key)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors",
                    activeSection === item.key
                      ? "bg-background text-foreground shadow-sm ring-1 ring-border/40"
                      : "text-muted-foreground hover:bg-background/60 hover:text-foreground",
                  )}
                >
                  <Icon className="size-4 shrink-0" />
                  {t(`nav.${item.key}`)}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      {/* ── Content area ─────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl space-y-6 p-6">
          {/* ── Account Section ────────────────────────── */}
          {activeSection === "account" && (
            <>
              <div>
                <h3 className="text-base font-semibold text-foreground">{t("account.title")}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{t("account.description")}</p>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  { label: t("account.email"), value: viewer.email || t("account.notAvailable") },
                  { label: t("account.role"), value: t(`members.roles.${viewer.role}`) },
                  { label: t("account.mode"), value: modeLabel },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl border border-border/60 bg-secondary/30 p-3.5">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                      {item.label}
                    </p>
                    <p className="mt-1.5 text-sm font-medium text-foreground">
                      {item.value}
                    </p>
                  </div>
                ))}
              </div>

              {viewer.authEnabled && viewer.authLocalEnabled ? (
                <form
                  className="space-y-4 rounded-xl border border-border/60 bg-card p-4"
                  onSubmit={handleChangePassword}
                >
                  <div className="flex items-center gap-3">
                    <div className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground">
                      <ShieldCheck className="size-4" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">
                        {t("account.changePasswordTitle")}
                      </p>
                      <p className="text-xs leading-5 text-muted-foreground">
                        {t("account.changePasswordDescription")}
                      </p>
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="current-password">
                        {t("account.currentPassword")}
                      </Label>
                      <Input
                        id="current-password"
                        type="password"
                        autoComplete="current-password"
                        value={currentPassword}
                        onChange={(event) => setCurrentPassword(event.target.value)}
                        required
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="new-password">
                        {t("account.newPassword")}
                      </Label>
                      <Input
                        id="new-password"
                        type="password"
                        autoComplete="new-password"
                        value={newPassword}
                        onChange={(event) => setNewPassword(event.target.value)}
                        required
                      />
                    </div>
                  </div>

                  <Button
                    type="submit"
                    disabled={savingPassword || !currentPassword || !newPassword}
                    size="sm"
                  >
                    {savingPassword ? (
                      <>
                        <Loader2 className="size-4 animate-spin" />
                        {t("account.savingPassword")}
                      </>
                    ) : (
                      t("account.savePassword")
                    )}
                  </Button>
                </form>
              ) : null}
            </>
          )}

          {/* ── AI Providers Section ───────────────────── */}
          {activeSection === "providers" && (
            <>
              <div>
                <h3 className="text-base font-semibold text-foreground">{t("title")}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
              </div>

              <div className="space-y-3">
                {providers.map((provider) => {
                  const fieldNames =
                    provider.credential_fields?.length
                      ? provider.credential_fields
                      : fallbackCredentialFields(provider)

                  const fields: ProviderField[] = fieldNames.map((fieldName) => ({
                    name: fieldName,
                    label: getFieldLabel(fieldName),
                    value: settings.provider_credentials[provider.id]?.[fieldName] ?? "",
                    placeholder: getFieldPlaceholder(provider, fieldName),
                    secret: fieldName === "api_key",
                  }))

                  return (
                    <ProviderCard
                      key={provider.id}
                      provider={provider.id}
                      label={provider.label}
                      fields={fields}
                      isConfigured={settings.configured_providers.includes(provider.id)}
                      onUpdateField={async (fieldName, value) => {
                        await updateSettings({
                          provider_credentials: {
                            [provider.id]: { [fieldName]: value },
                          },
                        })
                      }}
                      onTest={async () => await testProvider(provider.id)}
                    />
                  )
                })}
              </div>
            </>
          )}

          {/* ── Members Section ────────────────────────── */}
          {activeSection === "members" && viewer.canManageMembers && (
            <MembersPanel
              viewerId={viewer.id}
              viewerRole={viewer.role}
              authLocalEnabled={viewer.authLocalEnabled}
            />
          )}
        </div>
      </div>
    </div>
  )
}

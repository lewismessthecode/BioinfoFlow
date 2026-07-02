"use client"

import { useEffect, useState } from "react"
import { useTranslations } from "next-intl"
import {
  Cpu,
  Database,
  Loader2,
  Bot,
  Monitor,
  Moon,
  Palette,
  PartyPopper,
  ShieldCheck,
  Sun,
  User,
  Users,
} from "lucide-react"
import { Logo } from "@/components/bioinfoflow/logo"
import { ContainerRegistriesPanel } from "@/components/bioinfoflow/settings/container-registries-panel"
import { LlmCatalogPanel } from "@/components/bioinfoflow/settings/llm-catalog-panel"
import { MembersPanel } from "@/components/bioinfoflow/settings/members-panel"
import {
  appearancePresetIds,
  appearancePresets,
  type AppearanceTokens,
} from "@/lib/appearance/presets"
import { useAppearance } from "@/lib/appearance/use-appearance"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { authClient } from "@/lib/auth-client"
import {
  celebratePreview,
  setCelebrationsEnabled as persistCelebrationsEnabled,
  useCelebrationsEnabledPreference,
  useReducedMotionPreference,
} from "@/lib/celebrations"
import {
  readAgentTurnPolicy,
  writeAgentTurnPolicy,
  type AgentTurnPolicy,
} from "@/lib/agent-runtime/turn-policy"
import type { AuthMode, TeamRole } from "@/lib/auth-config"
import { cn } from "@/lib/utils"
import { toast } from "sonner"

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

type SettingsSection =
  | "account"
  | "appearance"
  | "agent"
  | "providers"
  | "registries"
  | "members"

const NAV_ITEMS: {
  key: SettingsSection
  icon: typeof User
  requiresMembers?: boolean
  requiresRegistryAdmin?: boolean
}[] = [
  { key: "account", icon: User },
  { key: "appearance", icon: Palette },
  { key: "agent", icon: Bot },
  { key: "providers", icon: Cpu },
  { key: "registries", icon: Database, requiresRegistryAdmin: true },
  { key: "members", icon: Users, requiresMembers: true },
]

const AGENT_TURN_POLICIES: AgentTurnPolicy[] = ["interrupt", "queue"]

function ThemePreviewCard({
  title,
  mode,
  modeLabel,
  presetLabel,
  tokens,
}: {
  title: string
  mode: "light" | "dark"
  modeLabel: string
  presetLabel: string
  tokens: AppearanceTokens
}) {
  const ModeIcon = mode === "dark" ? Moon : Sun

  return (
    <div
      data-testid="appearance-preview-shell"
      className="relative flex min-h-[452px] flex-col overflow-hidden rounded-[28px] border"
      style={{
        backgroundColor: tokens.background,
        borderColor: tokens.border,
        color: tokens.foreground,
        boxShadow:
          mode === "dark"
            ? "0 26px 64px -36px rgba(0, 0, 0, 0.72)"
            : "0 26px 64px -36px rgba(15, 23, 42, 0.18)",
      }}
    >
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-28 opacity-95"
        style={{
          backgroundImage: `linear-gradient(180deg, ${tokens["accent-subtle"]} 0%, transparent 100%)`,
        }}
      />

      <div
        className="relative flex items-center justify-between gap-3 border-b px-4 py-3.5"
        style={{
          borderColor: tokens.border,
          backgroundColor: tokens["surface-subtle"],
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="flex size-10 shrink-0 items-center justify-center rounded-2xl border"
            style={{
              borderColor: tokens.border,
              backgroundColor: tokens.card,
            }}
          >
            <Logo size={22} />
          </div>
          <div>
            <p className="text-sm font-semibold">{title}</p>
            <p
              className="text-xs"
              style={{ color: tokens["text-muted"] }}
            >
              {presetLabel}
            </p>
          </div>
        </div>
        <div
          className="inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium"
          style={{
            borderColor: tokens.border,
            backgroundColor: tokens["surface-elevated"],
            color: tokens["text-secondary"],
          }}
        >
          <ModeIcon className="size-3.5" />
          {modeLabel}
        </div>
      </div>

      <div className="relative grid flex-1 gap-3 p-4 md:grid-cols-[104px_minmax(0,1fr)]">
        <aside
          className="flex h-full flex-col rounded-[24px] border px-3 py-4"
          style={{
            backgroundColor: tokens.sidebar,
            borderColor: tokens["sidebar-border"],
            color: tokens["sidebar-foreground"],
          }}
        >
          <div className="flex justify-center">
            <div
              className="flex h-11 w-11 items-center justify-center rounded-[18px]"
              style={{ backgroundColor: tokens["sidebar-accent"] }}
            >
              <Logo size={24} />
            </div>
          </div>
          <div className="mt-4 space-y-2.5">
            <div
              className="h-8 rounded-2xl"
              style={{ backgroundColor: tokens["sidebar-accent"] }}
            />
            <div
              className="h-2.5 rounded-full"
              style={{ backgroundColor: tokens["accent-muted"] }}
            />
            <div
              className="h-2.5 w-4/5 rounded-full"
              style={{ backgroundColor: tokens["accent-subtle"] }}
            />
            <div
              className="h-2.5 w-3/5 rounded-full"
              style={{ backgroundColor: tokens["accent-subtle"] }}
            />
          </div>
        </aside>

        <div className="flex h-full flex-col gap-3">
          <div
            className="rounded-[24px] border p-3.5"
            style={{
              borderColor: tokens.border,
              backgroundColor: tokens.card,
            }}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span
                  className="size-2.5 rounded-full"
                  style={{ backgroundColor: tokens["fg-faint"] }}
                />
                <span
                  className="size-2.5 rounded-full"
                  style={{ backgroundColor: tokens["fg-faint"] }}
                />
                <span
                  className="size-2.5 rounded-full"
                  style={{ backgroundColor: tokens["fg-faint"] }}
                />
              </div>

              <div className="flex items-center gap-2">
                <span
                  className="inline-flex h-6 items-center rounded-full px-2.5 text-[11px] font-semibold"
                  style={{
                    backgroundColor: tokens.primary,
                    color: tokens["primary-foreground"],
                  }}
                >
                  {presetLabel}
                </span>
                <div
                  className="block h-6 w-12 rounded-full"
                  style={{ backgroundColor: tokens["surface-subtle"] }}
                />
              </div>
            </div>

            <div
              data-testid="appearance-preview-main"
              className="mt-4 grid flex-1 grid-cols-[minmax(0,1fr)_148px] gap-3"
            >
              <div className="space-y-3">
                <div
                  className="min-h-[126px] rounded-[20px] p-3"
                  style={{
                    backgroundColor: tokens.accent,
                    color: tokens["text-secondary"],
                  }}
                >
                  <div
                    className="h-2.5 w-24 rounded-full"
                    style={{ backgroundColor: tokens.primary }}
                  />
                  <div
                    className="mt-3 h-3 rounded-full"
                    style={{ backgroundColor: tokens["surface-elevated"] }}
                  />
                  <div
                    className="mt-2 h-3 w-4/5 rounded-full"
                    style={{ backgroundColor: tokens["surface-elevated"] }}
                  />
                  <div className="mt-4 flex items-center gap-2">
                    <span
                      className="inline-flex h-7 items-center rounded-full px-3"
                      style={{
                        backgroundColor: tokens.primary,
                        color: tokens["primary-foreground"],
                      }}
                    >
                      <span
                        className="block h-2.5 w-9 rounded-full"
                        style={{ backgroundColor: tokens["primary-foreground"] }}
                      />
                    </span>
                    <div
                      className="block h-7 w-16 rounded-full"
                      style={{ backgroundColor: tokens["surface-elevated"] }}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {Array.from({ length: 2 }).map((_, index) => (
                    <div
                      key={`${presetLabel}-${mode}-${index}`}
                      className="rounded-[18px] border p-3"
                      style={{
                        borderColor: tokens.border,
                        backgroundColor:
                          index === 0 ? tokens["surface-subtle"] : tokens["surface-elevated"],
                      }}
                    >
                      <div
                        className="h-2.5 w-2/3 rounded-full"
                        style={{ backgroundColor: tokens["accent-muted"] }}
                      />
                      <div
                        className="mt-3 h-8 rounded-2xl"
                        style={{ backgroundColor: tokens["accent-subtle"] }}
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div
                className="flex h-full min-h-[239px] flex-col rounded-[20px] border px-3 py-3 font-mono text-[11px]"
                style={{
                  borderColor: tokens.border,
                  backgroundColor: tokens["terminal-background"],
                  color: tokens["terminal-foreground"],
                }}
              >
                <div className="mb-3 flex items-center gap-1.5">
                  <span
                    className="size-2 rounded-full"
                    style={{ backgroundColor: tokens["announcement-bg"] }}
                  />
                  <span
                    className="size-2 rounded-full"
                    style={{ backgroundColor: tokens.primary }}
                  />
                  <span
                    className="size-2 rounded-full"
                    style={{ backgroundColor: tokens.ring }}
                  />
                </div>

                <div className="space-y-2.5">
                  <div className="flex items-center gap-2">
                    <span style={{ color: tokens.primary }}>$</span>
                    <span
                      className="h-2.5 w-16 rounded-full"
                      style={{ backgroundColor: tokens["terminal-selection"] }}
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <span style={{ color: tokens.ring }}>{">"}</span>
                    <span
                      className="h-2.5 w-24 rounded-full"
                      style={{ backgroundColor: tokens["accent-muted"] }}
                    />
                  </div>
                  <div
                    className="h-9 rounded-2xl border"
                    style={{
                      borderColor: tokens.border,
                      backgroundColor: tokens["terminal-selection"],
                    }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function SettingsPageClient({
  viewer,
}: SettingsPageClientProps) {
  const t = useTranslations("settings")
  const {
    mode,
    setMode,
    lightPreset,
    darkPreset,
    activePreset,
    setLightPreset,
    setDarkPreset,
  } = useAppearance()
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [savingPassword, setSavingPassword] = useState(false)
  const [activeSection, setActiveSection] = useState<SettingsSection>("account")
  const [agentTurnPolicy, setAgentTurnPolicy] = useState<AgentTurnPolicy>(
    readAgentTurnPolicy,
  )
  const celebrationsEnabled = useCelebrationsEnabledPreference()
  const reducedMotion = useReducedMotionPreference()
  const canManageRegistries =
    !viewer.authEnabled ||
    viewer.mode !== "team" ||
    viewer.role === "owner" ||
    viewer.role === "admin"

  useEffect(() => {
    const section = new URLSearchParams(window.location.search).get("section")
    if (section === "appearance" || section === "agent" || section === "providers") {
      setActiveSection(section)
    } else if (section === "registries" && canManageRegistries) {
      setActiveSection("registries")
    } else if (section === "members" && viewer.canManageMembers) {
      setActiveSection("members")
    } else {
      setActiveSection("account")
    }
  }, [canManageRegistries, viewer.canManageMembers])

  useEffect(() => {
    const sectionIsHidden =
      (activeSection === "registries" && !canManageRegistries) ||
      (activeSection === "members" && !viewer.canManageMembers)
    if (sectionIsHidden) {
      setActiveSection("account")
    }
  }, [activeSection, canManageRegistries, viewer.canManageMembers])

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

  const handleAgentTurnPolicyChange = (policy: AgentTurnPolicy) => {
    setAgentTurnPolicy(policy)
    writeAgentTurnPolicy(policy)
  }

  const visibleNavItems = NAV_ITEMS.filter(
    (item) =>
      (!item.requiresMembers || viewer.canManageMembers) &&
      (!item.requiresRegistryAdmin || canManageRegistries),
  )
  const lightTokens = appearancePresets[lightPreset].light
  const darkTokens = appearancePresets[darkPreset].dark

  return (
    <div className="flex h-full min-w-0 flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      {/* ── Sub-sidebar ──────────────────────────────────── */}
      <nav className="w-full shrink-0 border-b border-border/60 bg-secondary/30 p-4 md:w-[200px] md:border-b-0 md:border-r">
        <h2 className="mb-4 text-lg font-semibold tracking-tight text-foreground">
          {t("pageTitle")}
        </h2>
        <ul className="grid grid-cols-2 gap-1 md:block md:space-y-0.5">
          {visibleNavItems.map((item) => {
            const Icon = item.icon
            return (
              <li key={item.key}>
                <button
                  type="button"
                  onClick={() => {
                    setActiveSection(item.key)
                    if (typeof window !== "undefined") {
                      const url = new URL(window.location.href)
                      if (item.key === "account") {
                        url.searchParams.delete("section")
                      } else {
                        url.searchParams.set("section", item.key)
                      }
                      window.history.replaceState(null, "", `${url.pathname}${url.search}`)
                    }
                  }}
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
      <div className="min-w-0 flex-1 overflow-y-visible md:overflow-y-auto">
        <div
          className={cn(
            "mx-auto w-full space-y-6 p-4 sm:p-6",
            activeSection === "appearance" ||
              activeSection === "providers" ||
              activeSection === "registries"
              ? "max-w-5xl"
              : "max-w-2xl",
          )}
        >
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

          {activeSection === "appearance" && (
            <>
              <div>
                <h3 className="text-base font-semibold text-foreground">
                  {t("appearance.title")}
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t("appearance.description")}
                </p>
              </div>

              <div className="space-y-4 rounded-2xl border border-border/60 bg-card p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {t("appearance.mode")}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t("appearance.activePreset", {
                        preset: appearancePresets[activePreset].label,
                      })}
                    </p>
                  </div>

                  <Tabs
                    value={mode}
                    onValueChange={(value) =>
                      setMode(value as "light" | "dark" | "system")
                    }
                    className="w-full lg:w-auto"
                  >
                    <TabsList className="grid w-full grid-cols-3 lg:w-[280px]">
                      <TabsTrigger value="light" className="gap-2">
                        <Sun className="size-3.5" />
                        {t("appearance.modes.light")}
                      </TabsTrigger>
                      <TabsTrigger value="dark" className="gap-2">
                        <Moon className="size-3.5" />
                        {t("appearance.modes.dark")}
                      </TabsTrigger>
                      <TabsTrigger value="system" className="gap-2">
                        <Monitor className="size-3.5" />
                        {t("appearance.modes.system")}
                      </TabsTrigger>
                    </TabsList>
                  </Tabs>
                </div>

                <div className="grid gap-4 xl:grid-cols-2">
                  <ThemePreviewCard
                    title={t("appearance.preview.light")}
                    mode="light"
                    modeLabel={t("appearance.modes.light")}
                    presetLabel={appearancePresets[lightPreset].label}
                    tokens={lightTokens}
                  />
                  <ThemePreviewCard
                    title={t("appearance.preview.dark")}
                    mode="dark"
                    modeLabel={t("appearance.modes.dark")}
                    presetLabel={appearancePresets[darkPreset].label}
                    tokens={darkTokens}
                  />
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>{t("appearance.presets.light")}</Label>
                    <Select value={lightPreset} onValueChange={(value) => setLightPreset(value as typeof lightPreset)}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t("appearance.presets.light")} />
                      </SelectTrigger>
                      <SelectContent>
                        {appearancePresetIds.map((presetId) => (
                          <SelectItem key={`light-${presetId}`} value={presetId}>
                            {appearancePresets[presetId].label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>{t("appearance.presets.dark")}</Label>
                    <Select value={darkPreset} onValueChange={(value) => setDarkPreset(value as typeof darkPreset)}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t("appearance.presets.dark")} />
                      </SelectTrigger>
                      <SelectContent>
                        {appearancePresetIds.map((presetId) => (
                          <SelectItem key={`dark-${presetId}`} value={presetId}>
                            {appearancePresets[presetId].label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="rounded-[24px] border border-border/70 bg-secondary/35 p-4">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="flex items-start gap-3">
                      <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-primary/12 text-primary">
                        <PartyPopper className="size-5" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-foreground">
                            {t("appearance.celebrations.title")}
                          </p>
                          <span className="rounded-full border border-border/70 bg-background px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                            {celebrationsEnabled
                              ? t("appearance.celebrations.enabledLabel")
                              : t("appearance.celebrations.disabledLabel")}
                          </span>
                        </div>
                        <p
                          id="celebrations-description"
                          className="max-w-2xl text-sm leading-6 text-muted-foreground"
                        >
                          {t("appearance.celebrations.description")}
                        </p>
                        {reducedMotion ? (
                          <p
                            id="celebrations-reduced-motion"
                            className="text-xs text-muted-foreground"
                          >
                            {t("appearance.celebrations.reducedMotion")}
                          </p>
                        ) : null}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-3 lg:justify-end">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          celebratePreview()
                        }}
                        disabled={!celebrationsEnabled || reducedMotion}
                      >
                        <PartyPopper className="size-4" />
                        {t("appearance.celebrations.preview")}
                      </Button>
                      <Switch
                        aria-label={t("appearance.celebrations.title")}
                        aria-describedby={
                          reducedMotion
                            ? "celebrations-description celebrations-reduced-motion"
                            : "celebrations-description"
                        }
                        checked={celebrationsEnabled}
                        onCheckedChange={(checked) =>
                          persistCelebrationsEnabled(Boolean(checked))
                        }
                      />
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeSection === "agent" && (
            <>
              <div>
                <h3 className="text-base font-semibold text-foreground">
                  {t("agent.title")}
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t("agent.description")}
                </p>
              </div>

              <div className="space-y-4 rounded-2xl border border-border/60 bg-card p-4">
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {t("agent.turnPolicy.label")}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    {t("agent.turnPolicy.description")}
                  </p>
                </div>

                <div
                  role="radiogroup"
                  aria-label={t("agent.turnPolicy.label")}
                  className="grid gap-2 sm:grid-cols-2"
                >
                  {AGENT_TURN_POLICIES.map((policy) => {
                    const selected = agentTurnPolicy === policy
                    return (
                      <button
                        key={policy}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() => handleAgentTurnPolicyChange(policy)}
                        className={cn(
                          "rounded-xl border px-3.5 py-3 text-left transition-colors",
                          selected
                            ? "border-primary/55 bg-primary/10 text-foreground"
                            : "border-border/60 bg-secondary/25 text-muted-foreground hover:bg-secondary/45 hover:text-foreground",
                        )}
                      >
                        <span className="block text-sm font-semibold">
                          {t(`agent.turnPolicy.options.${policy}.label`)}
                        </span>
                        <span className="mt-1 block text-xs leading-5">
                          {t(`agent.turnPolicy.options.${policy}.description`)}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            </>
          )}

          {/* ── AI Providers Section ───────────────────── */}
          {activeSection === "providers" && (
            <>
              <div>
                <h3 className="text-base font-semibold text-foreground">{t("title")}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
              </div>

              <LlmCatalogPanel />
            </>
          )}

          {/* ── Container Registries Section ───────────── */}
          {activeSection === "registries" && canManageRegistries && (
            <ContainerRegistriesPanel />
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

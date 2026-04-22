import Link from "next/link"
import { headers } from "next/headers"
import { redirect } from "next/navigation"
import { ChevronRight, GitBranch, LockKeyhole, MessageSquare, Shield, Sparkles } from "lucide-react"
import { Logo } from "@/components/bioinfoflow/logo"
import { getTranslations } from "next-intl/server"
import { AuthActions } from "@/components/auth/auth-actions"
import { EmailSignInForm } from "@/components/auth/email-sign-in-form"
import { ensureAuthReady, getAuth } from "@/lib/auth"
import { authProviderStatus, getServerAuthConfig } from "@/lib/auth-config"

const TEAM_ROLES = ["owner", "admin", "member"] as const

export default async function AuthPage() {
  const t = await getTranslations("auth")
  const authConfig = getServerAuthConfig()

  if (!authConfig.authEnabled) {
    redirect("/agent")
  }

  await ensureAuthReady()
  const auth = await getAuth()
  const session = auth
    ? await auth.api.getSession({
        headers: await headers(),
      })
    : null

  if (session) {
    redirect("/agent")
  }

  const isTeamMode = authConfig.mode === "team"
  const modeBadge = t(`badges.${authConfig.mode}`)

  return (
    <main className="relative min-h-dvh overflow-auto bg-[radial-gradient(circle_at_top_left,_rgba(28,90,78,0.12),_transparent_30%),radial-gradient(circle_at_top_right,_rgba(231,211,167,0.26),_transparent_34%),linear-gradient(180deg,_#f7f5ef_0%,_#efe6d5_46%,_#f6f2e8_100%)] text-slate-900">
      {/* ── Logo — anchored to top-left ──────────────── */}
      <Link href="/" className="absolute left-4 top-4 z-10 inline-flex items-center gap-2.5 sm:left-6 lg:left-8">
        <Logo size={34} />
        <span className="text-[15px] font-semibold tracking-tight text-slate-800">
          Bioinfoflow
        </span>
      </Link>

      <div
        className={[
          "mx-auto grid min-h-dvh w-full max-w-[1180px] gap-6 px-4 pb-6 pt-16 sm:px-6 sm:pt-20 lg:px-8 lg:pb-5 lg:pt-5",
          isTeamMode
            ? "items-stretch lg:grid-cols-[minmax(0,430px)_minmax(0,1fr)]"
            : "items-center",
        ].join(" ")}
      >
        <section className={[
          "mx-auto flex w-full max-w-[430px] flex-col",
          isTeamMode ? "lg:max-w-none" : "justify-center",
        ].join(" ")}>

          <div className={[
            "overflow-hidden rounded-2xl border border-white/80 bg-white/92 shadow-[0_22px_60px_rgba(15,23,42,0.09)] backdrop-blur sm:rounded-[28px]",
            isTeamMode ? "flex flex-1 flex-col" : "",
          ].join(" ")}>
            {/* ── Header ─────────────────────────────────── */}
            <div className="px-4 pb-2 pt-5 sm:px-6">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <div className="inline-flex items-center gap-1.5 rounded-full border border-emerald-900/10 bg-emerald-950 px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-emerald-50">
                  <Shield className="h-2.5 w-2.5" />
                  {modeBadge}
                </div>
                <span className="truncate text-[10px] font-medium uppercase tracking-[0.14em] text-slate-400">
                  {authConfig.workspaceName}
                </span>
              </div>

              <h1 className="text-[1.4rem] font-semibold leading-tight tracking-tight text-slate-950 sm:text-[1.85rem] sm:leading-[1.08]">
                {t("title")}
              </h1>
              <p className="mt-1.5 max-w-xl text-[13px] leading-[1.6] text-slate-500">
                {isTeamMode
                  ? t("description")
                  : t("local.personalProvisioned")}
              </p>
            </div>

            {/* ── Form ───────────────────────────────────── */}
            <div className={[
              "flex flex-col space-y-3 px-4 pt-3 sm:px-6",
              isTeamMode ? "flex-1 justify-center pb-4" : "pb-5",
            ].join(" ")}>
              {authConfig.authLocalEnabled ? (
                <EmailSignInForm />
              ) : null}

              {(authProviderStatus.github || authProviderStatus.google) && (
                <div className="space-y-3">
                  {authConfig.authLocalEnabled && (
                    <div className="relative">
                      <div className="absolute inset-0 flex items-center">
                        <span className="w-full border-t border-slate-200" />
                      </div>
                      <div className="relative flex justify-center text-xs uppercase">
                        <span className="bg-white px-2 text-slate-500">{t("oauthDivider")}</span>
                      </div>
                    </div>
                  )}
                  <AuthActions providers={authProviderStatus} />
                </div>
              )}

              {!authConfig.authLocalEnabled && !authProviderStatus.github && !authProviderStatus.google && (
                <p className="rounded-2xl border border-amber-500/20 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  {t("noProviders")}
                </p>
              )}

              <p className="text-[11px] leading-5 text-slate-400">{t("terms")}</p>
            </div>

            {/* ── Hint / provisioning note ─────────────── */}
            <div className="mt-auto px-4 pb-5 sm:px-6">
              {isTeamMode ? (
                <p className="rounded-xl bg-slate-50/80 px-3.5 py-2.5 text-xs leading-5 text-slate-500">
                  {t("local.adminProvisioned")}
                </p>
              ) : (
                <div className="flex items-center gap-3 rounded-xl bg-slate-50/80 px-3.5 py-3">
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-emerald-100/80 text-emerald-700">
                    <LockKeyhole className="size-3.5" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-slate-800">
                      {t("preview.personalTitle")}
                    </p>
                    <p className="mt-0.5 text-[11px] leading-4 text-slate-500">
                      {t("preview.personalDescription")}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>

        {isTeamMode ? (
          <aside className="relative hidden overflow-hidden rounded-[32px] border border-emerald-950/12 bg-[#112520] p-5 text-white shadow-[0_28px_80px_rgba(16,33,29,0.22)] lg:flex lg:flex-col xl:p-6">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,_rgba(125,211,252,0.10),_transparent_30%),radial-gradient(circle_at_bottom_left,_rgba(110,231,183,0.14),_transparent_26%),linear-gradient(180deg,_rgba(255,255,255,0.02),_rgba(0,0,0,0.05))]" />
            <div className="relative flex h-full flex-col">
              <div className="max-w-2xl space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-[0.28em] text-emerald-300/70">
                  {t("preview.eyebrow")}
                </p>
                <h2 className="max-w-[16ch] text-[1.85rem] font-semibold tracking-tight text-white xl:text-[2.2rem] xl:leading-[1.06]">
                  {t("preview.title")}
                </h2>
                <p className="max-w-2xl text-[13px] leading-6 text-slate-400">
                  {t("preview.description")}
                </p>
              </div>

              {/* ── Bento grid ─────────────────────────────── */}
              <div className="mt-5 grid flex-1 gap-3 xl:grid-cols-[minmax(0,1.15fr)_minmax(230px,0.85fr)]">
                {/* Left column: chat context card */}
                <div className="flex flex-col gap-3">
                  <div className="flex flex-1 flex-col rounded-[22px] border border-white/10 bg-white/[0.05] p-4 backdrop-blur">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                        {t("preview.chatLabel")}
                      </p>
                      <div className="rounded-full bg-emerald-400/12 px-2.5 py-0.5 text-[9px] font-medium uppercase tracking-[0.16em] text-emerald-200/80">
                        {t("preview.workspaceShared")}
                      </div>
                    </div>
                    <p className="mb-4 text-[15px] font-medium leading-snug text-white/90">
                      {t("preview.chatTitle")}
                    </p>

                    <div className="mt-auto space-y-2.5 rounded-[18px] border border-white/8 bg-[#0b1714] p-3.5">
                      {/* Turn 1: User message */}
                      <div className="flex items-start gap-2.5">
                        <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-white text-slate-900">
                          <MessageSquare className="size-3.5" />
                        </div>
                        <div className="rounded-2xl rounded-tl-sm bg-white/8 px-3.5 py-2.5 text-[13px] leading-5 text-slate-300">
                          {t("preview.chatExample")}
                        </div>
                      </div>

                      {/* Turn 2: Agent response */}
                      <div className="flex items-start gap-2.5">
                        <div className="flex size-8 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-emerald-200/10 text-emerald-200">
                          <Sparkles className="size-3.5" />
                        </div>
                        <div className="rounded-2xl rounded-tl-sm bg-emerald-200/6 px-3.5 py-2.5 text-[13px] leading-5 text-emerald-100/80">
                          {t("preview.chatAgent1")}
                        </div>
                      </div>

                      {/* Turn 3: User follow-up */}
                      <div className="flex items-start gap-2.5">
                        <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-white text-slate-900">
                          <MessageSquare className="size-3.5" />
                        </div>
                        <div className="rounded-2xl rounded-tl-sm bg-white/8 px-3.5 py-2.5 text-[13px] leading-5 text-slate-300">
                          {t("preview.chatUser2")}
                        </div>
                      </div>

                      {/* Turn 4: Agent planning workflow */}
                      <div className="flex items-start gap-2.5">
                        <div className="flex size-8 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-emerald-200/10 text-emerald-200">
                          <GitBranch className="size-3.5" />
                        </div>
                        <div className="flex-1 space-y-2 rounded-2xl rounded-tl-sm border border-white/8 bg-emerald-200/6 px-3.5 py-3">
                          <div className="flex items-center justify-between gap-3 text-[13px]">
                            <span className="font-medium text-white/90">
                              {t("preview.planningWorkflow")}
                            </span>
                            <span className="rounded-full border border-white/10 px-2.5 py-0.5 text-[9px] uppercase tracking-[0.14em] text-emerald-200/70">
                              {t("preview.audit")}
                            </span>
                          </div>
                          <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-emerald-100/80">
                            <span className="rounded-full bg-white/8 px-2.5 py-1">
                              fastqc
                            </span>
                            <ChevronRight className="size-2.5 text-emerald-200/40" />
                            <span className="rounded-full bg-white/8 px-2.5 py-1">
                              star
                            </span>
                            <ChevronRight className="size-2.5 text-emerald-200/40" />
                            <span className="rounded-full bg-emerald-300/15 px-2.5 py-1">
                              deseq2
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Mobile roles grid */}
                  <div className="grid gap-2.5 sm:grid-cols-3 xl:hidden">
                    {TEAM_ROLES.map((role) => (
                      <div
                        key={role}
                        className="rounded-[18px] border border-white/10 bg-white/[0.05] p-3"
                      >
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <p className="text-[13px] font-medium text-white">
                            {t(`preview.roles.${role}.name`)}
                          </p>
                          <span className="rounded-full border border-white/10 px-2 py-0.5 text-[8px] uppercase tracking-[0.18em] text-slate-300">
                            {role}
                          </span>
                        </div>
                        <p className="text-[11px] leading-4 text-slate-400">
                          {t(`preview.roles.${role}.description`)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Right column: team roles card */}
                <div className="hidden rounded-[22px] border border-white/10 bg-white/[0.05] p-4 backdrop-blur xl:flex xl:flex-col">
                  <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                    {t("preview.membersLabel")}
                  </p>
                  <div className="flex flex-1 flex-col gap-2.5">
                    {TEAM_ROLES.map((role) => (
                      <div
                        key={role}
                        className="flex flex-1 flex-col rounded-[16px] border border-white/8 bg-black/14 px-3.5 py-3"
                      >
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <p className="text-[13px] font-semibold text-white">
                            {t(`preview.roles.${role}.name`)}
                          </p>
                          <span className="rounded-full border border-white/10 px-2.5 py-0.5 text-[8px] uppercase tracking-[0.16em] text-slate-300/80">
                            {role}
                          </span>
                        </div>
                        <p className="text-[11px] leading-[1.5] text-slate-400">
                          {t(`preview.roles.${role}.description`)}
                        </p>
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 border-t border-white/8 pt-3 text-[12px] leading-5 text-slate-400/80">
                    {t("preview.tagline")}
                  </p>
                </div>
              </div>
            </div>
          </aside>
        ) : null}
      </div>
    </main>
  )
}

import Link from "next/link"
import { cookies, headers } from "next/headers"
import { redirect } from "next/navigation"
import { Shield } from "@/lib/icons"
import { Logo } from "@/components/bioinfoflow/logo"
import { getTranslations } from "next-intl/server"
import { AuthActions } from "@/components/auth/auth-actions"
import { DemoAuthScreen } from "@/components/auth/demo-auth-screen"
import { EmailSignInForm } from "@/components/auth/email-sign-in-form"
import { ensureAuthReady, getAuth } from "@/lib/auth"
import { authProviderStatus, getServerAuthConfig } from "@/lib/auth-config"
import { DEMO_ACCESS_COOKIE, isDemoDeployment } from "@/lib/demo-auth"

export default async function AuthPage() {
  const t = await getTranslations("auth")
  const authConfig = getServerAuthConfig()
  const demoMode = isDemoDeployment()
  const cookieStore = await cookies()
  const hasDemoAccess = Boolean(cookieStore.get(DEMO_ACCESS_COOKIE)?.value)

  if (demoMode && !authConfig.authEnabled) {
    if (hasDemoAccess) {
      redirect("/")
    }

    return (
      <DemoAuthScreen
        t={t}
        workspaceName={authConfig.workspaceName}
      />
    )
  }

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
        className="mx-auto grid min-h-dvh w-full max-w-[1180px] items-center gap-6 px-4 pb-6 pt-16 sm:px-6 sm:pt-20 lg:px-8 lg:pb-5 lg:pt-5"
      >
        <section className="mx-auto flex w-full max-w-[430px] flex-col justify-center">

          <div className="overflow-hidden rounded-2xl border border-white/80 bg-white/92 shadow-[0_22px_60px_rgba(15,23,42,0.09)] backdrop-blur sm:rounded-[28px]">
            {/* ── Header ─────────────────────────────────── */}
            <div className="px-4 pb-2 pt-5 sm:px-6">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <div className="inline-flex items-center gap-1.5 rounded-full border border-success-border bg-success-muted px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-success-foreground">
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
            </div>

            {/* ── Form ───────────────────────────────────── */}
            <div className="flex flex-col space-y-3 px-4 pb-5 pt-3 sm:px-6">
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
          </div>
        </section>
      </div>
    </main>
  )
}

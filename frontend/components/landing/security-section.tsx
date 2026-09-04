"use client"

import { Check, Database, FileCheck, ShieldCheck } from "@/lib/icons"
import { useTranslations } from "next-intl"

const proofPoints = [
  { key: "dataControl", icon: Database },
  { key: "approval", icon: ShieldCheck },
  { key: "traceability", icon: FileCheck },
] as const

export function SecuritySection() {
  const t = useTranslations("landing.security")

  return (
    <section id="security" className="landing-security px-5 py-28 md:px-8 md:py-40">
      <div className="mx-auto max-w-7xl">
        <div className="landing-narrative-layout grid gap-14">
          <div className="xl:sticky xl:top-32 xl:self-start">
            <p className="landing-section-kicker">{t("badge")}</p>
            <h2 className="mt-5 max-w-xl text-3xl font-medium tracking-[-0.045em] md:text-5xl xl:text-6xl">
              <span className="block">{t("titleLead")}</span>
              <span className="block">{t("titleRest")}</span>
            </h2>
            <p className="mt-6 max-w-lg text-base leading-7 text-muted-foreground">
              {t("subtitle")}
            </p>
          </div>

          <div className="landing-evidence-surface border border-border bg-background">
            <div className="landing-evidence-header">
              <p className="font-mono text-[0.65rem] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                {t("boundaryLabel")}
              </p>
              <p className="text-sm text-foreground/70">{t("boundaryStatus")}</p>
            </div>
            <div className="landing-evidence-list">
              {proofPoints.map((item) => (
                <article
                  key={item.key}
                  className="landing-evidence-row group grid gap-5 border-b border-border p-6 last:border-b-0 sm:grid-cols-[2.75rem_minmax(0,1fr)] sm:p-8"
                >
                  <div className="landing-evidence-mark flex size-11 items-center justify-center border border-border bg-secondary/45">
                    <item.icon className="size-4.5 text-foreground" strokeWidth={1.6} />
                  </div>
                  <div>
                    <h3 className="text-lg font-medium tracking-tight md:text-xl">
                      {t(`${item.key}.title`)}
                    </h3>
                    <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground md:text-base md:leading-7">
                      {t(`${item.key}.description`)}
                    </p>
                    <p className="landing-evidence-proof mt-5 inline-flex items-center gap-2 text-xs font-medium text-foreground">
                      <Check className="size-3.5 text-[var(--brand-accent)]" />
                      {t(`${item.key}.proof`)}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

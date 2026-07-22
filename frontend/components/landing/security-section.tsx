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
        <div className="grid gap-14 lg:grid-cols-[0.82fr_1.18fr] lg:gap-24">
          <div className="lg:sticky lg:top-32 lg:self-start">
            <p className="mb-5 text-sm font-medium text-[var(--brand-accent)]">{t("badge")}</p>
            <h2 className="max-w-xl text-balance text-3xl font-medium tracking-[-0.04em] md:text-6xl">
              {t("title")}
            </h2>
            <p className="mt-6 max-w-lg text-base leading-7 text-muted-foreground">
              {t("subtitle")}
            </p>
          </div>

          <div className="landing-evidence-panel overflow-hidden rounded-xl border border-border bg-background shadow-[var(--landing-shadow-soft)]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-secondary/35 px-5 py-4">
              <span className="font-mono text-[0.65rem] uppercase tracking-[0.14em] text-muted-foreground">
                {t("boundaryLabel")}
              </span>
              <span className="inline-flex items-center gap-2 text-xs text-foreground/70">
                <span className="size-1.5 rounded-full bg-[var(--brand-accent)]" />
                {t("boundaryStatus")}
              </span>
            </div>
            {proofPoints.map((item, index) => (
              <article
                key={item.key}
                className="group grid gap-5 border-b border-border p-6 last:border-b-0 sm:grid-cols-[3.5rem_1fr] sm:p-8"
              >
                <div className="flex size-11 items-center justify-center rounded-md border border-border bg-secondary/45 transition-colors duration-300 group-hover:bg-[var(--brand-accent-muted)]">
                  <item.icon className="size-4.5 text-foreground" strokeWidth={1.6} />
                </div>
                <div>
                  <div className="flex items-baseline justify-between gap-6">
                    <h3 className="text-lg font-medium tracking-tight md:text-xl">
                      {t(`${item.key}.title`)}
                    </h3>
                    <span className="font-mono text-[0.65rem] text-muted-foreground">
                      0{index + 1}
                    </span>
                  </div>
                  <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground md:text-base md:leading-7">
                    {t(`${item.key}.description`)}
                  </p>
                  <p className="mt-5 inline-flex items-center gap-2 rounded-sm bg-secondary/45 px-2.5 py-1.5 text-xs font-medium text-foreground">
                    <Check className="size-3.5 text-[var(--brand-accent)]" />
                    {t(`${item.key}.proof`)}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

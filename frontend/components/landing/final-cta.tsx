"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ArrowRight } from "@/lib/icons"
import { useTranslations } from "next-intl"

export function FinalCTA() {
  const t = useTranslations("landing.cta")

  return (
    <section className="landing-final-cta px-5 pb-14 pt-24 text-[var(--landing-cta-fg)] md:px-8 md:pb-20 md:pt-36">
      <div className="mx-auto max-w-7xl">
        <div className="border-b border-white/12 pb-16 md:pb-24">
          <h2 className="max-w-6xl text-4xl font-medium leading-[0.98] tracking-[-0.06em] md:text-7xl">
            <span className="block">{t("titleLead")}</span>
            <span className="mt-1 block text-[color-mix(in_srgb,var(--landing-cta-fg)_82%,transparent)] md:mt-2">
              {t("titleRest")}
            </span>
          </h2>

          <div className="mt-9 grid gap-7 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end md:mt-12">
            <p className="max-w-xl text-base leading-7 text-[color-mix(in_srgb,var(--landing-cta-fg)_62%,transparent)]">
              {t("subtitle")}
            </p>
            <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
              <Button
                asChild
                size="lg"
                className="group w-full gap-2 rounded-md bg-[var(--landing-cta-fg)] px-5 text-[var(--landing-cta-bg)] shadow-none hover:bg-[var(--landing-cta-fg)] hover:opacity-90 active:translate-y-px sm:w-auto"
              >
                <Link href="/auth">
                  {t("getStarted")}
                  <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
                </Link>
              </Button>
              <Button
                variant="outline"
                size="lg"
                className="w-full rounded-md border-current/20 bg-transparent px-5 text-[var(--landing-cta-fg)] hover:bg-white/10 hover:text-[var(--landing-cta-fg)] sm:w-auto"
                asChild
              >
                <Link href="mailto:hello@bioinfoflow.io">{t("contactUs")}</Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

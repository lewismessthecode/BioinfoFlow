"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ArrowRight } from "@/lib/icons"
import { useTranslations } from "next-intl"

export function FinalCTA() {
  const t = useTranslations("landing.cta")

  return (
    <section className="landing-final-cta landing-footer-shell bg-[var(--landing-cta-bg)] px-5 pb-14 pt-24 text-[var(--landing-cta-fg)] md:px-8 md:pb-20 md:pt-36">
      <div className="mx-auto max-w-7xl">
        <div className="grid gap-12 border-b border-white/12 pb-16 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end md:pb-24">
          <div>
            <p className="mb-6 max-w-xl text-sm font-medium text-[var(--brand-accent)]">{t("eyebrow")}</p>
            <h2 className="max-w-5xl text-balance text-4xl font-medium leading-[0.98] tracking-[-0.055em] md:text-7xl">
              {t("title")}
            </h2>
            <p className="mt-7 max-w-xl text-base leading-7 opacity-55">
              {t("subtitle")}
            </p>
          </div>

          <div className="flex flex-wrap gap-3 lg:justify-end lg:pb-1">
            <Button asChild size="lg" className="group gap-2 rounded-md bg-[var(--landing-cta-fg)] px-5 text-[var(--landing-cta-bg)] shadow-none hover:bg-[var(--landing-cta-fg)] hover:opacity-90 active:translate-y-px">
              <Link href="/auth">
                {t("getStarted")}
                <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </Button>
            <Button
              variant="outline"
              size="lg"
              className="rounded-md border-current/20 bg-transparent px-5 text-[var(--landing-cta-fg)] hover:bg-white/10 hover:text-[var(--landing-cta-fg)]"
              asChild
            >
              <Link href="mailto:hello@bioinfoflow.io">
                {t("contactUs")}
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
}

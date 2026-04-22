"use client"

import { useTranslations } from "next-intl"

export function QuoteSection() {
  const t = useTranslations("landing.quote")

  return (
    <section className="section-padding bg-secondary/30 relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="max-w-3xl mx-auto text-center">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-6 font-medium">
            {t("label")}
          </p>
          <p className="text-2xl md:text-3xl lg:text-4xl font-semibold tracking-tight leading-tight text-balance">
            {t("text")}
          </p>
        </div>
      </div>
    </section>
  )
}

"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ArrowRight } from "lucide-react"
import { useTranslations } from "next-intl"

export function FinalCTA() {
  const t = useTranslations("landing.cta")

  return (
    <section className="section-padding bg-background border-t border-border">
      <div className="container mx-auto px-6">
        <div className="max-w-xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-semibold tracking-tight mb-4">
            {t("title")}
          </h2>
          <p className="text-muted-foreground text-base md:text-lg mb-8">
            {t("subtitle")}
          </p>

          <div className="flex flex-wrap justify-center gap-3">
            <Button asChild size="lg" className="rounded-full px-6 gap-2 group">
              <Link href="/auth">
                {t("getStarted")}
                <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </Button>
            <Button
              variant="outline"
              size="lg"
              className="rounded-full px-6"
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

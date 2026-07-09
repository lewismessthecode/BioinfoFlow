"use client"

import { Check } from "@/lib/icons"
import { FadeInOnScroll, StaggerContainer, StaggerItem } from "@/components/ui/scroll-animations"
import { useTranslations } from "next-intl"

export function ResultsSection() {
  const t = useTranslations("landing.results")

  const capabilities = [
    {
      title: t("wgsSpeed.title"),
      description: t("wgsSpeed.description")
    },
    {
      title: t("nlp.title"),
      description: t("nlp.description")
    },
    {
      title: t("zeroData.title"),
      description: t("zeroData.description")
    },
    {
      title: t("provenance.title"),
      description: t("provenance.description")
    },
  ]

  return (
    <section className="section-padding bg-background">
      <div className="container mx-auto px-6">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center max-w-5xl mx-auto">
          {/* Left: Capabilities */}
          <div>
            <FadeInOnScroll>
              <h2 className="text-3xl md:text-4xl font-semibold tracking-tight mb-4">
                {t("title")}
              </h2>
              <p className="text-muted-foreground text-lg mb-10">
                {t("subtitle")}
              </p>
            </FadeInOnScroll>

            <StaggerContainer className="space-y-6" staggerDelay={0.12}>
              {capabilities.map((item) => (
                <StaggerItem key={item.title}>
                  <div className="flex gap-4">
                    <div className="w-6 h-6 rounded-full bg-foreground flex items-center justify-center shrink-0 mt-0.5">
                      <Check className="w-3.5 h-3.5 text-background" />
                    </div>
                    <div>
                      <h3 className="font-medium mb-1">{item.title}</h3>
                      <p className="text-sm text-muted-foreground leading-relaxed">{item.description}</p>
                    </div>
                  </div>
                </StaggerItem>
              ))}
            </StaggerContainer>
          </div>

          {/* Right: Comparison */}
          <FadeInOnScroll delay={0.2} direction="left">
            <div className="bg-card border border-border rounded-xl p-6 lg:p-8 shadow-sm">
              <div className="text-sm font-medium text-muted-foreground mb-6">{t("comparison.title")}</div>

              {/* Simple bar comparison */}
              <div className="space-y-6">
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-muted-foreground">{t("comparison.manual")}</span>
                    <span className="font-mono text-xs">{t("comparison.manualTime")}</span>
                  </div>
                  <div className="h-3 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full w-full bg-muted-foreground/30 rounded-full" />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-foreground font-medium">{t("comparison.withBioinfoflow")}</span>
                    <span className="font-mono text-xs">{t("comparison.withBioinfoflowTime")}</span>
                  </div>
                  <div className="h-3 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full w-[8%] bg-foreground rounded-full" />
                  </div>
                </div>
              </div>

              <div className="mt-8 pt-6 border-t border-border">
                <p className="text-xs text-muted-foreground">
                  {t("comparison.note")}
                </p>
              </div>
            </div>
          </FadeInOnScroll>
        </div>
      </div>
    </section>
  )
}

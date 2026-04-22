"use client"

import { Dna, FlaskConical, Microscope, Layers, Bug } from "lucide-react"
import { FadeInOnScroll, StaggerContainer, StaggerItem } from "@/components/ui/scroll-animations"
import { useTranslations } from "next-intl"

export function TrustBar() {
  const t = useTranslations("landing.trustBar")

  const useCases = [
    { label: t("rnaseq"), icon: Dna },
    { label: t("chipseq"), icon: Layers },
    { label: t("variantCalling"), icon: FlaskConical },
    { label: t("singleCell"), icon: Microscope },
    { label: t("metagenomics"), icon: Bug },
  ]

  return (
    <section className="relative py-10 md:py-12 bg-secondary/20 gradient-fade-border-top gradient-fade-border-bottom">
      <div className="container mx-auto px-6">
        <FadeInOnScroll>
          <p className="text-center text-xs uppercase tracking-[0.2em] text-muted-foreground mb-6 font-medium">
            {t("builtFor")}
          </p>
        </FadeInOnScroll>
        <StaggerContainer
          className="flex flex-wrap justify-center items-center gap-6 md:gap-10"
          staggerDelay={0.06}
        >
          {useCases.map((useCase) => (
            <StaggerItem key={useCase.label}>
              <div className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors duration-200">
                <useCase.icon className="w-4 h-4" />
                <span className="text-sm md:text-base font-medium">{useCase.label}</span>
              </div>
            </StaggerItem>
          ))}
        </StaggerContainer>
      </div>
    </section>
  )
}


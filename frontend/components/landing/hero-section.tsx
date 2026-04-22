"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ArrowRight, Play, MessageSquare, GitBranch, ChevronRight, Cpu } from "lucide-react"
import { FadeInOnScroll } from "@/components/ui/scroll-animations"
import { useTranslations } from "next-intl"

export function HeroSection() {
  const t = useTranslations("landing.hero")

  return (
    <section className="relative min-h-[80vh] flex items-center dot-grid">
      <div className="container mx-auto px-6 py-20 md:py-32">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          {/* Left: Text Content */}
          <div className="max-w-xl">
            <FadeInOnScroll delay={0}>
              <div className="flex items-center gap-2 mb-4">
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gradient-to-r from-green-500/10 to-emerald-500/10 border border-green-500/20 text-green-600 dark:text-green-400 text-xs font-medium">
                  <Cpu className="w-3 h-3" />
                  {t("gpuPowered")}
                </span>
                <p className="text-sm text-muted-foreground font-medium tracking-wide">
                  {t("tagline")}
                </p>
              </div>
            </FadeInOnScroll>

            <FadeInOnScroll delay={0.1}>
              <h1 className="text-4xl md:text-5xl lg:text-6xl font-semibold tracking-tight leading-[1.1] text-balance mb-6">
                <span className="highlight-marker whitespace-nowrap">{t("title")}</span>{" "}
                <span className="nowrap">{t("titleSuffix")}</span>
              </h1>
            </FadeInOnScroll>

            <FadeInOnScroll delay={0.2}>
              <p className="text-lg md:text-xl text-muted-foreground leading-relaxed mb-2 max-w-lg">
                {t("description")}
              </p>
              <p className="text-base text-foreground/80 font-medium mb-8 max-w-lg">
                {t("wgsHighlight")}
              </p>
            </FadeInOnScroll>

            <FadeInOnScroll delay={0.3}>
              <div className="flex flex-wrap gap-4">
                <Button asChild size="lg" className="rounded-full px-6 gap-2 group">
                  <Link href="/auth">
                    {t("startFree")}
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </Link>
                </Button>
                <Button
                  variant="outline"
                  size="lg"
                  className="rounded-full px-6 gap-2 bg-transparent"
                >
                  <Play className="w-4 h-4" />
                  {t("bookDemo")}
                </Button>
              </div>
            </FadeInOnScroll>
          </div>

          {/* Right: Product Preview */}
          <FadeInOnScroll delay={0.2} direction="left">
            <div className="relative">
              {/* Main Preview Card */}
              <div className="bg-card border border-border rounded-xl shadow-[0_8px_24px_rgba(0,0,0,0.06)] overflow-hidden">
                {/* Window Header */}
                <div className="h-10 bg-secondary/50 border-b border-border flex items-center px-4 gap-2">
                  <div className="flex gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-border" />
                    <div className="w-3 h-3 rounded-full bg-border" />
                    <div className="w-3 h-3 rounded-full bg-border" />
                  </div>
                  <span className="text-xs text-muted-foreground ml-2 font-mono">{t("windowTitle")}</span>
                </div>

                {/* Content */}
                <div className="p-6 space-y-4">
                  {/* Chat Message */}
                  <div className="flex gap-3">
                    <div className="w-8 h-8 rounded-full bg-foreground flex items-center justify-center shrink-0">
                      <MessageSquare className="w-4 h-4 text-background" />
                    </div>
                    <div className="bg-secondary rounded-lg p-3 text-sm">
                      <p className="text-muted-foreground">{t("chatExample")}</p>
                    </div>
                  </div>

                  {/* Agent Response */}
                  <div className="flex gap-3">
                    <div className="w-8 h-8 rounded-lg bg-secondary border border-border flex items-center justify-center shrink-0">
                      <GitBranch className="w-4 h-4 text-foreground" />
                    </div>
                    <div className="space-y-3 flex-1">
                      <div className="text-sm">
                        <p className="font-medium mb-1">{t("planningWorkflow")}</p>
                        <p className="text-muted-foreground text-xs">{t("workflowDescription")}</p>
                      </div>

                      {/* Mini DAG - WGS Pipeline */}
                      <div className="bg-secondary/50 rounded-lg p-3 border border-border">
                        <div className="flex items-center gap-2 text-xs">
                          <div className="px-2 py-1 bg-background rounded border border-border font-mono">FASTQ</div>
                          <ChevronRight className="w-3 h-3 text-muted-foreground" />
                          <div className="px-2 py-1 bg-background rounded border border-border font-mono">fq2bam</div>
                          <ChevronRight className="w-3 h-3 text-muted-foreground" />
                          <div className="px-2 py-1 bg-foreground text-background rounded font-mono">VCF</div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Floating accent elements */}
              <div className="absolute -right-4 -bottom-4 w-32 h-32 bg-secondary/50 rounded-xl border border-border -z-10" />
            </div>
          </FadeInOnScroll>
        </div>
      </div>
    </section>
  )
}

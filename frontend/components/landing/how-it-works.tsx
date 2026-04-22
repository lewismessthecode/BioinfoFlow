"use client"

import { Folder, MessageSquare, GitBranch, Play, ChevronRight } from "lucide-react"
import { FadeInOnScroll, StaggerContainer, StaggerItem } from "@/components/ui/scroll-animations"
import { useTranslations } from "next-intl"

export function HowItWorks() {
  const t = useTranslations("landing.howItWorks")

  const steps = [
    {
      number: "01",
      title: t("step1.title"),
      description: t("step1.description"),
      icon: Folder,
    },
    {
      number: "02",
      title: t("step2.title"),
      description: t("step2.description"),
      icon: MessageSquare,
    },
    {
      number: "03",
      title: t("step3.title"),
      description: t("step3.description"),
      icon: GitBranch,
    },
    {
      number: "04",
      title: t("step4.title"),
      description: t("step4.description"),
      icon: Play,
    },
  ]

  return (
    <section id="workflows" className="section-padding bg-background">
      <div className="container mx-auto px-6">
        <FadeInOnScroll>
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-semibold tracking-tight mb-5">
              {t("title")}
            </h2>
            <p className="text-muted-foreground text-lg md:text-xl max-w-2xl mx-auto">
              {t("subtitle")}
            </p>
          </div>
        </FadeInOnScroll>

        {/* Desktop: Horizontal Timeline */}
        <div className="hidden md:block max-w-5xl mx-auto">
          <StaggerContainer staggerDelay={0.15}>
            <div className="relative">
              {/* Connection Line - Dashed */}
              <div className="absolute top-[64px] left-[10%] right-[10%] h-[2px] border-t-2 border-dashed border-border" />
              
              <div className="grid grid-cols-4 gap-4 lg:gap-6">
                {steps.map((step, index) => (
                  <StaggerItem key={step.number}>
                    <div className="relative">
                      {/* Step Card */}
                      <div className="bg-card border border-border rounded-xl p-5 lg:p-6 hover:border-foreground/20 transition-colors duration-200">
                        {/* Icon Circle */}
                        <div className="w-12 h-12 rounded-full bg-foreground text-background flex items-center justify-center mb-4 relative z-10">
                          <step.icon className="w-5 h-5" />
                        </div>
                        
                        <span className="text-xs font-mono text-muted-foreground mb-2 block">
                          {step.number}
                        </span>
                        <h3 className="font-semibold mb-2 text-base lg:text-lg">{step.title}</h3>
                        <p className="text-sm text-muted-foreground leading-relaxed">
                          {step.description}
                        </p>
                      </div>
                      
                      {/* Connector Arrow */}
                      {index < steps.length - 1 && (
                        <div className="absolute top-[52px] -right-2 lg:-right-3 z-20 flex items-center">
                          <div className="w-5 h-5 rounded-full bg-background border border-border flex items-center justify-center">
                            <ChevronRight className="w-3 h-3 text-muted-foreground" />
                          </div>
                        </div>
                      )}
                    </div>
                  </StaggerItem>
                ))}
              </div>
            </div>
          </StaggerContainer>
        </div>

        {/* Mobile: Vertical Timeline */}
        <div className="md:hidden">
          <StaggerContainer className="space-y-4" staggerDelay={0.12}>
            {steps.map((step, index) => (
              <StaggerItem key={step.number}>
                <div className="relative flex gap-4">
                  {/* Vertical Line */}
                  {index < steps.length - 1 && (
                    <div className="absolute left-7 top-16 bottom-0 w-[2px] border-l-2 border-dashed border-border" />
                  )}
                  
                  {/* Icon */}
                  <div className="w-12 h-12 rounded-full bg-foreground text-background flex items-center justify-center shrink-0 relative z-10">
                    <step.icon className="w-5 h-5" />
                  </div>
                  
                  {/* Content */}
                  <div className="pb-8 flex-1">
                    <div className="bg-card border border-border rounded-xl p-4">
                      <span className="text-xs font-mono text-muted-foreground mb-1 block">
                        {step.number}
                      </span>
                      <h3 className="font-semibold mb-1">{step.title}</h3>
                      <p className="text-sm text-muted-foreground leading-relaxed">
                        {step.description}
                      </p>
                    </div>
                  </div>
                </div>
              </StaggerItem>
            ))}
          </StaggerContainer>
        </div>
      </div>
    </section>
  )
}

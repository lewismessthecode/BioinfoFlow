"use client"

import { Lock, Folder, Shield, FileCheck, Server, Eye } from "lucide-react"
import { useTranslations } from "next-intl"

export function SecuritySection() {
  const t = useTranslations("landing.security")

  const securityFeatures = [
    {
      icon: Lock,
      title: t("dataNeverLeaves.title"),
      description: t("dataNeverLeaves.description")
    },
    {
      icon: FileCheck,
      title: t("auditTrails.title"),
      description: t("auditTrails.description")
    },
    {
      icon: Folder,
      title: t("localArtifacts.title"),
      description: t("localArtifacts.description")
    },
    {
      icon: Shield,
      title: t("secureByDesign.title"),
      description: t("secureByDesign.description")
    },
    {
      icon: Server,
      title: t("yourInfrastructure.title"),
      description: t("yourInfrastructure.description")
    },
    {
      icon: Eye,
      title: t("transparentExecution.title"),
      description: t("transparentExecution.description")
    },
  ]

  return (
    <section className="section-padding bg-secondary/30">
      <div className="container mx-auto px-6">
        <div className="max-w-6xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 items-start">
            {/* Left: Header + Icon Grid */}
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-border bg-background text-sm text-muted-foreground mb-6">
                <Lock className="w-3.5 h-3.5" />
                {t("badge")}
              </div>

              <h2 className="text-3xl md:text-4xl font-semibold tracking-tight mb-4">
                {t("title")}
              </h2>
              <p className="text-muted-foreground text-lg mb-10 max-w-md">
                {t("subtitle")}
              </p>
              
              {/* Visual: Privacy icons */}
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-2xl bg-foreground text-background flex items-center justify-center">
                  <Shield className="w-8 h-8" />
                </div>
                <div className="w-12 h-12 rounded-xl bg-card border border-border flex items-center justify-center">
                  <Lock className="w-5 h-5 text-muted-foreground" />
                </div>
                <div className="w-12 h-12 rounded-xl bg-card border border-border flex items-center justify-center">
                  <Folder className="w-5 h-5 text-muted-foreground" />
                </div>
              </div>
            </div>
            
            {/* Right: Feature Grid */}
            <div className="grid sm:grid-cols-2 gap-4">
              {securityFeatures.map((feature) => (
                <div 
                  key={feature.title}
                  className="bg-card border border-border rounded-xl p-5 hover:border-foreground/20 transition-colors"
                >
                  <feature.icon className="w-5 h-5 mb-3 text-muted-foreground" />
                  <h3 className="font-medium mb-1">{feature.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {feature.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

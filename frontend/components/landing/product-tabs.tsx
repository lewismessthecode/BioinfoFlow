"use client"

import { useState, useRef, useCallback, useMemo } from "react"
import { cn } from "@/lib/utils"
import { MessageSquare, Workflow, Play, Container, ChevronRight, CheckCircle2, Clock, Terminal } from "lucide-react"
import { motion, AnimatePresence, useReducedMotion } from "framer-motion"
import { FadeInOnScroll } from "@/components/ui/scroll-animations"
import { useTranslations } from "next-intl"

type ChatPreview = {
  type: "chat"
  content: { role: "user" | "agent"; text: string }[]
}

type ListPreview = {
  type: "list"
  items: { name: string; version: string; status: string }[]
}

type RunsPreview = {
  type: "runs"
  items: { name: string; status: string; time: string }[]
}

type ImagesPreview = {
  type: "images"
  items: { name: string; tag: string; size: string }[]
}

type TabPreview = ChatPreview | ListPreview | RunsPreview | ImagesPreview

type Tab = {
  id: string
  label: string
  icon: typeof MessageSquare
  title: string
  description: string
  preview: TabPreview
}

export function ProductTabs() {
  const [activeTab, setActiveTab] = useState("agent")
  const tabsRef = useRef<HTMLDivElement>(null)
  const prefersReducedMotion = useReducedMotion()
  const t = useTranslations("landing.productTabs")

  const tabs: Tab[] = useMemo(() => [
    {
      id: "agent",
      label: t("agent.label"),
      icon: MessageSquare,
      title: t("agent.title"),
      description: t("agent.description"),
      preview: {
        type: "chat",
        content: [
          { role: "user", text: t("agent.chatExample1") },
          { role: "agent", text: t("agent.chatExample2") },
        ]
      }
    },
    {
      id: "workflows",
      label: t("workflows.label"),
      icon: Workflow,
      title: t("workflows.title"),
      description: t("workflows.description"),
      preview: {
        type: "list",
        items: [
          { name: "nf-core/rnaseq", version: "3.14.0", status: "verified" },
          { name: "nf-core/sarek", version: "3.4.0", status: "verified" },
          { name: "custom/variant-qc", version: "1.2.0", status: "local" },
        ]
      }
    },
    {
      id: "runs",
      label: t("runs.label"),
      icon: Play,
      title: t("runs.title"),
      description: t("runs.description"),
      preview: {
        type: "runs",
        items: [
          { name: "rnaseq-batch-001", status: "completed", time: "2h 34m" },
          { name: "chipseq-h3k27ac", status: "running", time: "45m" },
          { name: "variant-calling", status: "completed", time: "5h 12m" },
        ]
      }
    },
    {
      id: "images",
      label: t("images.label"),
      icon: Container,
      title: t("images.title"),
      description: t("images.description"),
      preview: {
        type: "images",
        items: [
          { name: "bioinfoflow/deseq2", tag: "1.42.0", size: "1.2 GB" },
          { name: "nfcore/rnaseq", tag: "3.14.0", size: "2.8 GB" },
          { name: "biocontainers/bwa", tag: "0.7.17", size: "890 MB" },
        ]
      }
    },
  ], [t])

  const currentTab = tabs.find((tab) => tab.id === activeTab) || tabs[0]

  // Keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const currentIndex = tabs.findIndex((tab) => tab.id === activeTab)
    let nextIndex = currentIndex

    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault()
      nextIndex = (currentIndex + 1) % tabs.length
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault()
      nextIndex = (currentIndex - 1 + tabs.length) % tabs.length
    } else if (e.key === "Home") {
      e.preventDefault()
      nextIndex = 0
    } else if (e.key === "End") {
      e.preventDefault()
      nextIndex = tabs.length - 1
    }

    if (nextIndex !== currentIndex) {
      setActiveTab(tabs[nextIndex].id)
    }
  }, [activeTab, tabs])

  return (
    <section id="product" className="section-padding bg-background">
      <div className="container mx-auto px-6">
        <FadeInOnScroll>
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-semibold tracking-tight mb-5">
              {t("title")}
            </h2>
            <p className="text-muted-foreground text-lg md:text-xl max-w-2xl mx-auto">
              {t("subtitle")}
            </p>
          </div>
        </FadeInOnScroll>

        {/* Tab Navigation */}
        <FadeInOnScroll delay={0.1}>
          <div className="flex justify-center mb-14">
            <div
              ref={tabsRef}
              role="tablist"
              aria-label="Product features"
              className="inline-flex gap-1.5 p-1.5 bg-secondary rounded-full shadow-sm relative"
              onKeyDown={handleKeyDown}
            >
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  role="tab"
                  aria-selected={activeTab === tab.id}
                  aria-controls={`panel-${tab.id}`}
                  tabIndex={activeTab === tab.id ? 0 : -1}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "relative flex items-center gap-2 px-5 py-2.5 rounded-full text-sm md:text-base font-medium transition-colors duration-200",
                    activeTab === tab.id
                      ? "text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {activeTab === tab.id && (
                    <motion.div
                      layoutId="activeTab"
                      className="absolute inset-0 bg-background rounded-full shadow-md"
                      transition={{
                        type: "spring",
                        bounce: prefersReducedMotion ? 0 : 0.15,
                        duration: prefersReducedMotion ? 0 : 0.5,
                      }}
                    />
                  )}
                  <span className="relative z-10 flex items-center gap-2">
                    <tab.icon className="w-4 h-4" />
                    {tab.label}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </FadeInOnScroll>

        {/* Tab Content */}
        <FadeInOnScroll delay={0.2}>
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center max-w-5xl mx-auto">
            <AnimatePresence mode="wait">
              <motion.div
                key={currentTab.id + "-text"}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: prefersReducedMotion ? 0 : 0.3 }}
                className="order-2 lg:order-1"
              >
                <h3 className="text-2xl md:text-3xl lg:text-4xl font-semibold tracking-tight mb-5">
                  {currentTab.title}
                </h3>
                <p className="text-muted-foreground leading-relaxed mb-8 text-base md:text-lg lg:text-xl">
                  {currentTab.description}
                </p>
                <a
                  href="#"
                  className="inline-flex items-center gap-1 text-sm font-medium hover:gap-2 transition-[gap] group"
                >
                  {t("learnMore")} <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </a>
              </motion.div>
            </AnimatePresence>

            <AnimatePresence mode="wait">
              <motion.div
                key={currentTab.id + "-preview"}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{
                  duration: prefersReducedMotion ? 0 : 0.3,
                  delay: prefersReducedMotion ? 0 : 0.1,
                }}
                className="order-1 lg:order-2"
              >
                <div className="bg-card border border-border rounded-xl overflow-hidden shadow-lg">
                  <div className="h-11 bg-secondary/50 border-b border-border flex items-center px-4 gap-2">
                    <div className="flex gap-1.5">
                      <div className="w-3 h-3 rounded-full bg-border" />
                      <div className="w-3 h-3 rounded-full bg-border" />
                      <div className="w-3 h-3 rounded-full bg-border" />
                    </div>
                    <span className="text-xs text-muted-foreground ml-2 font-mono">{currentTab.id}</span>
                  </div>
                  
                  <div className="p-5 min-h-[280px]">
                    {currentTab.preview.type === "chat" && (
                      <div className="space-y-4">
                        {currentTab.preview.content?.map((msg, i) => (
                          <motion.div 
                            key={i} 
                            className={cn(
                              "flex gap-2",
                              msg.role === "user" ? "justify-end" : ""
                            )}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: prefersReducedMotion ? 0 : i * 0.15 }}
                          >
                            <div className={cn(
                              "rounded-lg px-4 py-2.5 text-sm max-w-[85%]",
                              msg.role === "user" 
                                ? "bg-foreground text-background" 
                                : "bg-secondary text-muted-foreground"
                            )}>
                              {msg.text}
                            </div>
                          </motion.div>
                        ))}
                      </div>
                    )}
                    
                    {currentTab.preview.type === "list" && (
                      <div className="space-y-2.5">
                        {(currentTab.preview as ListPreview).items.map((item, i) => (
                          <motion.div
                            key={i}
                            className="flex items-center justify-between p-3.5 bg-secondary/50 rounded-lg hover:bg-secondary/70 transition-colors"
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: prefersReducedMotion ? 0 : i * 0.1 }}
                          >
                            <div className="flex items-center gap-3">
                              <Workflow className="w-4 h-4 text-muted-foreground" />
                              <span className="font-mono text-sm">{item.name}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-muted-foreground font-mono">{item.version}</span>
                              <CheckCircle2 className="w-4 h-4 text-muted-foreground" />
                            </div>
                          </motion.div>
                        ))}
                      </div>
                    )}

                    {currentTab.preview.type === "runs" && (
                      <div className="space-y-2.5">
                        {(currentTab.preview as RunsPreview).items.map((item, i) => (
                          <motion.div
                            key={i}
                            className="flex items-center justify-between p-3.5 bg-secondary/50 rounded-lg hover:bg-secondary/70 transition-colors"
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: prefersReducedMotion ? 0 : i * 0.1 }}
                          >
                            <div className="flex items-center gap-3">
                              <div className={cn(
                                "w-2.5 h-2.5 rounded-full",
                                item.status === "running"
                                  ? "bg-foreground animate-pulse motion-reduce:animate-none"
                                  : "bg-muted-foreground"
                              )} />
                              <span className="font-mono text-sm">{item.name}</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                              <Clock className="w-3.5 h-3.5" />
                              {item.time}
                            </div>
                          </motion.div>
                        ))}
                      </div>
                    )}

                    {currentTab.preview.type === "images" && (
                      <div className="space-y-2.5">
                        {(currentTab.preview as ImagesPreview).items.map((item, i) => (
                          <motion.div
                            key={i}
                            className="flex items-center justify-between p-3.5 bg-secondary/50 rounded-lg hover:bg-secondary/70 transition-colors"
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: prefersReducedMotion ? 0 : i * 0.1 }}
                          >
                            <div className="flex items-center gap-3">
                              <Terminal className="w-4 h-4 text-muted-foreground" />
                              <span className="font-mono text-sm">{item.name}</span>
                              <span className="px-2 py-0.5 bg-background rounded text-xs font-mono">{item.tag}</span>
                            </div>
                            <span className="text-xs text-muted-foreground">{item.size}</span>
                          </motion.div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            </AnimatePresence>
          </div>
        </FadeInOnScroll>
      </div>
    </section>
  )
}

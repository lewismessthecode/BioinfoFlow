"use client"

import { useRef } from "react"
import { useTranslations } from "next-intl"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { useGSAP } from "@gsap/react"
import { ArrowUpRight, Check } from "@/lib/icons"

const capabilities = ["describe", "select", "execute", "recover", "preserve"] as const

export function CapabilityIndex() {
  const t = useTranslations("landing.capabilities")
  const root = useRef<HTMLElement>(null)

  useGSAP(
    () => {
      gsap.registerPlugin(ScrollTrigger)
      const mm = gsap.matchMedia()

      mm.add("(min-width: 900px) and (prefers-reduced-motion: no-preference)", () => {
        const rows = gsap.utils.toArray<HTMLElement>(".landing-capability-row")

        gsap.fromTo(
          rows,
          { autoAlpha: 0.28, y: 28 },
          {
            autoAlpha: 1,
            y: 0,
            stagger: 0.12,
            ease: "none",
            scrollTrigger: {
              trigger: root.current,
              start: "top 72%",
              end: "bottom 62%",
              scrub: 0.65,
            },
          }
        )

        gsap.fromTo(
          ".landing-capability-progress",
          { scaleY: 0 },
          {
            scaleY: 1,
            ease: "none",
            scrollTrigger: {
              trigger: root.current,
              start: "top 70%",
              end: "bottom 58%",
              scrub: 0.65,
            },
          }
        )

        return () => ScrollTrigger.getAll().forEach((trigger) => trigger.kill())
      })

      return () => mm.revert()
    },
    { scope: root }
  )

  return (
    <section ref={root} id="features" className="landing-capabilities px-5 py-28 md:px-8 md:py-40">
      <div className="mx-auto grid max-w-7xl gap-14 lg:grid-cols-[0.82fr_1.18fr] lg:gap-24">
        <div className="lg:sticky lg:top-32 lg:self-start">
          <p className="mb-5 text-sm font-medium text-[var(--brand-accent)]">
            {t("eyebrow")}
          </p>
          <h2 className="max-w-xl text-balance text-3xl font-medium tracking-[-0.04em] md:text-5xl">
            {t("title")}
          </h2>
          <p className="mt-6 max-w-lg text-base leading-7 text-muted-foreground">
            {t("description")}
          </p>

          <div className="mt-12 hidden max-w-md grid-cols-[auto_1fr_auto_1fr_auto_1fr_auto] items-center gap-3 lg:grid" aria-hidden="true">
            {["Goal", "Workflow", "Run", "Result"].map((label, index) => (
              <div key={label} className="contents">
                <span className="flex size-8 items-center justify-center rounded-full border border-border bg-background font-mono text-[0.6rem] text-muted-foreground">
                  {index + 1}
                </span>
                {index < 3 && <span className="h-px bg-border" />}
              </div>
            ))}
          </div>
        </div>

        <div className="relative border-t border-border pl-0 md:pl-8">
          <span className="absolute bottom-0 left-0 top-0 hidden w-px bg-border md:block" aria-hidden="true">
            <span className="landing-capability-progress block h-full w-full origin-top bg-[var(--brand-accent)]" />
          </span>

          {capabilities.map((key, index) => (
            <article
              key={key}
              className="landing-capability-row group grid gap-5 border-b border-border py-8 md:grid-cols-[3.25rem_minmax(0,1fr)] md:py-10"
            >
              <span className="font-mono text-xs text-muted-foreground">0{index + 1}</span>
              <div>
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <h3 className="text-xl font-medium tracking-[-0.02em] md:text-2xl">
                    {t(`${key}.title`)}
                  </h3>
                  <span className="inline-flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    {t(`${key}.surface`)}
                    <ArrowUpRight className="size-3.5 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                  </span>
                </div>
                <p className="mt-4 max-w-2xl text-sm leading-6 text-muted-foreground md:text-base md:leading-7">
                  {t(`${key}.description`)}
                </p>
                <span className="mt-5 inline-flex items-center gap-2 text-xs text-foreground/70">
                  <Check className="size-3.5 text-[var(--brand-accent)]" />
                  {t(`${key}.proof`)}
                </span>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

"use client"

import { useRef } from "react"
import { useTranslations } from "next-intl"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { useGSAP } from "@gsap/react"
import { Check } from "@/lib/icons"

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

        const rowsTween = gsap.fromTo(
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
        return () => {
          rowsTween.scrollTrigger?.kill()
          rowsTween.kill()
        }
      })

      return () => mm.revert()
    },
    { scope: root }
  )

  return (
    <section ref={root} id="features" className="landing-capabilities px-5 py-28 md:px-8 md:py-40">
      <div className="landing-narrative-layout mx-auto grid max-w-7xl gap-14">
        <div className="xl:sticky xl:top-32 xl:self-start">
          <p className="landing-section-kicker">{t("eyebrow")}</p>
          <h2 className="mt-5 max-w-xl text-balance text-3xl font-medium tracking-[-0.045em] md:text-5xl">
            {t("title")}
          </h2>
          <p className="mt-6 max-w-lg text-base leading-7 text-muted-foreground">
            {t("description")}
          </p>
        </div>

        <div className="landing-method-index border-t border-border">

          {capabilities.map((key) => (
            <article
              key={key}
              className="landing-capability-row group border-b border-border py-8 md:py-10"
            >
              <div>
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <h3 className="text-xl font-medium tracking-[-0.025em] md:text-2xl">
                    {t(`${key}.title`)}
                  </h3>
                  <span className="landing-capability-surface">{t(`${key}.surface`)}</span>
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

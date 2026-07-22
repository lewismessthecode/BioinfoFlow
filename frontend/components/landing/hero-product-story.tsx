"use client"

import Image from "next/image"
import Link from "next/link"
import { useRef } from "react"
import { useTranslations } from "next-intl"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { useGSAP } from "@gsap/react"
import { ArrowRight, Check } from "@/lib/icons"
import { Button } from "@/components/ui/button"

const stages = [
  { id: "dashboard", number: "01" },
  { id: "agent", number: "02" },
  { id: "workflows", number: "03" },
  { id: "runs", number: "04" },
] as const

export function HeroProductStory() {
  const t = useTranslations("landing.story")
  const root = useRef<HTMLElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const heroCopy = useRef<HTMLDivElement>(null)
  const productFrame = useRef<HTMLDivElement>(null)
  const screenRefs = useRef<Array<HTMLDivElement | null>>([])
  const copyRefs = useRef<Array<HTMLDivElement | null>>([])
  const progressRefs = useRef<Array<HTMLSpanElement | null>>([])

  useGSAP(
    () => {
      gsap.registerPlugin(ScrollTrigger)
      const mm = gsap.matchMedia()

      mm.add("(prefers-reduced-motion: reduce)", () => {
        gsap.set([heroCopy.current, productFrame.current], { clearProps: "all" })
      })

      mm.add(
        "(min-width: 900px) and (prefers-reduced-motion: no-preference)",
        () => {
          const screens = screenRefs.current.filter(Boolean)
          const copies = copyRefs.current.filter(Boolean)
          const progress = progressRefs.current.filter(Boolean)

          gsap.set(screens.slice(1), { autoAlpha: 0, yPercent: 4, scale: 0.992 })
          gsap.set(copies.slice(1), { autoAlpha: 0, y: 16 })
          gsap.set(progress, { scaleX: 0, transformOrigin: "left center" })
          gsap.set(progress[0], { scaleX: 1 })

          const timeline = gsap.timeline({
            defaults: { ease: "none" },
            scrollTrigger: {
              trigger: root.current,
              start: "top top",
              end: "+=440%",
              scrub: 0.7,
              pin: stage.current,
              anticipatePin: 1,
              invalidateOnRefresh: true,
            },
          })

          timeline
            .fromTo(
              productFrame.current,
              { scale: 0.88, y: 0 },
              {
                scale: 1,
                y: () => -(window.innerHeight * 0.61 - 104),
                duration: 1.1,
              },
              0
            )
            .to(heroCopy.current, { autoAlpha: 0, y: -48, duration: 0.55 }, 0.12)

          stages.slice(1).forEach((_, index) => {
            const previous = index
            const current = index + 1
            const position = 1.15 + index * 1.05

            timeline
              .to(
                [screens[previous], copies[previous]],
                { autoAlpha: 0, y: -12, duration: 0.28 },
                position
              )
              .fromTo(
                screens[current],
                { autoAlpha: 0, yPercent: 4, scale: 0.992 },
                { autoAlpha: 1, yPercent: 0, scale: 1, duration: 0.42 },
                position + 0.12
              )
              .fromTo(
                copies[current],
                { autoAlpha: 0, y: 16 },
                { autoAlpha: 1, y: 0, duration: 0.35 },
                position + 0.18
              )
              .to(progress[current], { scaleX: 1, duration: 0.3 }, position + 0.18)
          })

          return () => timeline.scrollTrigger?.kill()
        }
      )

      return () => mm.revert()
    },
    { scope: root }
  )

  return (
    <section ref={root} id="product" className="landing-story-root relative">
      <div ref={stage} className="landing-story-stage">
        <div ref={heroCopy} className="landing-hero-copy mx-auto max-w-7xl px-5 text-center">
          <p className="mb-5 text-[0.68rem] font-medium uppercase tracking-[0.24em] text-[var(--brand-accent)]">
            {t("eyebrow")}
          </p>
          <h1 className="text-balance text-[clamp(2.7rem,5.2vw,5rem)] font-medium leading-[0.98] tracking-[-0.06em]">
            <span className="block">{t("titleSuffix")}</span>
          </h1>
          <p className="mx-auto mt-7 max-w-xl text-balance text-base leading-7 text-muted-foreground md:text-lg">
            {t("description")}
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Button asChild size="lg" className="rounded-md px-5 shadow-none active:translate-y-px">
              <Link href="/auth">
                {t("primaryAction")}
                <ArrowRight className="size-4" />
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="rounded-md bg-background px-5 shadow-none active:translate-y-px">
              <Link href="#features">{t("secondaryAction")}</Link>
            </Button>
          </div>
          <p className="mt-5 inline-flex items-center gap-2 text-xs text-muted-foreground">
            <Check className="size-3.5 text-[var(--brand-accent)]" />
            {t("reassurance")}
          </p>
        </div>

        <div ref={productFrame} className="landing-product-frame">
          <div className="landing-product-meta" aria-hidden="true">
            <span className="landing-window-controls">
              <span className="landing-window-control bg-[var(--landing-window-close)]" />
              <span className="landing-window-control bg-[var(--landing-window-minimize)]" />
              <span className="landing-window-control bg-[var(--landing-window-maximize)]" />
            </span>
          </div>

          <div className="landing-product-viewport">
            {stages.map((stageItem, index) => (
              <div
                key={stageItem.id}
                ref={(node) => { screenRefs.current[index] = node }}
                className="landing-product-screen"
                aria-hidden={index === 0 ? undefined : true}
              >
                <Image
                  src={`/landing/product/${stageItem.id}-light.webp`}
                  alt={t(`stages.${stageItem.id}.alt`)}
                  width={2560}
                  height={1154}
                  priority={index === 0}
                  className="h-full w-full object-cover object-top dark:hidden"
                />
                <Image
                  src={`/landing/product/${stageItem.id}-dark.webp`}
                  alt=""
                  width={2560}
                  height={1154}
                  priority={index === 0}
                  className="hidden h-full w-full object-cover object-top dark:block"
                />
              </div>
            ))}
          </div>

          <div className="landing-product-caption">
            <div className="relative min-h-24 md:min-h-20">
              {stages.map((stageItem, index) => (
                <div
                  key={stageItem.id}
                  ref={(node) => { copyRefs.current[index] = node }}
                  className="landing-stage-copy"
                >
                  <p className="font-mono text-[0.65rem] text-[var(--brand-accent)]">
                    {stageItem.number} / {t(`stages.${stageItem.id}.label`)}
                  </p>
                  <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground md:text-base">
                    {t(`stages.${stageItem.id}.description`)}
                  </p>
                </div>
              ))}
            </div>
            <div className="hidden w-60 grid-cols-4 gap-2 md:grid" aria-hidden="true">
              {stages.map((stageItem, index) => (
                <span key={stageItem.id} className="h-0.5 overflow-hidden rounded-full bg-border">
                  <span
                    ref={(node) => { progressRefs.current[index] = node }}
                    className="block h-full w-full bg-[var(--brand-accent)]"
                  />
                </span>
              ))}
            </div>
          </div>
        </div>

      </div>

      <div className="landing-static-story px-5 pb-20 pt-12">
        <div className="mx-auto max-w-5xl space-y-12">
          {stages.map((stageItem) => (
            <article key={stageItem.id} className="space-y-4">
              <div className="overflow-hidden rounded-lg border border-border bg-card shadow-[var(--landing-shadow)]">
                <Image
                  src={`/landing/product/${stageItem.id}-light.webp`}
                  alt={t(`stages.${stageItem.id}.alt`)}
                  width={2560}
                  height={1154}
                  className="h-auto w-full dark:hidden"
                />
                <Image
                  src={`/landing/product/${stageItem.id}-dark.webp`}
                  alt=""
                  width={2560}
                  height={1154}
                  className="hidden h-auto w-full dark:block"
                />
              </div>
              <div className="grid gap-2 border-t border-border pt-4 sm:grid-cols-[7rem_1fr]">
                <p className="font-mono text-xs text-[var(--brand-accent)]">
                  {stageItem.number} / {t(`stages.${stageItem.id}.label`)}
                </p>
                <p className="text-sm leading-6 text-muted-foreground">
                  {t(`stages.${stageItem.id}.description`)}
                </p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

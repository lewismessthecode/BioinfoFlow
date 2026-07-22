import { existsSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const readFrontendFile = (path: string) =>
  readFileSync(resolve(process.cwd(), path), "utf8")

describe("Attio-led landing page", () => {
  it("provides a stable preview route that bypasses root access redirects", () => {
    const source = readFrontendFile("app/landing-preview/page.tsx")
    const proxySource = readFrontendFile("proxy.ts")

    expect(source).toContain("<DemoLandingPage />")
    expect(proxySource.match(/"\/landing-preview"/g)).toHaveLength(2)
  })

  it("composes one continuous product story without a workflow logo band", () => {
    const source = readFrontendFile("components/landing/demo-landing-page.tsx")

    expect(source).toContain("<HeroProductStory />")
    expect(source.match(/<HeroProductStory \/>/g)).toHaveLength(1)
    expect(source).not.toContain("<WorkflowBand />")
    expect(source).toContain("<CapabilityIndex />")
    expect(source.indexOf("<HeroProductStory />")).toBeLessThan(
      source.indexOf("<CapabilityIndex />")
    )
  })

  it("uses quiet traffic-light chrome without product-tour labels", () => {
    const source = readFrontendFile("components/landing/hero-product-story.tsx")

    expect(source).toContain("landing-window-controls")
    expect(source).not.toContain("landing-scroll-cue")
    expect(source).not.toContain("liveProduct")
    expect(source).not.toContain("localRuntime")
  })

  it("reduces the local-first section to three concrete product guarantees", () => {
    const source = readFrontendFile("components/landing/security-section.tsx")

    expect(source).toContain('"dataControl"')
    expect(source).toContain('"approval"')
    expect(source).toContain('"traceability"')
    expect(source).not.toContain("securityFeatures")
  })

  it("defines the real product stages in the approved order with accessible captures", () => {
    const source = readFrontendFile("components/landing/hero-product-story.tsx")

    const dashboard = source.indexOf('id: "dashboard"')
    const agent = source.indexOf('id: "agent"')
    const workflows = source.indexOf('id: "workflows"')
    const runs = source.indexOf('id: "runs"')

    expect(dashboard).toBeGreaterThan(-1)
    expect(dashboard).toBeLessThan(agent)
    expect(agent).toBeLessThan(workflows)
    expect(workflows).toBeLessThan(runs)
    expect(source).toContain("alt={t(`stages.${stageItem.id}.alt`)}")
    expect(source).toContain("dark:hidden")
    expect(source).toContain("dark:block")
  })

  it("uses scoped GSAP choreography with a complete reduced-motion path", () => {
    const source = readFrontendFile("components/landing/hero-product-story.tsx")

    expect(source).toContain("useGSAP(")
    expect(source).toContain("gsap.matchMedia()")
    expect(source).toContain("prefers-reduced-motion: reduce")
    expect(source).toContain("mm.revert()")
    expect(source).toContain("ScrollTrigger")
  })

  it("ships every light and dark product capture used by the story", () => {
    for (const stage of ["dashboard", "agent", "workflows", "runs"]) {
      for (const theme of ["light", "dark"]) {
        expect(
          existsSync(
            resolve(
              process.cwd(),
              `public/landing/product/${stage}-${theme}.webp`
            )
          )
        ).toBe(true)
      }
    }
  })
})

import { AnnouncementBar } from "@/components/landing/announcement-bar"
import { CapabilityIndex } from "@/components/landing/capability-index"
import { Footer } from "@/components/landing/footer"
import { FinalCTA } from "@/components/landing/final-cta"
import { HardwareSection } from "@/components/landing/hardware-section"
import { HeroProductStory } from "@/components/landing/hero-product-story"
import { Navigation } from "@/components/landing/navigation"
import { SecuritySection } from "@/components/landing/security-section"

export function DemoLandingPage() {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      data-testid="demo-landing-page"
      className="landing-shell min-h-dvh bg-background text-foreground"
    >
      <AnnouncementBar />
      <Navigation />
      <HeroProductStory />
      <CapabilityIndex />
      <HardwareSection />
      <SecuritySection />
      <FinalCTA />
      <Footer />
    </main>
  )
}

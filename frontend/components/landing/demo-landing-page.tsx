import { AnnouncementBar } from "@/components/landing/announcement-bar"
import { BentoGrid } from "@/components/landing/bento-grid"
import { Footer } from "@/components/landing/footer"
import { FinalCTA } from "@/components/landing/final-cta"
import { HeroSection } from "@/components/landing/hero-section"
import { HowItWorks } from "@/components/landing/how-it-works"
import { Navigation } from "@/components/landing/navigation"
import { ProductTabs } from "@/components/landing/product-tabs"
import { ResultsSection } from "@/components/landing/results-section"
import { SecuritySection } from "@/components/landing/security-section"
import { TrustBar } from "@/components/landing/trust-bar"

export function DemoLandingPage() {
  return (
    <main
      data-testid="demo-landing-page"
      className="min-h-dvh bg-background text-foreground"
    >
      <AnnouncementBar />
      <Navigation />
      <HeroSection />
      <TrustBar />
      <ProductTabs />
      <BentoGrid />
      <HowItWorks />
      <ResultsSection />
      <SecuritySection />
      <FinalCTA />
      <Footer />
    </main>
  )
}

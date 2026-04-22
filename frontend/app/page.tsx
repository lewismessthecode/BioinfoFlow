import { AnnouncementBar } from "@/components/landing/announcement-bar";
import { Navigation } from "@/components/landing/navigation";
import { HeroSection } from "@/components/landing/hero-section";
import { TrustBar } from "@/components/landing/trust-bar";
import { ProductTabs } from "@/components/landing/product-tabs";
import { BentoGrid } from "@/components/landing/bento-grid";
import { HardwareSection } from "@/components/landing/hardware-section";
import { HowItWorks } from "@/components/landing/how-it-works";
import { QuoteSection } from "@/components/landing/quote-section";
import { ResultsSection } from "@/components/landing/results-section";
import { SecuritySection } from "@/components/landing/security-section";
import { FinalCTA } from "@/components/landing/final-cta";
import { Footer } from "@/components/landing/footer";

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      <AnnouncementBar />
      <Navigation />

      <main id="main-content">
        <HeroSection />
        <TrustBar />
        <ProductTabs />
        <HardwareSection />
        <BentoGrid />
        <HowItWorks />
        <QuoteSection />
        <ResultsSection />
        <SecuritySection />
        <FinalCTA />
      </main>

      <Footer />
    </div>
  );
}

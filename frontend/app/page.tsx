import { cookies } from "next/headers"
import { redirect } from "next/navigation"

import { DemoLandingPage } from "@/components/landing/demo-landing-page"
import { DEMO_ACCESS_COOKIE, isDemoDeployment } from "@/lib/demo-auth"

const productJsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Bioinfoflow",
  alternateName: ["bioinfoflow", "BioInfoFlow"],
  url: "https://www.bioinfoflow.com",
  applicationCategory: "ScienceApplication",
  operatingSystem: "Linux, macOS, Windows",
  description:
    "Bioinfoflow is a local-first agentic bioinformatics platform for turning biological intent into reproducible pipelines that run on your own data.",
  softwareHelp: "https://github.com/lewisliu/bioinfoflow",
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
  },
  author: {
    "@type": "Organization",
    name: "Bioinfoflow",
    url: "https://www.bioinfoflow.com",
  },
}

export default async function RootPage() {
  if (isDemoDeployment()) {
    const cookieStore = await cookies()
    if (cookieStore.get(DEMO_ACCESS_COOKIE)?.value) {
      redirect("/agent")
    }

    return (
      <>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(productJsonLd) }}
        />
        <DemoLandingPage />
      </>
    )
  }

  redirect("/auth")
}

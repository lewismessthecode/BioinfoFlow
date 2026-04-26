import { cookies } from "next/headers"
import { redirect } from "next/navigation"

import { DemoLandingPage } from "@/components/landing/demo-landing-page"
import { DEMO_ACCESS_COOKIE, isDemoDeployment } from "@/lib/demo-auth"

export default async function RootPage() {
  if (isDemoDeployment()) {
    const cookieStore = await cookies()
    if (cookieStore.get(DEMO_ACCESS_COOKIE)?.value) {
      redirect("/agent")
    }

    return <DemoLandingPage />
  }

  redirect("/auth")
}
